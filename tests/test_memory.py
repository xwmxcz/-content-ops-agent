"""Contract tests for the long-term memory system."""
import json
from unittest.mock import patch, MagicMock

import pytest

from src.storage.content_store import ContentStore
from src.storage.memory_vector_store import MemoryVectorStore
from src.utils import config


# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def store():
    return ContentStore(database_url="sqlite:///:memory:")


@pytest.fixture
def fake_embeddings():
    """Deterministic fake embeddings for testing."""
    class FakeEmbeddings:
        def embed_query(self, text: str) -> list[float]:
            val = (sum(ord(c) for c in text) % 100 + 1) / 101.0
            return [val] * 384

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [self.embed_query(t) for t in texts]

    return FakeEmbeddings()


@pytest.fixture
def memory_store(tmp_path, fake_embeddings):
    ms = MemoryVectorStore(persist_dir=str(tmp_path / "chroma"))
    ms._embeddings = fake_embeddings
    return ms


# ─── SQL CRUD Tests ────────────────────────────────────────────────────────────

class TestMemoryCRUD:
    def test_save_and_get(self, store):
        result = store.save_memory("m1", "用户喜欢简洁风格", "preference", importance=0.8)
        assert result["id"] == "m1"
        assert result["content"] == "用户喜欢简洁风格"
        assert result["category"] == "preference"
        assert result["importance"] == 0.8

        fetched = store.get_memory("m1")
        assert fetched is not None
        assert fetched["content"] == "用户喜欢简洁风格"

    def test_get_nonexistent(self, store):
        assert store.get_memory("nope") is None

    def test_upsert(self, store):
        store.save_memory("m1", "old content", "fact")
        store.save_memory("m1", "new content", "preference", importance=0.9)
        fetched = store.get_memory("m1")
        assert fetched["content"] == "new content"
        assert fetched["category"] == "preference"
        assert fetched["importance"] == 0.9

    def test_search_text(self, store):
        store.save_memory("m1", "用户喜欢简洁风格", "preference", importance=0.8)
        store.save_memory("m2", "品牌名是 TechFlow", "fact", importance=0.6)
        store.save_memory("m3", "用户偏好短视频", "preference", importance=0.7)

        results = store.search_memories_text("用户")
        assert len(results) == 2
        assert results[0]["importance"] >= results[1]["importance"]

    def test_search_text_with_category(self, store):
        store.save_memory("m1", "用户喜欢简洁", "preference")
        store.save_memory("m2", "用户的公司叫 ABC", "fact")
        results = store.search_memories_text("用户", category="fact")
        assert len(results) == 1
        assert results[0]["category"] == "fact"

    def test_touch_memory(self, store):
        store.save_memory("m1", "test", "fact")
        store.touch_memory("m1")
        store.touch_memory("m1")
        fetched = store.get_memory("m1")
        assert fetched["access_count"] == 2
        assert fetched["last_used_at"] is not None

    def test_delete_memory(self, store):
        store.save_memory("m1", "test", "fact")
        assert store.delete_memory("m1") is True
        assert store.get_memory("m1") is None
        assert store.delete_memory("m1") is False

    def test_count_and_evict(self, store):
        for i in range(10):
            store.save_memory(f"m{i}", f"memory {i}", "fact", importance=i / 10.0)
        assert store.count_memories() == 10
        evicted = store.evict_memories(5)
        assert evicted == 5
        assert store.count_memories() == 5

    def test_list_memories(self, store):
        store.save_memory("m1", "high", "preference", importance=0.9)
        store.save_memory("m2", "low", "fact", importance=0.1)
        all_mems = store.list_memories()
        assert len(all_mems) == 2
        assert all_mems[0]["importance"] >= all_mems[1]["importance"]


# ─── Vector Store Tests ────────────────────────────────────────────────────────

class TestMemoryVectorStore:
    def test_add_and_query(self, memory_store):
        memory_store.add("m1", "用户喜欢简洁风格", "preference")
        memory_store.add("m2", "品牌名是 TechFlow", "fact")

        results = memory_store.query("简洁", n_results=5, threshold=0.0)
        assert len(results) >= 1
        assert any(r["id"] == "m1" for r in results)

    def test_query_with_category_filter(self, memory_store):
        memory_store.add("m1", "用户喜欢简洁", "preference")
        memory_store.add("m2", "公司叫 ABC", "fact")

        results = memory_store.query("用户", category="preference", n_results=5, threshold=0.0)
        ids = [r["id"] for r in results]
        assert "m1" in ids
        assert "m2" not in ids

    def test_delete(self, memory_store):
        memory_store.add("m1", "test content", "fact")
        memory_store.delete("m1")
        assert memory_store.count() == 0

    def test_count(self, memory_store):
        assert memory_store.count() == 0
        memory_store.add("m1", "a", "fact")
        memory_store.add("m2", "b", "fact")
        assert memory_store.count() == 2

    def test_threshold_filtering(self, memory_store):
        memory_store.add("m1", "completely unrelated topic xyz", "fact")
        results = memory_store.query("completely unrelated topic xyz", threshold=0.99)
        assert len(results) >= 1
        results_strict = memory_store.query("something else entirely", threshold=0.99)
        assert len(results_strict) <= len(results)


# ─── Integration: Chat Agent with Memory ───────────────────────────────────────

class TestChatAgentMemoryIntegration:
    def test_remember_tool(self, store, memory_store):
        from src.api.services.chat_agent import ChatAgentService

        service = ChatAgentService(store=store, memory_store=memory_store)
        tools = service._build_tools("claude", "claude-3-5-sonnet", 0.7, 4096)
        tool_names = [t.name for t in tools]
        assert "remember" in tool_names
        assert "recall" in tool_names

    def test_auto_recall_returns_empty_without_memories(self, store, memory_store):
        from src.api.services.chat_agent import ChatAgentService

        service = ChatAgentService(store=store, memory_store=memory_store)
        result = service._auto_recall("hello")
        assert result == ""

    def test_auto_recall_returns_context_with_memories(self, store, memory_store):
        from src.api.services.chat_agent import ChatAgentService

        store.save_memory("m1", "用户喜欢简洁风格", "preference", importance=0.8)
        memory_store.add("m1", "用户喜欢简洁风格", "preference")

        service = ChatAgentService(store=store, memory_store=memory_store)
        result = service._auto_recall("用户喜欢简洁风格")
        assert "Relevant memories" in result
        assert "简洁" in result

    def test_auto_recall_disabled_when_no_memory_store(self, store):
        from src.api.services.chat_agent import ChatAgentService

        service = ChatAgentService(store=store, memory_store=None)
        result = service._auto_recall("anything")
        assert result == ""
