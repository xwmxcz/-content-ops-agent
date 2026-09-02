"""Proposal-only memory curator.

If explicitly called by a future user-visible workflow, an auxiliary LLM may
read a transcript plus the current MEMORY.md / USER.md and propose a JSON list
of `add` / `replace` / `remove` operations. Thread deletion never invokes this
component. Curator output is untrusted and is never applied directly; only
user-confirmed Chat memory tools may mutate the files.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.llm.litellm_client import LiteLLMClient
from src.storage.file_memory import AGENT, FileMemory, USER


logger = logging.getLogger(__name__)


CURATOR_SYSTEM_PROMPT = """You are a memory curator for the Content Ops Agent.
Given a finished conversation transcript plus the current MEMORY.md and
USER.md, identify durable facts/preferences worth preserving for FUTURE
sessions.

WHAT TO RECORD
  target='agent' (MEMORY.md): project conventions, brand vocabulary, tool
    quirks, lessons learned, recurring workflows.
  target='user' (USER.md): user name/language/timezone, communication style,
    pet peeves, content preferences.

WHAT TO SKIP
  - One-off requests, transient task state, content drafts (those live
    elsewhere in the system).
  - Anything already covered by a near-identical entry in the current files.

OUTPUT
  Strict JSON array only, no prose, no markdown fence. Each element:
    {"action": "add",     "target": "agent"|"user", "text": "..."}
    {"action": "replace", "target": "agent"|"user", "old_text": "...", "new_text": "..."}
    {"action": "remove",  "target": "agent"|"user", "old_text": "..."}
  Use replace/remove only when old_text appears verbatim in the current file
  AND is unique within that file.

  Empty array [] is a valid answer when nothing is worth saving. Keep entries
  short (≤ 200 chars each) and at most 6 entries total.
"""


_VALID_OPS = {"add", "replace", "remove"}
_VALID_TARGETS = {AGENT, USER}


class MemoryCurator:
    def __init__(
        self,
        aux_llm: LiteLLMClient,
        file_memory: FileMemory,
        *,
        min_messages: int = 4,
        max_actions: int = 6,
    ) -> None:
        self.aux_llm = aux_llm
        self.file_memory = file_memory
        self.min_messages = min_messages
        self.max_actions = max_actions

    async def curate(
        self,
        messages: list[dict[str, Any]],
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        if len(messages) < self.min_messages:
            return {"skipped": True, "reason": "transcript too short", "applied": [], "rejected": []}

        snap = self.file_memory.snapshot()
        user_prompt = (
            f"CONVERSATION:\n{self._render_transcript(messages)}\n\n"
            f"CURRENT MEMORY.md:\n{snap['memory'] or '(empty)'}\n\n"
            f"CURRENT USER.md:\n{snap['user'] or '(empty)'}"
        )
        try:
            raw = await self.aux_llm.generate_from_prompts(
                provider=provider or "claude",
                model=model,
                system_prompt=CURATOR_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.3,
                max_tokens=1024,
            )
        except Exception as exc:
            logger.warning("memory curator: aux LLM failed error_class=%s", exc.__class__.__name__)
            return {"skipped": True, "reason": f"llm error: {exc.__class__.__name__}", "applied": [], "rejected": []}

        actions = self._parse(raw)[: self.max_actions]
        logger.info("memory curator: proposed=%d applied=0", len(actions))
        return {
            "applied": [],
            "rejected": [],
            "proposed": actions,
            "actions": actions,
            "requires_user_confirmation": bool(actions),
        }

    # ─── helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _parse(raw: str) -> list[dict[str, Any]]:
        s = (raw or "").strip()
        s = re.sub(r"^```(?:json)?\s*|\s*```\s*$", "", s, flags=re.IGNORECASE | re.DOTALL).strip()
        if not s:
            return []
        try:
            data = json.loads(s)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        cleaned: list[dict[str, Any]] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            if entry.get("action") not in _VALID_OPS:
                continue
            if entry.get("target") not in _VALID_TARGETS:
                continue
            cleaned.append(entry)
        return cleaned

    @staticmethod
    def _render_transcript(messages: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for m in messages:
            role = (m.get("role") or "?").upper()
            content = m.get("content") or ""
            if isinstance(content, str):
                lines.append(f"{role}: {content}")
            else:
                lines.append(f"{role}: {json.dumps(content, ensure_ascii=False)}")
        return "\n".join(lines)
