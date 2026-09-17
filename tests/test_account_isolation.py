"""Real-session HTTP and worker regression tests for independent workspaces."""
from datetime import date

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from src.api.dependencies import (
    _file_memory_for,
    get_chat_agent_service,
    get_file_memory,
    get_litellm_client,
    get_store,
    get_system_store,
)
from src.api.main import app
from src.api.schemas.agent import ChatIntent
from src.api.services.chat_agent import ChatAgentService
from src.llm.litellm_client import LiteLLMClient
from src.models import ContentType, GeneratedContent
from src.utils import config

pytestmark = pytest.mark.real_auth


class FakeLLM:
    async def generate_from_prompts(self, **kwargs):
        return "【标题】\nTest draft\n【正文】\nPrivate generated content"


class ClarificationOnly:
    async def recognize(self, **kwargs):
        return ChatIntent(name="clarify", confidence=1.0, clarification="Private test reply")


@pytest.fixture
def accounts(store, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEMORY_ENABLED", True)
    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path / "memory"))
    monkeypatch.setattr(config, "MEDIA_STORAGE_ROOT", str(tmp_path / "media"))

    async def forbid_provider(*args, **kwargs):
        raise AssertionError("This test must not contact an LLM provider")
    monkeypatch.setattr(LiteLLMClient, "generate", forbid_provider)

    def chat_service(owned=Depends(get_store), memory=Depends(get_file_memory)):
        return ChatAgentService(store=owned, llm=FakeLLM(), file_memory=memory,
                                intent_recognizer=ClarificationOnly())

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_litellm_client] = FakeLLM
    app.dependency_overrides[get_chat_agent_service] = chat_service
    sessions = []
    try:
        with TestClient(app) as first, TestClient(app) as second:
            for client, username in ((first, "owner_first"), (second, "owner_second")):
                response = client.post("/api/auth/register", json={"username": username, "password": "Local-test-password-28!"})
                assert response.status_code == 201, response.text
                session = response.json()
                client.headers["Authorization"] = f"Bearer {session['access_token']}"
                sessions.append(session)
            system = get_system_store()
            yield (first, second, system.for_user(sessions[0]["user"]["id"]),
                   system.for_user(sessions[1]["user"]["id"]))
    finally:
        for session in sessions:
            ChatAgentService.invalidate_frozen(user_id=session["user"]["id"])
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def create_content(client):
    response = client.post("/api/content/generate", json={"topic": "Private topic", "content_type": "blog"},
                           headers={"Idempotency-Key": "same-key-for-both-users"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_content_crud_calendar_stats_and_idempotency_are_private(accounts):
    first, second, _, _ = accounts
    first_id, second_id = create_content(first), create_content(second)
    assert first_id != second_id
    assert create_content(first) == first_id
    assert [item["id"] for item in first.get("/api/content").json()] == [first_id]
    assert [item["id"] for item in second.get("/api/content").json()] == [second_id]
    assert first.get("/api/stats").json()["total_contents"] == 1
    assert second.get("/api/stats").json()["total_contents"] == 1
    assert first.get(f"/api/content/{first_id}").status_code == 200
    assert second.get(f"/api/content/{first_id}").status_code == 404
    assert second.post(f"/api/content/{first_id}/archive").status_code == 404
    assert second.delete(f"/api/content/{first_id}").status_code == 404
    assert second.post("/api/content/refine", json={"content_id": first_id, "instruction": "cross-user"}).status_code == 404
    event = {"content_id": first_id, "platform": "blog", "scheduled_date": date.today().isoformat()}
    assert first.post("/api/calendar/events", json=event).status_code == 201
    assert second.post("/api/calendar/events", json=event).status_code == 404
    assert second.get("/api/calendar/events").json() == []
    assert first.post(f"/api/content/{first_id}/archive").status_code == 200
    assert first.get(f"/api/content/{first_id}").json()["status"] == "archived"
    assert first.delete(f"/api/content/{first_id}").status_code == 200
    assert second.get(f"/api/content/{second_id}").status_code == 200


def test_chat_history_search_rename_delete_and_send_reject_foreign_threads(accounts):
    first, second, _, _ = accounts
    response = first.post("/api/agent/chat", json={"message": "private transcript marker"})
    assert response.status_code == 200, response.text
    thread_id = response.json()["thread_id"]
    assert first.get(f"/api/agent/threads/{thread_id}/messages").status_code == 200
    assert second.get("/api/agent/threads").json() == []
    assert second.get(f"/api/agent/threads/{thread_id}/messages").status_code == 404
    assert second.get("/api/agent/threads/search", params={"q": "private transcript"}).json() == []
    assert second.post("/api/memory/search", json={"q": "private transcript"}).json() == {"messages": [], "count": 0}
    assert second.patch(f"/api/agent/threads/{thread_id}", json={"title": "forged"}).status_code == 404
    assert second.delete(f"/api/agent/threads/{thread_id}").status_code == 404
    assert second.post("/api/agent/chat", json={"thread_id": thread_id, "message": "foreign"}).status_code == 404
    own = first.get(f"/api/agent/threads/{thread_id}/messages").json()
    assert [message["content"] for message in own] == ["private transcript marker", "Private test reply"]


def test_jobs_runs_sse_and_resource_ticket_issuance_are_private(accounts):
    first, second, owned, _ = accounts
    owned.create_job("job_private", "content_generation", {"private": True})
    owned.create_run("run_private", "private", "blog", "casual")
    owned.transition_run_and_append_event("run_private", expected_statuses={"running"},
                                         new_status="completed", event_type="run_complete", payload={"private": "marker"})
    assert first.get("/api/jobs/job_private").status_code == 200
    assert second.get("/api/jobs/job_private").status_code == 404
    assert second.delete("/api/jobs/job_private").status_code == 404
    assert second.get("/api/agent/runs/run_private").status_code == 404
    assert second.delete("/api/agent/runs/run_private").status_code == 404
    path = "/api/agent/runs/run_private/stream"
    assert second.get(path, headers={"Authorization": ""}).status_code == 404
    stream = first.get(path, headers={"Authorization": ""})
    assert stream.status_code == 200 and '"private": "marker"' in stream.text
    assert second.post("/api/auth/resource-ticket", json={"path": path}).status_code == 404
    assert first.post("/api/auth/resource-ticket", json={"path": path}).status_code == 200


def test_media_upload_listing_file_cookie_and_deletion_are_private(accounts):
    first, second, _, _ = accounts
    content_id = create_content(first)
    payload = b"\x89PNG\r\n\x1a\nprivate-media"
    response = first.post("/api/media/upload", data={"content_id": content_id, "media_type": "image"},
                          files={"file": ("private.png", payload, "image/png")})
    assert response.status_code == 201, response.text
    media = response.json()
    assert len(first.get(f"/api/content/{content_id}/media").json()) == 1
    assert second.get(f"/api/content/{content_id}/media").status_code == 404
    assert second.get(media["file_url"], headers={"Authorization": ""}).status_code == 404
    assert first.get(media["file_url"], headers={"Authorization": ""}).content == payload
    assert second.post("/api/media/upload", data={"content_id": content_id, "media_type": "image"},
                       files={"file": ("foreign.png", payload, "image/png")}).status_code == 404
    assert second.delete(f"/api/media/{media['id']}").status_code == 404
    assert first.get(media["file_url"]).status_code == 200
    assert first.delete(f"/api/media/{media['id']}").status_code == 200


def test_memory_files_frozen_prompts_and_refresh_are_private(accounts):
    first, second, own_first, own_second = accounts
    for path in ("agent", "user"):
        assert first.put(f"/api/memory/{path}", json={"content": f"first-private-{path}"}).status_code == 200
        assert second.get(f"/api/memory/{path}").json()["content"] == ""
        assert second.put(f"/api/memory/{path}", json={"content": f"second-private-{path}"}).status_code == 200
    own_first.upsert_agent_thread("thread_first")
    own_second.upsert_agent_thread("thread_second")
    first_service = ChatAgentService(own_first, file_memory=_file_memory_for(own_first.user_id))
    second_service = ChatAgentService(own_second, file_memory=_file_memory_for(own_second.user_id))
    # Identical cache keys in different workspaces must still get distinct memory.
    first_prompt = first_service._get_frozen_system_prompt("collision")
    second_prompt = second_service._get_frozen_system_prompt("collision")
    assert "first-private-agent" in first_prompt and "second-private-agent" not in first_prompt
    assert "second-private-agent" in second_prompt and "first-private-agent" not in second_prompt
    first_service._get_frozen_system_prompt("thread_first")
    second_service._get_frozen_system_prompt("thread_second")
    first.put("/api/memory/agent", json={"content": "first-updated"})
    second.put("/api/memory/agent", json={"content": "second-updated"})
    assert second.post("/api/memory/refresh-snapshot", json={"thread_id": "thread_first"}).status_code == 404
    assert first.post("/api/memory/refresh-snapshot", json={}).status_code == 200
    assert "first-updated" in first_service._get_frozen_system_prompt("collision")
    assert second_service._get_frozen_system_prompt("collision") == second_prompt
    assert first.get("/api/memory/agent").json()["content"] == "first-updated"


def test_background_worker_uses_persisted_owner_not_forged_payload(accounts, monkeypatch):
    from src.jobs import runner

    first, second, owned, other = accounts
    owned.create_job("job_worker", "content_generation", {"user_id": other.user_id})
    observed = []

    async def execute(job, llm, scoped):
        observed.append(scoped.user_id)
        content_id = scoped.save_content(GeneratedContent(content="worker private result", content_type=ContentType.BLOG))
        return {"content_id": content_id}

    monkeypatch.setattr(runner, "_execute_job", execute)
    monkeypatch.setattr(runner, "create_litellm_client", lambda: object())
    runner.run_job("job_worker", database_url=owned.database_url)
    assert observed == [owned.user_id]
    job = first.get("/api/jobs/job_worker").json()
    assert job["status"] == "completed"
    content_id = job["result"]["content_id"]
    assert first.get(f"/api/content/{content_id}").status_code == 200
    assert second.get(f"/api/content/{content_id}").status_code == 404
    assert second.get("/api/jobs/job_worker").status_code == 404
