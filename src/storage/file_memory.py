"""Hermes-style file-based memory for the chat Agent.

Two flat markdown files persisted under the configured memory directory:

  MEMORY.md  — the Agent's own notes (project conventions, tool quirks, brand
               vocabulary). Hard char limit MEMORY_MD_LIMIT.
  USER.md    — the user profile (name, language, style preferences). Hard char
               limit USER_MD_LIMIT.

Both files are injected wholesale into the system prompt at session start and
then frozen for the rest of the session so Anthropic prompt caching stays warm.
Within a file, entries are separated by a line containing just `§`. The
delimiter lets a single entry span multiple lines while still allowing
substring-based `replace`/`remove` operations.

The API runs several gunicorn processes next to an RQ worker, all sharing one
memory volume, so writers are serialized with an OS file lock rather than an
in-process one, and every write lands through an atomic rename: a reader sees
the old file or the new file, never a truncated one.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

AGENT = "agent"
USER = "user"
_VALID_TARGETS = {AGENT, USER}

_SECTION = "§"

_LOCK_FILE = ".lock"
_EPOCH_FILE = ".snapshot_epoch"
_LOCK_TIMEOUT_SECONDS = 10.0
_LOCK_POLL_SECONDS = 0.02
_REPLACE_ATTEMPTS = 10

if sys.platform == "win32":
    import msvcrt

    def _try_lock(fd: int) -> bool:
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    def _unlock(fd: int) -> None:
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        return True

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


class MemoryLimitExceeded(ValueError):
    """Raised when an operation would push a memory file past its char limit."""


class MemoryNotFound(ValueError):
    """Raised when `old_text` is not present in the targeted memory file."""


class MemoryAmbiguous(ValueError):
    """Raised when `old_text` matches more than one location in the file."""


class MemoryLockTimeout(TimeoutError):
    """Raised when another writer held the memory directory lock for too long."""


class MemoryEditConflict(ValueError):
    """Raised when a memory file changed after the editor loaded it."""


class FileMemory:
    """Process-safe reader/writer for MEMORY.md and USER.md."""

    def __init__(
        self,
        dir: str | Path,
        memory_limit: int = 2200,
        user_limit: int = 1375,
    ) -> None:
        self.dir = Path(dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.memory_path = self.dir / "MEMORY.md"
        self.user_path = self.dir / "USER.md"
        self.memory_limit = memory_limit
        self.user_limit = user_limit
        self._lock = threading.Lock()

    # ─── Public API ────────────────────────────────────────────────────────

    @staticmethod
    def compute_etag(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def etag(self, target: str) -> str:
        return self.compute_etag(self.load(target))

    def load(self, target: str) -> str:
        path = self._path_for(target)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def save(self, target: str, content: str, *, expected_etag: str | None = None) -> None:
        self._check_limit(target, content)
        with self._exclusive():
            if expected_etag is not None:
                current_etag = self.compute_etag(self.load(target))
                if current_etag != expected_etag:
                    raise MemoryEditConflict("记忆文件已被其他页面或助手更新，请重新加载后再保存。当前编辑内容仍保留。")
            self._write(target, content)

    # add/replace/remove read the file and write back a derived value, so the
    # lock has to span the read as well: taken around the write alone, two
    # concurrent adds both start from the same content and one entry is lost.

    def add(self, target: str, text: str) -> None:
        entry = text.strip()
        if not entry:
            raise ValueError("Cannot add an empty memory entry")
        with self._exclusive():
            current = self.load(target).rstrip()
            if current:
                new = f"{current}\n{_SECTION}\n{entry}\n"
            else:
                new = f"{entry}\n"
            self._check_limit(target, new)
            self._write(target, new)

    def replace(self, target: str, old_text: str, new_text: str) -> None:
        with self._exclusive():
            current = self.load(target)
            self._require_unique(target, current, old_text)
            new = current.replace(old_text, new_text)
            self._check_limit(target, new)
            self._write(target, new)

    def remove(self, target: str, old_text: str) -> None:
        with self._exclusive():
            current = self.load(target)
            self._require_unique(target, current, old_text)
            new = current.replace(old_text, "")
            # Collapse leftover delimiter pairs / extra blank lines after removal.
            new = re.sub(rf"(?m)^{re.escape(_SECTION)}\s*\n{re.escape(_SECTION)}\s*\n", f"{_SECTION}\n", new)
            new = (
                re.sub(rf"(?m)^{re.escape(_SECTION)}\s*\n", "", new, count=1)
                if new.startswith(f"{_SECTION}\n")
                else new
            )
            new = re.sub(rf"\n{re.escape(_SECTION)}\s*\Z", "", new)
            new = re.sub(r"\n{3,}", "\n\n", new)
            self._check_limit(target, new)
            self._write(target, new)

    def stats(self, target: str) -> dict[str, Any]:
        content = self.load(target)
        return {
            "content": content,
            "char_count": len(content),
            "char_limit": self.limit_for(target),
        }

    def snapshot(self) -> dict[str, str]:
        """Return the current contents of both files — for system prompt injection."""
        return {
            "memory": self.load(AGENT),
            "user": self.load(USER),
        }

    def bump_snapshot_epoch(self, thread_id: str | None = None) -> int:
        """Record an explicit snapshot refresh so all Gunicorn workers drop stale frozen prompts."""
        epoch_path = self.dir / _EPOCH_FILE
        with self._exclusive():
            data = self._read_epoch_data(epoch_path)
            raw_threads = data.get("threads")
            threads: dict[str, int] = (
                {str(k): int(v) for k, v in raw_threads.items() if isinstance(v, int)}
                if isinstance(raw_threads, dict)
                else {}
            )
            highest = max([int(data.get("all") or 0), *threads.values()])
            next_epoch = max(highest + 1, time.time_ns())
            if thread_id is None:
                payload = {"all": next_epoch, "threads": {}}
            else:
                threads[thread_id] = next_epoch
                payload = {"all": int(data.get("all") or 0), "threads": threads}
            self._write_path(epoch_path, json.dumps(payload, ensure_ascii=False))
            return next_epoch

    def snapshot_epoch(self, thread_id: str | None = None) -> int:
        """Return the latest explicit refresh epoch affecting ``thread_id``."""
        data = self._read_epoch_data(self.dir / _EPOCH_FILE)
        global_epoch = int(data.get("all") or 0)
        if not thread_id:
            return global_epoch
        threads = data.get("threads")
        thread_epoch = int(threads.get(thread_id) or 0) if isinstance(threads, dict) else 0
        return max(global_epoch, thread_epoch)

    @staticmethod
    def _read_epoch_data(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
            return parsed if isinstance(parsed, dict) else {}
        except (OSError, ValueError):
            return {}

    def limit_for(self, target: str) -> int:
        self._validate_target(target)
        return self.memory_limit if target == AGENT else self.user_limit

    # ─── Internals ─────────────────────────────────────────────────────────

    @contextmanager
    def _exclusive(self) -> Iterator[None]:
        """Hold the directory's writer lock across threads and processes."""
        with self._lock:
            fd = os.open(self.dir / _LOCK_FILE, os.O_RDWR | os.O_CREAT, 0o600)
            try:
                deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
                while not _try_lock(fd):
                    if time.monotonic() >= deadline:
                        raise MemoryLockTimeout(f"Memory directory {self.dir} stayed locked by another writer")
                    time.sleep(_LOCK_POLL_SECONDS)
                try:
                    yield
                finally:
                    _unlock(fd)
            finally:
                os.close(fd)

    def _write(self, target: str, content: str) -> None:
        """Replace the file in one step. The caller holds the writer lock."""
        self._write_path(self._path_for(target), content)

    def _write_path(self, path: Path, content: str) -> None:
        fd, tmp_name = tempfile.mkstemp(dir=self.dir, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            self._replace(tmp_name, path)
        except BaseException:
            with suppress(OSError):
                os.unlink(tmp_name)
            raise

    @staticmethod
    def _replace(tmp_name: str, path: Path) -> None:
        # Windows refuses to replace a file that a concurrent load() has open;
        # the reader is done within milliseconds, so a short retry covers it.
        attempts = _REPLACE_ATTEMPTS if sys.platform == "win32" else 1
        for attempt in range(attempts):
            try:
                os.replace(tmp_name, path)
                return
            except PermissionError:
                if attempt == attempts - 1:
                    raise
                time.sleep(_LOCK_POLL_SECONDS)

    def _check_limit(self, target: str, content: str) -> None:
        limit = self.limit_for(target)
        if len(content) > limit:
            raise MemoryLimitExceeded(f"{target} memory has {len(content)} chars, limit is {limit}")

    @staticmethod
    def _require_unique(target: str, current: str, old_text: str) -> None:
        occurrences = current.count(old_text)
        if occurrences == 0:
            raise MemoryNotFound(f"old_text not found in {target} memory")
        if occurrences > 1:
            raise MemoryAmbiguous(
                f"old_text matches {occurrences} locations in {target} memory; make it more specific so it is unique"
            )

    def _path_for(self, target: str) -> Path:
        self._validate_target(target)
        return self.memory_path if target == AGENT else self.user_path

    @staticmethod
    def _validate_target(target: str) -> None:
        if target not in _VALID_TARGETS:
            raise ValueError(f"Unknown memory target: {target!r}. Must be one of {sorted(_VALID_TARGETS)}")
