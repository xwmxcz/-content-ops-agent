"""Default in-session context engine — Hermes-style lossy compression.

When the number of non-system messages crosses a threshold, the middle slice
is replaced by a single AIMessage summary produced by an auxiliary LLM call.
The head (earliest N messages — usually contains the user's framing) and tail
(latest M messages — usually contains active back-and-forth) are kept verbatim.

Tool-call pairs are protected: if a slice boundary would land between an AI
message carrying `tool_calls` and its trailing `ToolMessage`(s), the boundary
is pushed outward until the pair is intact.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Iterable

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from src.agent.context_engine import CompressionResult, ContextEngine
from src.llm.litellm_client import LiteLLMClient


logger = logging.getLogger(__name__)


SUMMARY_SYSTEM_PROMPT = """You are a conversation context compressor for the
Content Ops Agent. You will receive a transcript fragment from the middle of
an ongoing assistant↔user dialogue. Produce a STRUCTURED checkpoint summary
in markdown using EXACTLY the section headers listed below — in this order,
all sections present even if empty (write `(none)` for an empty section).

Rules:
- Reply in the same language as the transcript.
- Reply with the markdown only — no preface, no fence.
- Redact secrets, API keys, and access tokens as `[REDACTED]`.
- Quote concrete identifiers verbatim: content_id, thread_id, event_id,
  scheduled_date (YYYY-MM-DD), URLs, file paths, brand/product names.

## Active Task
THE SINGLE MOST IMPORTANT FIELD. Copy the user's most recent request
verbatim — exactly as they phrased it. One or two sentences max.

## Goal
What the user is ultimately trying to achieve in this thread
(may differ from Active Task, which is the current step).

## Constraints & Preferences
Style guidance, banned phrases / emoji rules, brand voice, length caps,
target audience, language requirements. Anything the agent has been told
to follow.

## Completed Actions
What was successfully done — list content_ids created, refined, scheduled;
calendar event_ids; SEO analyses returned; etc. Format:
`- create_content → content_id=42, title="..."`.

## Active State
The current state of the workspace at this checkpoint: which content_id is
"on the table", which platform / scheduled_date is being negotiated, etc.

## In Progress
Tasks the agent is currently running or has partial output for.

## Blocked
Anything that failed or is waiting on input. Include the failure reason.

## Key Decisions
Choices made during this segment (e.g., "platform = xiaohongshu",
"cadence = mwf", "style = casual"). Include WHY when stated.

## Resolved Questions
Clarifications the user gave (e.g., "brand name is TechFlow").

## Pending User Asks
Questions the user asked that the agent has NOT yet answered.

## Relevant Artifacts
- content_ids: list
- thread_ids: list (if referenced)
- calendar event_ids: list
- file paths / URLs: list

## Remaining Work
Concrete next steps implied by Active Task + Pending User Asks.

## Critical Context
Anything else a fresh agent reading this checkpoint cold would NEED to know
to continue the conversation without surprises.
"""


SUMMARY_ITERATIVE_SYSTEM_PROMPT = """You are a conversation context compressor.
You will receive (1) a PRIOR CHECKPOINT in the same 13-section markdown
format, and (2) NEW TURNS that occurred after that checkpoint.

Produce an UPDATED checkpoint in the same 13-section markdown format. Rules:
- Preserve information from the prior checkpoint unless the new turns
  contradict or supersede it.
- Move items from `## In Progress` to `## Completed Actions` when the new
  turns show they finished.
- Refresh `## Active Task` from the user's MOST RECENT request in the new
  turns. Copy verbatim.
- Drop items from `## Blocked` if the new turns resolved them; add new
  blocked items if anything failed.
- Keep `## Relevant Artifacts` as a cumulative running list — never delete
  ids the agent has touched.
- All 13 section headers must be present, in order. Use `(none)` for empty
  sections.
- Same language as the new turns. No fence, no preface. Redact secrets as
  `[REDACTED]`.
"""


CHECKPOINT_MARKER = "[Conversation checkpoint"


def _has_prior_checkpoint(messages: list[BaseMessage]) -> bool:
    return any(
        isinstance(m, AIMessage)
        and isinstance(m.content, str)
        and CHECKPOINT_MARKER in m.content
        for m in messages
    )


class ContextCompressor(ContextEngine):
    def __init__(
        self,
        aux_llm: LiteLLMClient,
        *,
        trigger_messages: int = 30,
        keep_head: int = 4,
        keep_tail: int = 8,
    ) -> None:
        if keep_head < 1 or keep_tail < 1:
            raise ValueError("keep_head and keep_tail must be >= 1")
        self.aux_llm = aux_llm
        self.trigger_messages = trigger_messages
        self.keep_head = keep_head
        self.keep_tail = keep_tail

    async def maybe_compress(
        self,
        messages: list[BaseMessage],
        *,
        provider: str,
        model: str,
        extra: dict[str, Any] | None = None,
    ) -> CompressionResult:
        system, body = self._split_system(messages)
        if len(body) <= self.trigger_messages:
            return CompressionResult(messages=messages, compressed=False)
        if len(body) <= self.keep_head + self.keep_tail:
            return CompressionResult(messages=messages, compressed=False)

        head_end = self._safe_head_end(body, self.keep_head)
        tail_start = self._safe_tail_start(body, len(body) - self.keep_tail)
        if tail_start <= head_end + 1:
            return CompressionResult(messages=messages, compressed=False)

        middle = body[head_end:tail_start]
        iterative = _has_prior_checkpoint(middle)
        system_prompt = SUMMARY_ITERATIVE_SYSTEM_PROMPT if iterative else SUMMARY_SYSTEM_PROMPT
        transcript = self._render_transcript(middle)
        try:
            summary = await self.aux_llm.generate_from_prompts(
                provider=provider,
                model=model,
                system_prompt=system_prompt,
                user_prompt=transcript,
                temperature=0.2,
                max_tokens=1500,
            )
        except Exception as exc:
            logger.warning("Context compression skipped: aux LLM call failed (%s)", exc)
            return CompressionResult(messages=messages, compressed=False)

        summary = (summary or "").strip()
        if not summary:
            return CompressionResult(messages=messages, compressed=False)

        marker = AIMessage(
            content=(
                f"{CHECKPOINT_MARKER} — {len(middle)} earlier messages summarized. "
                "Treat the structured sections below as background reference; "
                "respond only to messages AFTER this checkpoint.]\n\n"
                f"{summary}"
            )
        )
        rebuilt: list[BaseMessage] = list(system) + body[:head_end] + [marker] + body[tail_start:]
        return CompressionResult(
            messages=rebuilt,
            compressed=True,
            summary=summary,
            dropped_count=len(middle),
        )

    # ─── helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _split_system(messages: list[BaseMessage]) -> tuple[list[BaseMessage], list[BaseMessage]]:
        system: list[BaseMessage] = []
        rest: list[BaseMessage] = []
        for m in messages:
            if isinstance(m, SystemMessage) and not rest:
                system.append(m)
            else:
                rest.append(m)
        return system, rest

    @staticmethod
    def _safe_head_end(body: list[BaseMessage], proposed_end: int) -> int:
        """Shrink head so it doesn't cut between an AI tool_call and its ToolMessage."""
        idx = min(proposed_end, len(body))
        while idx > 0:
            prev = body[idx - 1]
            if isinstance(prev, AIMessage) and getattr(prev, "tool_calls", None):
                idx -= 1
                continue
            break
        return max(idx, 1)

    @staticmethod
    def _safe_tail_start(body: list[BaseMessage], proposed_start: int) -> int:
        """Push tail forward so it doesn't begin with an orphan ToolMessage."""
        idx = max(proposed_start, 0)
        while idx < len(body) and isinstance(body[idx], ToolMessage):
            idx += 1
        return idx

    @staticmethod
    def _render_transcript(messages: Iterable[BaseMessage]) -> str:
        lines: list[str] = []
        for m in messages:
            content = m.content if isinstance(m.content, str) else json.dumps(m.content, ensure_ascii=False)
            if isinstance(m, HumanMessage):
                lines.append(f"USER: {content}")
            elif isinstance(m, AIMessage):
                if content:
                    lines.append(f"ASSISTANT: {content}")
                for call in getattr(m, "tool_calls", None) or []:
                    lines.append(f"ASSISTANT_TOOL_CALL: {call.get('name')} {json.dumps(call.get('args') or {}, ensure_ascii=False)}")
            elif isinstance(m, ToolMessage):
                lines.append(f"TOOL_RESULT: {content}")
            else:
                lines.append(content)
        return "\n".join(lines)
