"""Business idempotency for publication and memory mutation (P1-02 part B).

Part A covered content create/refine and calendar commit. These are the two
surfaces it left: an external publish, which is not reversible once the platform
accepts it, and the filesystem-backed memory store, which has no transaction of
its own and therefore leans entirely on the durable ledger row.

Every test asserts the real side effect — provider call counts, publication row
counts, file contents — not just the returned payload. A retry that returns the
right value while publishing twice is exactly the failure being guarded.
"""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from src.api.dependencies import get_litellm_client, get_publish_service, get_store
from src.api.main import app
from src.api.services.chat_agent import ChatAgentService
from src.api.services.publish_service import PublishService
from src.models import ContentType, GeneratedContent
from src.storage.file_memory import AGENT, FileMemory, USER
from src.utils.idempotency import (
    SCOPE_MEMORY_MUTATION,
    SCOPE_PUBLICATION_EXECUTE,
    publication_request_id,
    request_key,
)


class RecordingMcpClient:
    """Counts publish calls and captures the request id the platform receives."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def check_login_status(self):
        return {"text": "logged in", "data": {}}

    async def publish_content(self, arguments):
        self.calls.append(("publish_content", arguments))
        return {"text": "Image post published", "data": {"post_id": f"xhs-{len(self.calls)}"}}

    async def publish_with_video(self, arguments):
        self.calls.append(("publish_with_video", arguments))
        return {"text": "Video post published", "data": {"post_id": f"xhs-{len(self.calls)}"}}


class FailingThenOkMcpClient(RecordingMcpClient):
    """Fails the first publish so the retry path can be exercised."""

    def __init__(self):
        super().__init__()
        self.attempts = 0

    async def publish_content(self, arguments):
        self.attempts += 1
        if self.attempts == 1:
            raise RuntimeError("platform timed out")
        return await super().publish_content(arguments)


class FakeLLMClient:
    async def generate_from_prompts(self, **kw):
        return "stub"

    async def generate(self, **kw):
        return "stub"


def _count(store, table="idempotency_records", where=""):
    clause = f" WHERE {where}" if where else ""
    with store.engine.connect() as connection:
        return connection.execute(text(f"SELECT count(*) FROM {table}{clause}")).scalar_one()


def _seed_publication(store, tmp_path, *, title="publish me"):
    content_id = store.save_content(
        GeneratedContent(
            content=f"{title} body",
            title=title,
            tags=["ai"],
            content_type=ContentType.XIAOHONGSHU,
        ),
        style="casual",
    )
    image = tmp_path / f"{title}.jpg"
    image.write_bytes(b"image-bytes")
    store.save_media_asset(
        content_id=content_id,
        media_type="image",
        source_type="upload",
        file_name=image.name,
        file_path=str(image),
        mime_type="image/jpeg",
    )
    return content_id


def _memory_tools(store, file_memory):
    service = ChatAgentService(
        store=store,
        llm=FakeLLMClient(),
        model_factory=lambda *a, **kw: None,
        file_memory=file_memory,
        context_engine=None,
    )
    return {tool.name: tool for tool in service._build_tools("claude", "m", 0.7, 1024)}


@pytest.fixture
def file_memory(tmp_path):
    return FileMemory(tmp_path / "memory", memory_limit=2000, user_limit=2000)


@pytest.fixture
def publish_mcp():
    return RecordingMcpClient()


@pytest.fixture
def client(store, publish_mcp, monkeypatch):
    """Local to this module: `client` in test_api_contract is not a shared fixture."""
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_litellm_client] = lambda: FakeLLMClient()
    app.dependency_overrides[get_publish_service] = lambda: PublishService(
        store=store, mcp_client=publish_mcp
    )
    monkeypatch.setattr(
        "src.jobs.runner.create_publish_service",
        lambda current_store: PublishService(store=current_store, mcp_client=publish_mcp),
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ─── Publication ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_publication_retry_does_not_publish_twice(store, tmp_path):
    """The core non-reversible case: two executions of one publication row."""
    content_id = _seed_publication(store, tmp_path)
    mcp = RecordingMcpClient()
    service = PublishService(store=store, mcp_client=mcp)
    publication = service.create_publication_request(content_id, "image_post")

    first = await service.execute_publication(publication["id"])
    second = await service.execute_publication(publication["id"])

    # One provider call, not two: the platform never saw the retry.
    assert len(mcp.calls) == 1
    assert first["external_post_id"] == second["external_post_id"] == "xhs-1"
    assert _count(store, "platform_publications") == 1
    assert _count(
        store,
        where=f"scope = '{SCOPE_PUBLICATION_EXECUTE}' AND status = 'completed'",
    ) == 1


@pytest.mark.asyncio
async def test_publication_sends_a_stable_request_id_across_retries(store, tmp_path):
    """The token must be derived from the row, not minted per attempt."""
    content_id = _seed_publication(store, tmp_path)
    mcp = FailingThenOkMcpClient()
    service = PublishService(store=store, mcp_client=mcp)
    publication = service.create_publication_request(content_id, "image_post")
    expected = publication_request_id(publication["id"])

    with pytest.raises(RuntimeError):
        await service.execute_publication(publication["id"])
    # A failed attempt releases the key, otherwise a transient error would make
    # the publication permanently unretryable.
    await service.execute_publication(publication["id"])

    assert mcp.attempts == 2
    assert mcp.calls[0][1]["request_id"] == expected
    assert expected == f"pub-{publication['id']}"
    assert _count(store, "platform_publications") == 1


@pytest.mark.asyncio
async def test_two_publications_of_one_content_are_not_deduplicated(store, tmp_path):
    """An intentional repost is a different request and must go through."""
    content_id = _seed_publication(store, tmp_path)
    mcp = RecordingMcpClient()
    service = PublishService(store=store, mcp_client=mcp)

    first = service.create_publication_request(content_id, "image_post")
    second = service.create_publication_request(content_id, "image_post")
    await service.execute_publication(first["id"])
    await service.execute_publication(second["id"])

    assert first["id"] != second["id"]
    assert len(mcp.calls) == 2
    assert _count(store, "platform_publications") == 2


def test_publish_route_replays_the_same_publication_for_one_key(client, store, tmp_path):
    """A retried POST must not mint a second publication row and job."""
    content_id = _seed_publication(store, tmp_path)
    body = {"content_id": content_id, "publish_type": "image_post"}
    headers = {"Idempotency-Key": "publish-req-1"}

    first = client.post("/api/publish/xiaohongshu", json=body, headers=headers)
    second = client.post("/api/publish/xiaohongshu", json=body, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["publication"]["id"] == second.json()["publication"]["id"]
    assert first.json()["job_id"] == second.json()["job_id"]
    assert _count(store, "platform_publications") == 1
    assert _count(store, "jobs") == 1


def test_publish_route_without_a_key_keeps_current_behavior(client, store, tmp_path):
    """No key means the client promised nothing; two POSTs are two requests."""
    content_id = _seed_publication(store, tmp_path)
    body = {"content_id": content_id, "publish_type": "image_post"}

    first = client.post("/api/publish/xiaohongshu", json=body)
    second = client.post("/api/publish/xiaohongshu", json=body)

    assert first.json()["publication"]["id"] != second.json()["publication"]["id"]
    assert _count(store, "platform_publications") == 2
    assert _count(store) == 0


def test_publish_route_rejects_one_key_reused_with_different_arguments(client, store, tmp_path):
    """Silently replaying the first result would discard the second intent."""
    first_content = _seed_publication(store, tmp_path, title="first")
    second_content = _seed_publication(store, tmp_path, title="second")
    headers = {"Idempotency-Key": "publish-req-2"}

    ok = client.post(
        "/api/publish/xiaohongshu",
        json={"content_id": first_content, "publish_type": "image_post"},
        headers=headers,
    )
    conflict = client.post(
        "/api/publish/xiaohongshu",
        json={"content_id": second_content, "publish_type": "image_post"},
        headers=headers,
    )

    assert ok.status_code == 202
    assert conflict.status_code == 422
    assert "different arguments" in conflict.json()["detail"]
    assert _count(store, "platform_publications") == 1


# ─── Memory mutation ───────────────────────────────────────────────────────


def test_memory_add_applies_once_for_one_capability(store, file_memory):
    """The retry must not append a second copy of the same entry."""
    tools = _memory_tools(store, file_memory)

    with request_key("mem-action-1"):
        first = json.loads(tools["memory_add"].invoke({"target": "user", "text": "偏好简洁"}))
        second = json.loads(tools["memory_add"].invoke({"target": "user", "text": "偏好简洁"}))

    assert first["saved"] is True and second["saved"] is True
    assert file_memory.load(USER).count("偏好简洁") == 1
    assert first["char_count"] == second["char_count"]
    assert _count(store, where=f"scope = '{SCOPE_MEMORY_MUTATION}'") == 1


def test_concurrent_same_key_memory_add_applies_once(store, file_memory):
    """Two threads racing on one capability produce one entry, not two."""
    tools = _memory_tools(store, file_memory)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def attempt():
        barrier.wait()
        with request_key("mem-action-race"):
            try:
                outcomes.append(tools["memory_add"].invoke({"target": "agent", "text": "并发条目"}))
            except Exception as exc:  # DuplicateRequestInFlight is a valid loss
                outcomes.append(type(exc).__name__)

    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in [pool.submit(attempt), pool.submit(attempt)]:
            future.result()

    assert file_memory.load(AGENT).count("并发条目") == 1
    assert _count(store, where=f"scope = '{SCOPE_MEMORY_MUTATION}'") == 1


def test_memory_replace_and_remove_apply_once(store, file_memory):
    tools = _memory_tools(store, file_memory)
    file_memory.add(USER, "旧偏好")

    with request_key("mem-replace-1"):
        first = json.loads(
            tools["memory_replace"].invoke(
                {"target": "user", "old_text": "旧偏好", "new_text": "新偏好"}
            )
        )
        # A replay whose old_text no longer exists would normally raise
        # MemoryNotFound; the ledger short-circuits before FileMemory is touched.
        second = json.loads(
            tools["memory_replace"].invoke(
                {"target": "user", "old_text": "旧偏好", "new_text": "新偏好"}
            )
        )

    assert first["replaced"] is True and second["replaced"] is True
    assert file_memory.load(USER).count("新偏好") == 1

    with request_key("mem-remove-1"):
        removed = json.loads(tools["memory_remove"].invoke({"target": "user", "old_text": "新偏好"}))
        replayed = json.loads(tools["memory_remove"].invoke({"target": "user", "old_text": "新偏好"}))

    assert removed["removed"] is True and replayed["removed"] is True
    assert "新偏好" not in file_memory.load(USER)


def test_different_memory_mutations_are_not_deduplicated(store, file_memory):
    """Distinct capabilities are distinct requests, even on the same target."""
    tools = _memory_tools(store, file_memory)

    with request_key("mem-a"):
        tools["memory_add"].invoke({"target": "user", "text": "条目 A"})
    with request_key("mem-b"):
        tools["memory_add"].invoke({"target": "user", "text": "条目 B"})

    content = file_memory.load(USER)
    assert "条目 A" in content and "条目 B" in content
    assert _count(store, where=f"scope = '{SCOPE_MEMORY_MUTATION}'") == 2


def test_memory_mutation_without_a_key_is_unchanged(store, file_memory):
    """Direct calls outside a chat turn keep Phase 0 behavior and write no row."""
    tools = _memory_tools(store, file_memory)

    tools["memory_add"].invoke({"target": "user", "text": "无键条目"})
    tools["memory_add"].invoke({"target": "user", "text": "无键条目"})

    assert file_memory.load(USER).count("无键条目") == 2
    assert _count(store, where=f"scope = '{SCOPE_MEMORY_MUTATION}'") == 0


def test_memory_and_publication_may_share_a_key_without_cross_deduplication(store, file_memory):
    """Scope is part of the unique key, so one value serves both families."""
    tools = _memory_tools(store, file_memory)

    store.claim_idempotency_key(
        scope=SCOPE_PUBLICATION_EXECUTE,
        key="shared-b",
        args={"publication_id": 1},
    )
    with request_key("shared-b"):
        result = json.loads(tools["memory_add"].invoke({"target": "user", "text": "共享键条目"}))

    assert result["saved"] is True
    assert "共享键条目" in file_memory.load(USER)
    assert _count(store, where="idempotency_key = 'shared-b'") == 2


def test_failed_memory_mutation_leaves_the_key_retryable(store, file_memory):
    """A rejected mutation must not burn the capability permanently."""
    tools = _memory_tools(store, file_memory)

    with request_key("mem-retry"):
        rejected = json.loads(
            tools["memory_replace"].invoke(
                {"target": "user", "old_text": "不存在的文本", "new_text": "x"}
            )
        )
        assert rejected["replaced"] is False
        recovered = json.loads(tools["memory_add"].invoke({"target": "user", "text": "重试后的条目"}))

    assert recovered["saved"] is True
    assert "重试后的条目" in file_memory.load(USER)
