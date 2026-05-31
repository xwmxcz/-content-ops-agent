"""Tests for SQLite FTS5 trigram search over agent_messages."""
from __future__ import annotations

import pytest

from src.storage import ContentStore


@pytest.fixture
def store():
    s = ContentStore(database_url="sqlite:///:memory:")
    s.upsert_agent_thread("t1", title="ops", provider="claude", model="m")
    s.upsert_agent_thread("t2", title="weibo", provider="claude", model="m")
    s.save_agent_message(thread_id="t1", role="user", content="今天写一篇关于小红书的笔记", provider="claude", model="m")
    s.save_agent_message(thread_id="t1", role="assistant", content="好的我们来写小红书种草文案", provider="claude", model="m")
    s.save_agent_message(thread_id="t1", role="user", content="换个话题聊聊微博", provider="claude", model="m")
    s.save_agent_message(thread_id="t2", role="user", content="微博的标题怎么写", provider="claude", model="m")
    return s


class TestSessionSearch:
    def test_three_char_chinese_uses_fts(self, store):
        rows = store.search_agent_messages("小红书")
        assert len(rows) == 2
        contents = [r["content"] for r in rows]
        assert any("种草" in c for c in contents)

    def test_two_char_chinese_falls_back_to_ilike(self, store):
        rows = store.search_agent_messages("微博")
        assert len(rows) == 2  # one per thread

    def test_thread_filter(self, store):
        rows_all = store.search_agent_messages("微博")
        rows_t1 = store.search_agent_messages("微博", thread_id="t1")
        rows_t2 = store.search_agent_messages("微博", thread_id="t2")
        assert len(rows_all) == 2
        assert len(rows_t1) == 1 and rows_t1[0]["thread_id"] == "t1"
        assert len(rows_t2) == 1 and rows_t2[0]["thread_id"] == "t2"

    def test_empty_query_returns_nothing(self, store):
        assert store.search_agent_messages("") == []
        assert store.search_agent_messages("   ") == []

    def test_no_match_returns_empty(self, store):
        assert store.search_agent_messages("天气预报") == []

    def test_fts5_stays_in_sync_on_insert(self, store):
        store.save_agent_message(thread_id="t1", role="user", content="再补充一条小红书技巧", provider="claude", model="m")
        rows = store.search_agent_messages("小红书")
        assert len(rows) == 3

    def test_fts5_stays_in_sync_on_thread_delete(self, store):
        store.delete_agent_thread("t1")
        rows = store.search_agent_messages("小红书")
        assert rows == []
