"""Tests for the file-based memory backend (MEMORY.md / USER.md)."""
from __future__ import annotations

import pytest

from src.storage.file_memory import (
    AGENT,
    USER,
    FileMemory,
    MemoryAmbiguous,
    MemoryLimitExceeded,
    MemoryNotFound,
)


@pytest.fixture
def fm(tmp_path):
    return FileMemory(tmp_path / "memory", memory_limit=200, user_limit=100)


class TestFileMemoryCRUD:
    def test_empty_files_when_missing(self, fm):
        assert fm.load(AGENT) == ""
        assert fm.load(USER) == ""
        assert fm.stats(AGENT) == {"content": "", "char_count": 0, "char_limit": 200}

    def test_add_writes_to_file(self, fm):
        fm.add(AGENT, "first entry")
        assert fm.load(AGENT).strip() == "first entry"

    def test_add_separates_entries_with_section(self, fm):
        fm.add(AGENT, "one")
        fm.add(AGENT, "two")
        assert fm.load(AGENT) == "one\n§\ntwo\n"

    def test_add_rejects_blank(self, fm):
        with pytest.raises(ValueError):
            fm.add(AGENT, "   \n  ")

    def test_save_enforces_char_limit(self, fm):
        with pytest.raises(MemoryLimitExceeded):
            fm.save(AGENT, "x" * 201)

    def test_replace_substitutes_unique_match(self, fm):
        fm.add(AGENT, "用户偏好简洁")
        fm.replace(AGENT, "简洁", "口语化")
        assert "用户偏好口语化" in fm.load(AGENT)

    def test_replace_rejects_ambiguous_match(self, fm):
        fm.add(AGENT, "用户喜欢 A 用户喜欢 B")
        with pytest.raises(MemoryAmbiguous):
            fm.replace(AGENT, "用户", "X")

    def test_replace_raises_when_missing(self, fm):
        fm.add(AGENT, "anything")
        with pytest.raises(MemoryNotFound):
            fm.replace(AGENT, "nope", "x")

    def test_remove_drops_unique_entry(self, fm):
        fm.add(AGENT, "keep this")
        fm.add(AGENT, "drop this")
        fm.remove(AGENT, "drop this")
        body = fm.load(AGENT)
        assert "keep this" in body
        assert "drop this" not in body

    def test_remove_rejects_ambiguous(self, fm):
        fm.add(AGENT, "abc abc")
        with pytest.raises(MemoryAmbiguous):
            fm.remove(AGENT, "abc")

    def test_remove_missing_raises(self, fm):
        with pytest.raises(MemoryNotFound):
            fm.remove(AGENT, "x")

    def test_snapshot_returns_both_files(self, fm):
        fm.save(AGENT, "AGENT_NOTE")
        fm.save(USER, "USER_PROFILE")
        snap = fm.snapshot()
        assert snap == {"memory": "AGENT_NOTE", "user": "USER_PROFILE"}

    def test_invalid_target_raises(self, fm):
        with pytest.raises(ValueError):
            fm.load("nope")
        with pytest.raises(ValueError):
            fm.save("nope", "x")

    def test_separate_limits_per_target(self, fm):
        # user_limit=100 in fixture
        fm.save(USER, "u" * 100)
        with pytest.raises(MemoryLimitExceeded):
            fm.save(USER, "u" * 101)
