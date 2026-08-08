"""Tests for ILIKE substring search over agent_messages."""
from __future__ import annotations

import pytest


@pytest.fixture
def seeded(store):
    store.upsert_agent_thread("t1", title="ops", provider="claude", model="m")
    store.upsert_agent_thread("t2", title="weibo", provider="claude", model="m")
    store.save_agent_message(thread_id="t1", role="user", content="今天写一篇关于小红书的笔记", provider="claude", model="m")
    store.save_agent_message(thread_id="t1", role="assistant", content="好的我们来写小红书种草文案", provider="claude", model="m")
    store.save_agent_message(thread_id="t1", role="user", content="换个话题聊聊微博", provider="claude", model="m")
    store.save_agent_message(thread_id="t2", role="user", content="微博的标题怎么写", provider="claude", model="m")
    return store


class TestSessionSearch:
    def test_matches_all_occurrences(self, seeded):
        rows = seeded.search_agent_messages("小红书")
        assert len(rows) == 2
        contents = [r["content"] for r in rows]
        assert any("种草" in c for c in contents)

    def test_matches_across_threads(self, seeded):
        rows = seeded.search_agent_messages("微博")
        assert len(rows) == 2  # one per thread

    def test_thread_filter(self, seeded):
        rows_all = seeded.search_agent_messages("微博")
        rows_t1 = seeded.search_agent_messages("微博", thread_id="t1")
        rows_t2 = seeded.search_agent_messages("微博", thread_id="t2")
        assert len(rows_all) == 2
        assert len(rows_t1) == 1 and rows_t1[0]["thread_id"] == "t1"
        assert len(rows_t2) == 1 and rows_t2[0]["thread_id"] == "t2"

    def test_empty_query_returns_nothing(self, seeded):
        assert seeded.search_agent_messages("") == []
        assert seeded.search_agent_messages("   ") == []

    def test_no_match_returns_empty(self, seeded):
        assert seeded.search_agent_messages("天气预报") == []

    def test_search_reflects_insert(self, seeded):
        seeded.save_agent_message(thread_id="t1", role="user", content="再补充一条小红书技巧", provider="claude", model="m")
        rows = seeded.search_agent_messages("小红书")
        assert len(rows) == 3

    def test_search_reflects_thread_delete(self, seeded):
        seeded.delete_agent_thread("t1")
        rows = seeded.search_agent_messages("小红书")
        assert rows == []
