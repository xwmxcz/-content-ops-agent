"""Calendar navigation and corrections must work outside the default future window."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_store
from src.api.main import app
from src.models import ContentType, GeneratedContent
from src.storage.account_store import AccountStore
from src.storage.models import CalendarEvent


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


def content(store, title="Calendar draft"):
    return store.save_content(GeneratedContent(title=title, content="Draft", content_type=ContentType.BLOG))


def test_explicit_range_includes_past_and_distant_plans(client, store):
    content_id = content(store)
    dates = [date(2020, 1, 1), date(2020, 1, 31), date(2020, 2, 1), date(2030, 10, 1)]
    for day in dates:
        store.save_calendar_event(content_id, "blog", day)

    response = client.get("/api/calendar/events", params={"start_date": "2020-01-01", "end_date": "2020-01-31"})
    assert response.status_code == 200
    assert [item["scheduled_date"] for item in response.json()] == ["2020-01-01", "2020-01-31"]
    distant = client.get("/api/calendar/events", params={"start_date": "2030-10-01", "end_date": "2030-10-01"})
    assert len(distant.json()) == 1


def test_legacy_days_query_still_works(client, store):
    content_id = content(store)
    store.save_calendar_event(content_id, "blog", date.today())
    store.save_calendar_event(content_id, "blog", date.today() + timedelta(days=90))
    assert len(client.get("/api/calendar/events?days=60").json()) == 1


@pytest.mark.parametrize(
    "params",
    [
        {"start_date": "2026-01-01"},
        {"end_date": "2026-01-01"},
        {"start_date": "2026-02-01", "end_date": "2026-01-01"},
        {"start_date": "2026-01-01", "end_date": "2028-01-01"},
    ],
)
def test_invalid_ranges_are_rejected(client, params):
    assert client.get("/api/calendar/events", params=params).status_code == 422


def test_edit_and_delete_local_plan(client, store):
    first, second = content(store), content(store, "Replacement draft")
    created = client.post(
        "/api/calendar/events", json={"content_id": first, "platform": " BLOG ", "scheduled_date": "2030-01-01"}
    )
    assert created.status_code == 201
    event_id = created.json()["event_id"]
    assert store.get_calendar_events()[0]["platform"] == "blog"
    updated = client.put(
        f"/api/calendar/events/{event_id}",
        json={"content_id": second, "platform": "weibo", "scheduled_date": "2030-02-02"},
    )
    assert updated.status_code == 200
    row = store.get_calendar_events()[0]
    assert (row["content_id"], row["platform"], row["scheduled_date"]) == (second, "weibo", "2030-02-02")
    assert client.delete(f"/api/calendar/events/{event_id}").status_code == 204
    assert store.get_calendar_events() == []
    assert client.delete(f"/api/calendar/events/{event_id}").status_code == 404


@pytest.mark.parametrize("status", ["scheduled", "published", "completed"])
def test_platform_records_cannot_be_changed_as_local_plans(client, store, status):
    content_id = content(store)
    event_id = store.save_calendar_event(content_id, "blog", date.today())
    with store._get_session() as session:
        event = session.query(CalendarEvent).filter(CalendarEvent.id == event_id).one()
        event.status = status
        session.commit()
    payload = {"content_id": content_id, "platform": "weibo", "scheduled_date": "2030-02-02"}
    assert client.put(f"/api/calendar/events/{event_id}", json=payload).status_code == 409
    assert client.delete(f"/api/calendar/events/{event_id}").status_code == 409
    assert store.get_calendar_events()[0]["status"] == status


def test_calendar_mutations_preserve_workspace_isolation(client, store):
    from src.api.dependencies import get_system_store

    system = get_system_store()
    user = AccountStore(system).create_user("calendar_other", "!")
    other = system.for_user(user["id"])
    own_content, other_content = content(store), content(other)
    own_event = store.save_calendar_event(own_content, "blog", date.today())
    other_event = other.save_calendar_event(other_content, "blog", date.today())
    payload = {"content_id": own_content, "platform": "weibo", "scheduled_date": "2030-02-02"}
    assert client.put(f"/api/calendar/events/{other_event}", json=payload).status_code == 404
    assert client.delete(f"/api/calendar/events/{other_event}").status_code == 404
    payload["content_id"] = other_content
    assert client.put(f"/api/calendar/events/{own_event}", json=payload).status_code == 404
    assert len(other.get_calendar_events()) == 1
    assert store.get_calendar_events()[0]["content_id"] == own_content


@pytest.mark.parametrize("platform", ["", "   ", "a" * 51])
def test_invalid_platform_is_rejected(client, store, platform):
    response = client.post(
        "/api/calendar/events",
        json={"content_id": content(store), "platform": platform, "scheduled_date": "2030-01-01"},
    )
    assert response.status_code == 422
