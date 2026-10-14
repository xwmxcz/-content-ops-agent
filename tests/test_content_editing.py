"""Local edits must preserve related records and reject stale concurrent writes."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_store
from src.api.main import app
from src.models import ContentType, GeneratedContent
from src.storage.repositories.content_repository import ContentEditConflict


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


def draft(store):
    return store.save_content(GeneratedContent(title="原稿", content="完整正文", content_type=ContentType.BLOG))


def edit_payload(store, content_id, **changes):
    return {
        "title": " 新标题 ",
        "content": "修改后的正文\n保留换行",
        "tags": [" 品牌 ", "品牌", "运营"],
        "expected_updated_at": store.get_content(content_id)["updated_at"],
        **changes,
    }


def test_edit_preserves_relationships_and_status(client, store):
    content_id = draft(store)
    store.update_content(content_id, status="published")
    event_id = store.save_calendar_event(content_id, "blog", date.today())
    original = store.get_content(content_id)
    publication = store.create_publication(content_id, "blog", "image_post", "completed", "平台标题", "平台正文")
    response = client.put(f"/api/content/{content_id}", json=edit_payload(store, content_id))
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "新标题"
    assert response.json()["content"] == "修改后的正文\n保留换行"
    assert response.json()["tags"] == ["品牌", "运营"]
    assert response.json()["status"] == "published"
    assert response.json()["created_at"] == original["created_at"]
    assert response.json()["updated_at"] != original["updated_at"]
    assert store.get_content(content_id)["version"] == original["version"] + 1
    assert store.get_calendar_events()[0]["event_id"] == event_id
    assert store.get_publication(publication["id"])["body"] == "平台正文"


def test_stale_edit_after_another_save_or_archive_cannot_overwrite(client, store):
    content_id = draft(store)
    payload = edit_payload(store, content_id)
    assert client.put(f"/api/content/{content_id}", json=payload).status_code == 200
    assert client.put(f"/api/content/{content_id}", json={**payload, "content": "过期修改"}).status_code == 409
    assert store.get_content(content_id)["content"] == payload["content"]
    payload = edit_payload(store, content_id, content="归档前编辑")
    store.archive_content(content_id)
    assert client.put(f"/api/content/{content_id}", json=payload).status_code == 409
    assert store.get_content(content_id)["status"] == "archived"


def test_simultaneous_editors_allow_exactly_one_writer(store):
    content_id = draft(store)
    payload = edit_payload(store, content_id)
    barrier = Barrier(2)

    def save(index):
        barrier.wait(timeout=5)
        try:
            result = store.edit_content(content_id, **{**payload, "content": f"editor-{index}"})
            return result["content"]
        except ContentEditConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, range(2)))
    assert results.count("conflict") == 1
    assert store.get_content(content_id)["content"] in results


@pytest.mark.parametrize(
    "changes",
    [
        {"content": " \n\t "},
        {"title": "x" * 501},
        {"content": "x" * 200_001},
        {"tags": [" "]},
        {"tags": ["x" * 51]},
        {"tags": [str(i) for i in range(31)]},
        {"status": "published"},
        {"user_id": "other-owner"},
    ],
)
def test_invalid_edit_does_not_change_the_draft(client, store, changes):
    content_id = draft(store)
    original = store.get_content(content_id)
    response = client.put(f"/api/content/{content_id}", json=edit_payload(store, content_id, **changes))
    assert response.status_code == 422
    assert store.get_content(content_id) == original


def test_edits_require_a_read_token_and_support_empty_tags(client, store):
    content_id = draft(store)
    payload = edit_payload(store, content_id, title="", tags=[])
    token = payload.pop("expected_updated_at")
    assert client.put(f"/api/content/{content_id}", json=payload).status_code == 422
    assert client.put(f"/api/content/{content_id}", json={**payload, "expected_updated_at": None}).status_code == 409
    response = client.put(f"/api/content/{content_id}", json={**payload, "expected_updated_at": token})
    assert response.status_code == 200
    assert response.json()["title"] == ""
    assert response.json()["tags"] == []


def test_restore_explicitly_returns_an_archive_to_draft(client, store):
    content_id = draft(store)
    assert client.post(f"/api/content/{content_id}/restore").status_code == 409
    store.archive_content(content_id)
    original = store.get_content(content_id)
    response = client.post(f"/api/content/{content_id}/restore")
    assert response.status_code == 200
    assert response.json()["status"] == "draft"
    assert response.json()["content"] == original["content"]
    assert client.post(f"/api/content/{content_id}/restore").status_code == 409
    assert client.post("/api/content/99999/restore").status_code == 404
    assert client.put("/api/content/99999", json=edit_payload(store, content_id)).status_code == 404
