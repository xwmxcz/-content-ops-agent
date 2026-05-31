"""Tests for the memory curator triggered on thread close."""
from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient

from src.agent.memory_curator import MemoryCurator
from src.api.dependencies import get_file_memory, get_memory_curator, get_store
from src.api.main import app
from src.storage import ContentStore
from src.storage.file_memory import AGENT, FileMemory, USER


class StubAuxLLM:
    def __init__(self, response: str):
        self.response = response
        self.calls = []

    async def generate_from_prompts(self, **kw):
        self.calls.append(kw)
        return self.response


@pytest.fixture
def store():
    return ContentStore(database_url="sqlite:///:memory:")


@pytest.fixture
def file_memory(tmp_path):
    return FileMemory(tmp_path / "memory", memory_limit=2200, user_limit=1375)


@pytest.fixture
def transcript():
    return [
        {"role": "user", "content": "我们品牌叫 TechFlow,主要写 AI 工具教程", "provider": None, "model": None},
        {"role": "assistant", "content": "记下来了,目标受众是开发者", "provider": "claude", "model": "claude-3-5-sonnet"},
        {"role": "user", "content": "我喜欢简洁口语化,别用 emoji", "provider": None, "model": None},
        {"role": "assistant", "content": "好的,以后默认简洁不堆 emoji", "provider": "claude", "model": "claude-3-5-sonnet"},
    ]


# ─── Unit tests ────────────────────────────────────────────────────────────


class TestCuratorParse:
    def test_parses_clean_json_array(self):
        raw = '[{"action":"add","target":"user","text":"喜欢简洁"}]'
        actions = MemoryCurator._parse(raw)
        assert actions == [{"action": "add", "target": "user", "text": "喜欢简洁"}]

    def test_strips_markdown_fence(self):
        raw = '```json\n[{"action":"add","target":"agent","text":"X"}]\n```'
        assert len(MemoryCurator._parse(raw)) == 1

    def test_rejects_invalid_action(self):
        raw = '[{"action":"hack","target":"agent","text":"x"}]'
        assert MemoryCurator._parse(raw) == []

    def test_rejects_invalid_target(self):
        raw = '[{"action":"add","target":"root","text":"x"}]'
        assert MemoryCurator._parse(raw) == []

    def test_returns_empty_on_garbage(self):
        assert MemoryCurator._parse("not json") == []
        assert MemoryCurator._parse("") == []
        assert MemoryCurator._parse('{"oops":1}') == []


@pytest.mark.asyncio
class TestCuratorCurate:
    async def test_skips_short_transcript(self, file_memory):
        c = MemoryCurator(StubAuxLLM("[]"), file_memory, min_messages=4)
        result = await c.curate([{"role": "user", "content": "hi"}])
        assert result["skipped"] is True
        assert result["applied"] == []

    async def test_applies_add_actions(self, file_memory, transcript):
        aux = StubAuxLLM(json.dumps([
            {"action": "add", "target": "user", "text": "偏好简洁口语化,不爱 emoji"},
            {"action": "add", "target": "agent", "text": "品牌 TechFlow,受众开发者"},
        ]))
        c = MemoryCurator(aux, file_memory)
        result = await c.curate(transcript)
        assert len(result["applied"]) == 2
        assert len(result["rejected"]) == 0
        assert "TechFlow" in file_memory.load(AGENT)
        assert "简洁口语化" in file_memory.load(USER)

    async def test_collects_per_item_failures(self, file_memory, transcript):
        # Mix one valid + one invalid (limit exceeded)
        aux = StubAuxLLM(json.dumps([
            {"action": "add", "target": "user", "text": "ok"},
            {"action": "add", "target": "user", "text": "x" * 9999},
        ]))
        c = MemoryCurator(aux, file_memory)
        result = await c.curate(transcript)
        assert len(result["applied"]) == 1
        assert len(result["rejected"]) == 1
        assert "limit" in result["rejected"][0]["error"].lower()

    async def test_replace_action(self, file_memory, transcript):
        file_memory.save(USER, "旧偏好")
        aux = StubAuxLLM(json.dumps([
            {"action": "replace", "target": "user", "old_text": "旧偏好", "new_text": "新偏好"},
        ]))
        c = MemoryCurator(aux, file_memory)
        result = await c.curate(transcript)
        assert len(result["applied"]) == 1
        assert "新偏好" in file_memory.load(USER)

    async def test_remove_action(self, file_memory, transcript):
        file_memory.save(USER, "要删的条目")
        aux = StubAuxLLM(json.dumps([
            {"action": "remove", "target": "user", "old_text": "要删的条目"},
        ]))
        c = MemoryCurator(aux, file_memory)
        result = await c.curate(transcript)
        assert len(result["applied"]) == 1
        assert "要删的条目" not in file_memory.load(USER)

    async def test_aux_llm_failure_is_safe(self, file_memory, transcript):
        class Boom:
            async def generate_from_prompts(self, **kw):
                raise RuntimeError("upstream down")
        c = MemoryCurator(Boom(), file_memory)
        result = await c.curate(transcript)
        assert result["skipped"] is True
        assert "llm error" in result["reason"]

    async def test_caps_actions_to_max(self, file_memory, transcript):
        aux = StubAuxLLM(json.dumps([
            {"action": "add", "target": "user", "text": f"entry {i}"} for i in range(20)
        ]))
        c = MemoryCurator(aux, file_memory, max_actions=3)
        result = await c.curate(transcript)
        assert len(result["applied"]) == 3


# ─── Route integration ────────────────────────────────────────────────────


class TestThreadDeleteTriggersCurator:
    def test_delete_thread_invokes_curator_in_background(self, tmp_path):
        # TestClient runs the route in a worker thread; `:memory:` SQLite would
        # give that thread its own empty in-memory DB. Use a temp file instead
        # so create_all on the fixture thread is visible to the request thread.
        db = tmp_path / "test.db"
        fm = FileMemory(tmp_path / "memory", memory_limit=2200, user_limit=1375)
        store = ContentStore(database_url=f"sqlite:///{db.as_posix()}")
        store.upsert_agent_thread("t1", title="x", provider="claude", model="m")
        for i in range(4):
            store.save_agent_message(
                thread_id="t1",
                role="user" if i % 2 == 0 else "assistant",
                content=f"msg {i}",
                provider="claude",
                model="m",
            )
        aux = StubAuxLLM(json.dumps([
            {"action": "add", "target": "user", "text": "curator-saved-marker"},
        ]))
        curator = MemoryCurator(aux, fm, min_messages=2)

        app.dependency_overrides[get_store] = lambda: store
        app.dependency_overrides[get_file_memory] = lambda: fm
        app.dependency_overrides[get_memory_curator] = lambda: curator
        try:
            with TestClient(app) as client:
                r = client.delete("/api/agent/threads/t1")
                assert r.status_code == 200
                assert r.json() == {"deleted": True}
            # TestClient(client) context-manager flushes BackgroundTasks on exit.
            assert "curator-saved-marker" in fm.load(USER)
            assert len(aux.calls) == 1
        finally:
            app.dependency_overrides.clear()
            store.engine.dispose()

    def test_delete_unknown_thread_does_not_call_curator(self, tmp_path):
        db = tmp_path / "test.db"
        fm = FileMemory(tmp_path / "memory")
        store = ContentStore(database_url=f"sqlite:///{db.as_posix()}")
        aux = StubAuxLLM("[]")
        curator = MemoryCurator(aux, fm)
        app.dependency_overrides[get_store] = lambda: store
        app.dependency_overrides[get_file_memory] = lambda: fm
        app.dependency_overrides[get_memory_curator] = lambda: curator
        try:
            with TestClient(app) as client:
                r = client.delete("/api/agent/threads/nope")
                assert r.status_code == 404
            assert len(aux.calls) == 0
        finally:
            app.dependency_overrides.clear()
            store.engine.dispose()
