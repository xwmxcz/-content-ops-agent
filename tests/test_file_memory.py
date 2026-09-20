"""Tests for the file-based memory backend (MEMORY.md / USER.md)."""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

import pytest

from src.storage.file_memory import (
    AGENT,
    USER,
    FileMemory,
    MemoryAmbiguous,
    MemoryLimitExceeded,
    MemoryLockTimeout,
    MemoryNotFound,
)

ROOT = Path(__file__).resolve().parents[1]


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


def _entries(fm: FileMemory) -> list[str]:
    return [entry.strip() for entry in fm.load(AGENT).split("§")]


_ADD_ENTRIES_SCRIPT = """
import sys
from src.storage.file_memory import AGENT, FileMemory

memory_dir, writer, count = sys.argv[1], sys.argv[2], int(sys.argv[3])
fm = FileMemory(memory_dir, memory_limit=100_000)
for index in range(count):
    fm.add(AGENT, f"{writer}-{index}")
"""


class TestFileMemoryConcurrency:
    """The API's gunicorn processes and the RQ worker share one memory volume."""

    def test_concurrent_adds_across_processes_lose_no_entry(self, tmp_path):
        memory_dir = tmp_path / "memory"
        writers, per_writer = 4, 15
        processes = [
            subprocess.Popen(
                [sys.executable, "-c", _ADD_ENTRIES_SCRIPT, str(memory_dir), f"w{writer}", str(per_writer)],
                cwd=ROOT,
                stderr=subprocess.PIPE,
                text=True,
            )
            for writer in range(writers)
        ]
        for process in processes:
            _, stderr = process.communicate(timeout=120)
            assert process.returncode == 0, stderr

        entries = _entries(FileMemory(memory_dir, memory_limit=100_000))
        expected = {f"w{writer}-{index}" for writer in range(writers) for index in range(per_writer)}
        assert sorted(entries) == sorted(expected)

    def test_concurrent_adds_across_instances_lose_no_entry(self, tmp_path):
        # One FileMemory is built per request, so an instance-level lock alone
        # never serialized two requests for the same user.
        memory_dir = tmp_path / "memory"
        writers, per_writer = 6, 10
        start = threading.Barrier(writers)
        errors: list[BaseException] = []

        def write(writer: int) -> None:
            fm = FileMemory(memory_dir, memory_limit=100_000)
            try:
                start.wait(timeout=30)
                for index in range(per_writer):
                    fm.add(AGENT, f"w{writer}-{index}")
            except BaseException as exc:  # noqa: BLE001 -- reported by the assertion below
                errors.append(exc)

        threads = [threading.Thread(target=write, args=(writer,)) for writer in range(writers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=120)

        assert errors == []
        assert len(_entries(FileMemory(memory_dir, memory_limit=100_000))) == writers * per_writer

    def test_failed_write_keeps_the_previous_file_and_leaves_no_temp_file(self, fm, monkeypatch):
        fm.save(AGENT, "original")

        def fail(src, dst):
            raise OSError("disk full")

        monkeypatch.setattr("src.storage.file_memory.os.replace", fail)
        with pytest.raises(OSError, match="disk full"):
            fm.add(AGENT, "new entry")

        assert fm.load(AGENT) == "original"
        assert sorted(path.name for path in fm.dir.iterdir()) == [".lock", "MEMORY.md"]

    def test_lock_is_released_after_a_rejected_write(self, fm):
        with pytest.raises(MemoryLimitExceeded):
            fm.add(AGENT, "x" * 500)

        fm.add(AGENT, "still writable")
        assert fm.load(AGENT).strip() == "still writable"

    def test_writer_gives_up_instead_of_hanging_on_a_stuck_lock(self, fm, monkeypatch):
        monkeypatch.setattr("src.storage.file_memory._LOCK_TIMEOUT_SECONDS", 0.2)
        other = FileMemory(fm.dir, memory_limit=200, user_limit=100)

        with fm._exclusive():
            with pytest.raises(MemoryLockTimeout):
                other.add(AGENT, "blocked")

        other.add(AGENT, "unblocked")
        assert other.load(AGENT).strip() == "unblocked"
