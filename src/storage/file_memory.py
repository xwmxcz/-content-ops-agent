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
"""
from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any


AGENT = "agent"
USER = "user"
_VALID_TARGETS = {AGENT, USER}

_SECTION = "§"


class MemoryLimitExceeded(ValueError):
    """Raised when an operation would push a memory file past its char limit."""


class MemoryNotFound(ValueError):
    """Raised when `old_text` is not present in the targeted memory file."""


class MemoryAmbiguous(ValueError):
    """Raised when `old_text` matches more than one location in the file."""


class FileMemory:
    """Thread-safe reader/writer for MEMORY.md and USER.md."""

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

    def load(self, target: str) -> str:
        path = self._path_for(target)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def save(self, target: str, content: str) -> None:
        limit = self.limit_for(target)
        if len(content) > limit:
            raise MemoryLimitExceeded(
                f"{target} memory has {len(content)} chars, limit is {limit}"
            )
        path = self._path_for(target)
        with self._lock:
            path.write_text(content, encoding="utf-8")

    def add(self, target: str, text: str) -> None:
        entry = text.strip()
        if not entry:
            raise ValueError("Cannot add an empty memory entry")
        current = self.load(target).rstrip()
        if current:
            new = f"{current}\n{_SECTION}\n{entry}\n"
        else:
            new = f"{entry}\n"
        self.save(target, new)

    def replace(self, target: str, old_text: str, new_text: str) -> None:
        current = self.load(target)
        occurrences = current.count(old_text)
        if occurrences == 0:
            raise MemoryNotFound(f"old_text not found in {target} memory")
        if occurrences > 1:
            raise MemoryAmbiguous(
                f"old_text matches {occurrences} locations in {target} memory; "
                "make it more specific so it is unique"
            )
        self.save(target, current.replace(old_text, new_text))

    def remove(self, target: str, old_text: str) -> None:
        current = self.load(target)
        occurrences = current.count(old_text)
        if occurrences == 0:
            raise MemoryNotFound(f"old_text not found in {target} memory")
        if occurrences > 1:
            raise MemoryAmbiguous(
                f"old_text matches {occurrences} locations in {target} memory; "
                "make it more specific so it is unique"
            )
        new = current.replace(old_text, "")
        # Collapse leftover delimiter pairs / extra blank lines after removal.
        new = re.sub(rf"(?m)^{re.escape(_SECTION)}\s*\n{re.escape(_SECTION)}\s*\n", f"{_SECTION}\n", new)
        new = re.sub(rf"(?m)^{re.escape(_SECTION)}\s*\n", "", new, count=1) if new.startswith(f"{_SECTION}\n") else new
        new = re.sub(rf"\n{re.escape(_SECTION)}\s*\Z", "", new)
        new = re.sub(r"\n{3,}", "\n\n", new)
        self.save(target, new)

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

    def limit_for(self, target: str) -> int:
        self._validate_target(target)
        return self.memory_limit if target == AGENT else self.user_limit

    # ─── Internals ─────────────────────────────────────────────────────────

    def _path_for(self, target: str) -> Path:
        self._validate_target(target)
        return self.memory_path if target == AGENT else self.user_path

    @staticmethod
    def _validate_target(target: str) -> None:
        if target not in _VALID_TARGETS:
            raise ValueError(
                f"Unknown memory target: {target!r}. Must be one of {sorted(_VALID_TARGETS)}"
            )
