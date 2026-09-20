"""Recording platform numbers for content.

The analytics (`aggregate_performance`, `list_optimization_candidates`) and the
chat agent's performance tools always read `content_metrics`, but nothing in the
product could write to it: outside the demo seed script the table stayed empty
and every performance answer was computed from no data.
"""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_store
from src.api.main import app
from src.models import ContentType, GeneratedContent
from src.storage.content_store import ContentMetrics, User

OTHER_USER_ID = "33333333333333333333333333333333"


@pytest.fixture
def client(store):
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _content(store, title: str = "Post", content_type: ContentType = ContentType.XIAOHONGSHU) -> int:
    return store.save_content(GeneratedContent(title=title, content="body", content_type=content_type))


def _metric_rows(store, content_id: int) -> list[ContentMetrics]:
    with store._get_session() as session:
        return session.query(ContentMetrics).filter(ContentMetrics.content_id == content_id).all()


def _foreign_content(store) -> int:
    """Content owned by a second workspace, created through the unscoped store."""
    from src.api.dependencies import get_system_store

    system = get_system_store()
    with system._get_session() as session:
        session.add(User(id=OTHER_USER_ID, username="other_user", password_hash="!", is_active=True))
        session.commit()
    return _content(system.for_user(OTHER_USER_ID), title="Someone else's post")


def test_recorded_numbers_are_returned_with_their_engagement_rate(client, store):
    content_id = _content(store)

    response = client.put(
        f"/api/content/{content_id}/metrics",
        json={"platform": " Xiaohongshu ", "views": 2000, "likes": 150, "comments": 30, "shares": 20},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["platform"] == "xiaohongshu"
    assert body["engagement_rate"] == 0.1
    assert body["recorded_at"]
    assert client.get(f"/api/content/{content_id}/metrics").json() == [body]


def test_a_new_reading_replaces_the_previous_one_even_when_it_is_lower(client, store):
    content_id = _content(store)
    url = f"/api/content/{content_id}/metrics"
    client.put(url, json={"platform": "xiaohongshu", "views": 90000, "likes": 10})

    # A typo corrected downward: the analytics keep the highest-view row per
    # content, so a second row here would leave the wrong number in charge.
    client.put(url, json={"platform": "xiaohongshu", "views": 9000, "likes": 10})

    assert [row.views for row in _metric_rows(store, content_id)] == [9000]
    assert store.aggregate_performance(days=30)["top_performers"][0]["views"] == 9000


def test_each_platform_keeps_its_own_numbers(client, store):
    content_id = _content(store)
    url = f"/api/content/{content_id}/metrics"
    client.put(url, json={"platform": "xiaohongshu", "views": 1000})
    client.put(url, json={"platform": "wechat", "views": 300})

    listed = {row["platform"]: row["views"] for row in client.get(url).json()}

    assert listed == {"wechat": 300, "xiaohongshu": 1000}


def test_recording_collapses_duplicate_rows_left_by_older_data(client, store):
    content_id = _content(store)
    with store._get_session() as session:
        session.add_all(
            [ContentMetrics(content_id=content_id, platform="xiaohongshu", views=views) for views in (50000, 100)]
        )
        session.commit()

    client.put(f"/api/content/{content_id}/metrics", json={"platform": "xiaohongshu", "views": 700})

    assert [row.views for row in _metric_rows(store, content_id)] == [700]


def test_concurrent_recordings_for_one_platform_leave_a_single_row(store, monkeypatch):
    content_id = _content(store)
    writers = 6

    # Hold every writer between "no row yet" and its insert. Unserialized, all of
    # them pass the check before any commits and each inserts its own row; the
    # natural window is too narrow for the race to show up reliably.
    open_session = store._get_session

    def slow_insert_session():
        session = open_session()
        add = session.add

        def delayed_add(instance, *args, **kwargs):
            time.sleep(0.3)
            return add(instance, *args, **kwargs)

        session.add = delayed_add
        return session

    monkeypatch.setattr(store, "_get_session", slow_insert_session)
    start = threading.Barrier(writers)
    errors: list[BaseException] = []

    def record(views: int) -> None:
        try:
            start.wait(timeout=30)
            store.record_content_metrics(content_id, "xiaohongshu", views=views, likes=0, comments=0, shares=0)
        except BaseException as exc:  # noqa: BLE001 -- reported by the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=record, args=(1000 + index,)) for index in range(writers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert errors == []
    assert len(_metric_rows(store, content_id)) == 1


def test_unknown_content_is_not_found(client):
    assert client.get("/api/content/999999/metrics").status_code == 404
    assert client.put("/api/content/999999/metrics", json={"platform": "blog", "views": 1}).status_code == 404


def test_another_workspaces_content_is_not_found_and_stays_untouched(client, store):
    foreign_id = _foreign_content(store)

    assert client.get(f"/api/content/{foreign_id}/metrics").status_code == 404
    assert client.put(f"/api/content/{foreign_id}/metrics", json={"platform": "blog", "views": 1}).status_code == 404
    imported = client.post(
        "/api/content/metrics/import", json={"rows": [{"content_id": foreign_id, "platform": "blog", "views": 1}]}
    )

    assert imported.json() == {"recorded": 0, "missing_content_ids": [foreign_id]}
    from src.api.dependencies import get_system_store

    assert _metric_rows(get_system_store().for_user(OTHER_USER_ID), foreign_id) == []


@pytest.mark.parametrize(
    "payload",
    [
        {"platform": "blog", "views": -1},
        {"platform": "blog", "likes": 3_000_000_000},
        {"platform": "", "views": 1},
        {"platform": "blog; drop table", "views": 1},
        {"views": 1},
    ],
    ids=["negative", "overflows-int32", "blank-platform", "malformed-platform", "missing-platform"],
)
def test_invalid_numbers_are_rejected_before_reaching_the_database(client, store, payload):
    content_id = _content(store)

    assert client.put(f"/api/content/{content_id}/metrics", json=payload).status_code == 422
    assert _metric_rows(store, content_id) == []


def test_import_records_known_rows_and_reports_unknown_content_once(client, store):
    first, second = _content(store, "A"), _content(store, "B")

    response = client.post(
        "/api/content/metrics/import",
        json={
            "rows": [
                {"content_id": first, "platform": "xiaohongshu", "views": 1000, "likes": 80},
                {"content_id": second, "platform": "xiaohongshu", "views": 400, "likes": 4},
                {"content_id": 999999, "platform": "xiaohongshu", "views": 1},
                {"content_id": 999999, "platform": "wechat", "views": 1},
            ]
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"recorded": 2, "missing_content_ids": [999999]}
    assert [row.views for row in _metric_rows(store, second)] == [400]


def test_import_size_is_bounded(client, store):
    content_id = _content(store)
    rows = [{"content_id": content_id, "platform": "blog", "views": index} for index in range(501)]

    assert client.post("/api/content/metrics/import", json={"rows": rows}).status_code == 422
    assert client.post("/api/content/metrics/import", json={"rows": []}).status_code == 422


def test_recorded_numbers_drive_the_agents_performance_tools(client, store):
    strong, weak = _content(store, "Strong"), _content(store, "Weak")
    client.put(f"/api/content/{strong}/metrics", json={"platform": "xiaohongshu", "views": 10000, "likes": 1200})
    client.put(f"/api/content/{weak}/metrics", json={"platform": "xiaohongshu", "views": 10000, "likes": 20})

    performance = store.aggregate_performance(days=30)
    candidates = store.list_optimization_candidates("underperforming")

    assert performance["total_with_metrics"] == 2
    assert performance["top_performers"][0]["id"] == strong
    assert [candidate["id"] for candidate in candidates] == [weak]
