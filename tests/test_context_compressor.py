"""Tests for the in-session ContextCompressor (Hermes layer 4)."""
from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.agent.context_compressor import (
    CHECKPOINT_MARKER,
    ContextCompressor,
    SUMMARY_ITERATIVE_SYSTEM_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
)


class FakeAuxLLM:
    def __init__(self, response: str = "[summary] discussed XHS topic"):
        self.response = response
        self.calls = []

    async def generate_from_prompts(self, **kw):
        self.calls.append(kw)
        return self.response


def _build_chat(n: int) -> list:
    msgs = [SystemMessage(content="sys")]
    for i in range(n):
        msgs.append(HumanMessage(content=f"q{i}"))
        msgs.append(AIMessage(content=f"a{i}"))
    return msgs


@pytest.mark.asyncio
class TestContextCompressor:
    async def test_no_op_below_threshold(self):
        c = ContextCompressor(FakeAuxLLM(), trigger_messages=20, keep_head=2, keep_tail=2)
        msgs = _build_chat(5)  # 10 non-system, below 20
        r = await c.maybe_compress(msgs, provider="claude", model="m")
        assert not r.compressed
        assert r.messages == msgs

    async def test_fires_above_threshold(self):
        aux = FakeAuxLLM("merged summary")
        c = ContextCompressor(aux, trigger_messages=10, keep_head=2, keep_tail=2)
        msgs = _build_chat(10)  # 20 non-system
        r = await c.maybe_compress(msgs, provider="claude", model="m")
        assert r.compressed
        assert r.dropped_count > 0
        # head + summary + tail + system
        assert len(r.messages) == 1 + 2 + 1 + 2
        # summary text is inside an AIMessage
        assert any("merged summary" in (m.content or "") for m in r.messages if isinstance(m, AIMessage))
        assert len(aux.calls) == 1

    async def test_protects_tool_call_pair(self):
        aux = FakeAuxLLM("S")
        c = ContextCompressor(aux, trigger_messages=4, keep_head=2, keep_tail=2)
        msgs = [
            SystemMessage(content="sys"),
            HumanMessage(content="u1"),
            AIMessage(content="a1", tool_calls=[{"id": "t1", "name": "foo", "args": {}}]),
            ToolMessage(content="r1", tool_call_id="t1"),
            AIMessage(content="a2"),
            HumanMessage(content="u2"),
            AIMessage(content="a3"),
            HumanMessage(content="u3"),
            AIMessage(content="a4"),
        ]
        r = await c.maybe_compress(msgs, provider="claude", model="m")
        # No ToolMessage should appear immediately after the summary marker.
        kinds = [type(m).__name__ for m in r.messages]
        if "ToolMessage" in kinds:
            tool_idx = kinds.index("ToolMessage")
            # Whatever lives at tool_idx-1 must be the AIMessage that issued tool_calls.
            prev = r.messages[tool_idx - 1]
            assert isinstance(prev, AIMessage)
            assert prev.tool_calls

    async def test_aux_llm_failure_is_silent(self):
        class BoomLLM:
            async def generate_from_prompts(self, **kw):
                raise RuntimeError("nope")
        c = ContextCompressor(BoomLLM(), trigger_messages=4, keep_head=2, keep_tail=2)
        msgs = _build_chat(5)
        r = await c.maybe_compress(msgs, provider="claude", model="m")
        assert not r.compressed
        assert r.messages == msgs

    async def test_empty_summary_skips_compression(self):
        c = ContextCompressor(FakeAuxLLM("   "), trigger_messages=4, keep_head=2, keep_tail=2)
        msgs = _build_chat(5)
        r = await c.maybe_compress(msgs, provider="claude", model="m")
        assert not r.compressed


@pytest.mark.asyncio
class TestStructuredPrompt:
    async def test_first_compression_uses_full_prompt(self):
        aux = FakeAuxLLM("## Active Task\n(none)\n\n## Goal\n(none)")
        c = ContextCompressor(aux, trigger_messages=4, keep_head=2, keep_tail=2)
        msgs = _build_chat(5)
        r = await c.maybe_compress(msgs, provider="claude", model="m")
        assert r.compressed
        assert len(aux.calls) == 1
        sys_prompt = aux.calls[0]["system_prompt"]
        assert sys_prompt == SUMMARY_SYSTEM_PROMPT
        assert "## Active Task" in sys_prompt
        assert "verbatim" in sys_prompt.lower()
        assert "[REDACTED]" in sys_prompt
        # Marker text is now the Hermes-style checkpoint wrapper.
        marker = next(m for m in r.messages if isinstance(m, AIMessage) and CHECKPOINT_MARKER in (m.content or ""))
        assert "Treat the structured sections" in marker.content
        assert "## Active Task" in marker.content

    async def test_re_compression_switches_to_iterative_prompt(self):
        aux = FakeAuxLLM("## Active Task\nupdated")
        c = ContextCompressor(aux, trigger_messages=4, keep_head=1, keep_tail=1)
        # Build a transcript whose middle slice already contains a prior checkpoint.
        msgs: list = [SystemMessage(content="sys"), HumanMessage(content="u_head")]
        msgs.append(AIMessage(content=f"{CHECKPOINT_MARKER} — 8 earlier messages summarized."))
        for i in range(6):
            msgs.append(HumanMessage(content=f"q{i}"))
            msgs.append(AIMessage(content=f"a{i}"))
        r = await c.maybe_compress(msgs, provider="claude", model="m")
        assert r.compressed
        assert aux.calls[0]["system_prompt"] == SUMMARY_ITERATIVE_SYSTEM_PROMPT
        assert "PRIOR CHECKPOINT" in aux.calls[0]["system_prompt"]
        assert "cumulative running list" in aux.calls[0]["system_prompt"]
