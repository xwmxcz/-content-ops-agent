"""Analytics show current readings by creation cohort, never invented daily gains."""

from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from src.api.dependencies import get_store, get_system_store
from src.api.main import app
from src.models import ContentType, GeneratedContent
from src.storage.account_store import AccountStore
from src.storage.models import Content, ContentMetrics


@pytest.fixture
def client(store):
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_store] = lambda: store
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def content(store, title="Post", days_ago=0):
    content_id = store.save_content(GeneratedContent(title=title, content="body", content_type=ContentType.BLOG))
    with store._get_session() as session:
        row = session.query(Content).filter(Content.id == content_id).one()
        row.created_at = datetime.combine(date.today() - timedelta(days=days_ago), time.min)
        session.commit()
    return content_id


def record(store, content_id, platform="blog", views=100, likes=10, comments=0, shares=0):
    return store.record_content_metrics(
        content_id, platform, views=views, likes=likes, comments=comments, shares=shares
    )


def test_analytics_distinguish_empty_data_from_zero_readings(client, store):
    missing = content(store, "No readings")
    data = client.get("/api/stats/performance?days=7").json()
    assert data["total_contents"] == data["missing_contents"] == 1
    assert data["measured_contents"] == data["totals"]["metric_rows"] == 0
    assert data["totals"]["engagement_rate"] is None
    assert len(data["by_creation_date"]) == 7
    record(store, missing, views=0, likes=0)
    data = client.get("/api/stats/performance?days=7").json()
    assert data["measured_contents"] == data["totals"]["metric_rows"] == 1
    assert data["missing_contents"] == 0
    assert data["totals"]["views"] == 0
    assert data["totals"]["engagement_rate"] is None


def test_all_platforms_are_counted_with_a_weighted_engagement_rate(client, store):
    first, second = content(store, "First"), content(store, "Second")
    content(store, "Missing")
    record(store, first, "blog", views=100, likes=90)
    record(store, first, "wechat", views=1000, likes=10, comments=5, shares=5)
    record(store, second, "blog", views=900, likes=90)
    data = client.get("/api/stats/performance").json()
    assert data["total_contents"] == 3
    assert data["measured_contents"] == 2
    assert data["missing_contents"] == 1
    assert data["totals"]["metric_rows"] == 3
    assert data["totals"]["views"] == 2000
    assert data["totals"]["interactions"] == 200
    assert data["totals"]["engagement_rate"] == 0.1
    by_platform = {row["platform"]: row for row in data["by_platform"]}
    assert by_platform["blog"]["views"] == 1000
    assert by_platform["blog"]["metric_rows"] == 2
    assert by_platform["wechat"]["views"] == 1000


def test_concurrent_content_and_reading_creation_cannot_overcount_coverage(store):
    record(store, content(store, "Already measured"), views=10, likes=1)
    inserted = False

    def create_after_snapshot(connection, cursor, statement, parameters, context, executemany):
        nonlocal inserted
        if inserted or not statement.lstrip().upper().startswith("SELECT") or "FROM contents" not in statement:
            return
        inserted = True
        # A separate committed transaction lands after the first statistics
        # statement has its snapshot, before its caller can issue another read.
        record(store, content(store, "Concurrent measured content"), views=100, likes=10)

    event.listen(store.engine, "after_cursor_execute", create_after_snapshot)
    try:
        data = store.get_performance_stats()
    finally:
        event.remove(store.engine, "after_cursor_execute", create_after_snapshot)

    assert inserted
    assert data["missing_contents"] >= 0
    assert data["measured_contents"] <= data["total_contents"]
    assert data["total_contents"] == data["measured_contents"] == 1
    assert data["totals"]["views"] == 10
    assert all(day["measured_contents"] <= day["total_contents"] for day in data["by_creation_date"])
    refreshed = store.get_performance_stats()
    assert refreshed["total_contents"] == refreshed["measured_contents"] == 2
    assert refreshed["totals"]["views"] == 110


def test_unmeasured_contents_remain_distinct_in_the_outer_join(store):
    for index in range(3):
        content(store, f"No metrics {index}")

    data = store.get_performance_stats()

    assert data["total_contents"] == data["missing_contents"] == 3
    assert data["measured_contents"] == data["totals"]["metric_rows"] == 0
    assert data["available_platforms"] == []
    assert data["by_creation_date"][-1]["total_contents"] == 3


def test_platform_filter_changes_totals_but_preserves_available_options(client, store):
    first, second = content(store), content(store)
    record(store, first, "blog", views=100)
    record(store, second, "wechat", views=1000)
    data = client.get("/api/stats/performance", params={"platform": " BLOG "}).json()
    assert data["platform"] == "blog"
    assert data["available_platforms"] == ["blog", "wechat"]
    assert data["totals"]["views"] == 100
    assert data["measured_contents"] == 1
    assert data["missing_contents"] == 1
    assert len(data["top_contents"]) == 1
    unknown = client.get("/api/stats/performance?platform=unknown-platform").json()
    assert unknown["measured_contents"] == 0
    assert unknown["totals"]["views"] == 0


def test_creation_window_has_inclusive_days_and_excludes_future_content(client, store):
    for age in (0, 6, 7, -1):
        record(store, content(store, days_ago=age), views=100)
    data = client.get("/api/stats/performance?days=7").json()
    assert data["total_contents"] == 2
    assert data["totals"]["views"] == 200
    assert data["window_start"] == (date.today() - timedelta(days=6)).isoformat()
    assert data["window_end"] == date.today().isoformat()
    assert data["by_creation_date"][0]["views"] == 100
    assert data["by_creation_date"][-1]["views"] == 100


def test_recent_reading_belongs_to_content_creation_day_not_recording_day(client, store):
    content_id = content(store, days_ago=4)
    record(store, content_id, views=500)
    data = client.get("/api/stats/performance?days=7").json()
    assert data["by_creation_date"][2]["views"] == 500
    assert data["by_creation_date"][-1]["views"] == 0


def test_latest_duplicate_reading_wins_even_when_lower_and_timestamps_tie(client, store):
    content_id = content(store)
    now = datetime.now()
    with store._get_session() as session:
        session.add_all(
            [
                ContentMetrics(
                    content_id=content_id, platform="blog", views=90000, recorded_at=now - timedelta(days=1)
                ),
                ContentMetrics(content_id=content_id, platform="blog", views=9000, recorded_at=now),
                ContentMetrics(content_id=content_id, platform="blog", views=900, recorded_at=now),
            ]
        )
        session.commit()
    data = client.get("/api/stats/performance").json()
    assert data["totals"]["views"] == 900
    assert data["totals"]["metric_rows"] == 1
    assert data["top_contents"][0]["views"] == 900
    record(store, content_id, views=500)
    assert client.get("/api/stats/performance").json()["totals"]["views"] == 500


def test_performance_stats_do_not_leak_other_workspaces(client, store):
    system = get_system_store()
    other_user = AccountStore(system).create_user("stats_other", "!")
    other = system.for_user(other_user["id"])
    record(other, content(other, "Private foreign title"), "private-platform", views=999)
    record(store, content(store, "Own title"), "blog", views=15)
    data = client.get("/api/stats/performance").json()
    assert data["total_contents"] == data["measured_contents"] == 1
    assert data["available_platforms"] == ["blog"]
    assert data["totals"]["views"] == 15
    assert "Private foreign title" not in str(data)


def test_top_contents_are_bounded_and_sorted_by_views(client, store):
    for views in range(12):
        record(store, content(store, str(views)), views=views, likes=0)
    data = client.get("/api/stats/performance").json()
    assert [row["views"] for row in data["top_contents"]] == list(range(11, 1, -1))


@pytest.mark.parametrize("params", [{"days": 0}, {"days": 366}, {"days": "bad"}, {"platform": "p" * 51}])
def test_invalid_performance_filters_are_rejected(client, params):
    assert client.get("/api/stats/performance", params=params).status_code == 422
