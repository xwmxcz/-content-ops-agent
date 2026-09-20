"""Streamed tokens are coalesced before they are persisted.

Every run event is a transaction that locks the run row, and one per token meant
roughly one per generated token. Coalescing must not lose, reorder, or delay the
first piece of a step's text, and must not let text overtake the events around it.
"""

from __future__ import annotations

import json

import pytest

from src.api.services import dynamic_pipeline
from src.api.services.dynamic_pipeline import DynamicPipeline, _TokenBatcher
from src.api.services.sub_agents import SubAgentSpec
from src.models import ContentStyle, ContentType
from src.utils import config

# ─── Token coalescing ──────────────────────────────────────────────────────


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch) -> _Clock:
    fake = _Clock()
    monkeypatch.setattr(dynamic_pipeline.time, "monotonic", fake.monotonic)
    monkeypatch.setattr(config, "SSE_TOKEN_BATCH_SECONDS", 0.15)
    monkeypatch.setattr(config, "SSE_TOKEN_BATCH_MAX_CHARS", 400)
    return fake


def _batcher() -> tuple[_TokenBatcher, list[str]]:
    emitted: list[str] = []

    async def emit(delta: str) -> None:
        emitted.append(delta)

    return _TokenBatcher(emit), emitted


async def test_first_delta_is_not_held_back(clock):
    batcher, emitted = _batcher()

    await batcher.add("Hel")

    assert emitted == ["Hel"]


async def test_deltas_inside_the_interval_become_one_event(clock):
    batcher, emitted = _batcher()
    await batcher.add("a")

    for delta in ("b", "c", "d"):
        clock.now += 0.04
        await batcher.add(delta)
    assert emitted == ["a"]

    clock.now += 0.04
    await batcher.add("e")
    assert emitted == ["a", "bcde"]


async def test_size_cap_flushes_without_waiting_for_the_interval(clock, monkeypatch):
    monkeypatch.setattr(config, "SSE_TOKEN_BATCH_MAX_CHARS", 10)
    batcher, emitted = _batcher()
    await batcher.add("x")

    await batcher.add("123456")
    await batcher.add("7890")

    assert emitted == ["x", "1234567890"]


async def test_flush_emits_the_remainder_once_and_nothing_when_empty(clock):
    batcher, emitted = _batcher()
    await batcher.add("a")
    await batcher.add("tail")

    await batcher.flush()
    await batcher.flush()

    assert emitted == ["a", "tail"]


async def test_zero_interval_restores_one_event_per_delta(clock, monkeypatch):
    monkeypatch.setattr(config, "SSE_TOKEN_BATCH_SECONDS", 0)
    batcher, emitted = _batcher()

    for delta in ("a", "b", "c"):
        await batcher.add(delta)

    assert emitted == ["a", "b", "c"]


async def test_no_text_is_lost_or_reordered_by_coalescing(clock):
    batcher, emitted = _batcher()
    text = "流式输出的每一个字都必须按顺序到达客户端。" * 40

    for index, char in enumerate(text):
        clock.now += 0.01 if index % 7 else 0.2
        await batcher.add(char)
    await batcher.flush()

    assert "".join(emitted) == text
    assert len(emitted) < len(text) / 5


# ─── Pipeline ordering with coalescing on ──────────────────────────────────


class _PlannerLLM:
    async def generate_from_prompts(self, **kwargs) -> str:
        return json.dumps(
            [{"index": 1, "agent_id": "writer", "description": "Draft", "instruction": "go", "inputs_from": []}]
        )


class _StreamingRunner:
    """Streams text, calls a tool mid-stream, then streams the rest."""

    def __init__(self, fail_after_streaming: bool = False) -> None:
        self.fail_after_streaming = fail_after_streaming

    async def run(self, spec: SubAgentSpec, token_sink=None, tool_sink=None, **kwargs):
        for char in "before-tool ":
            await token_sink(char)
        await tool_sink("tool_call_result", {"name": "web_search", "status": "completed"})
        for char in "after-tool":
            await token_sink(char)
        if self.fail_after_streaming:
            raise RuntimeError("provider dropped the stream")
        return "before-tool after-tool", 10, 5, 12, 0.0001


def _pipeline_request():
    from src.api.schemas.agent import PipelineRunRequest

    return PipelineRunRequest(
        topic="topic",
        content_type=ContentType.BLOG,
        style=ContentStyle.CASUAL,
        provider="siliconflow",
        model="Qwen/Qwen2.5-7B-Instruct",
    )


def _events(store, run_id: str) -> list[tuple[str, dict]]:
    return [(e["event_type"], json.loads(e["payload"])) for e in store.list_run_events(run_id, limit=1000)]


@pytest.fixture
def coalescing(monkeypatch):
    # An interval no test reaches, so only the ordering flushes can emit.
    monkeypatch.setattr(config, "SSE_TOKEN_BATCH_SECONDS", 3600.0)
    monkeypatch.setattr(config, "SSE_TOKEN_BATCH_MAX_CHARS", 10_000)


async def test_text_streamed_before_a_tool_call_is_persisted_before_it(store, coalescing):
    pipeline = DynamicPipeline(store=store, llm=_PlannerLLM(), runner=_StreamingRunner())

    response = await pipeline.run(_pipeline_request())

    events = _events(store, response.run_id)
    step = [(kind, payload.get("delta")) for kind, payload in events if kind in {"step_token", "tool_call_result"}]
    assert step == [
        ("step_token", "b"),
        ("step_token", "efore-tool "),
        ("tool_call_result", None),
        ("step_token", "after-tool"),
    ]
    kinds = [kind for kind, _ in events]
    assert kinds.index("step_complete") > max(i for i, kind in enumerate(kinds) if kind == "step_token")


async def test_text_streamed_before_a_failure_is_persisted_before_step_failed(store, coalescing):
    pipeline = DynamicPipeline(store=store, llm=_PlannerLLM(), runner=_StreamingRunner(fail_after_streaming=True))

    try:
        response = await pipeline.run(_pipeline_request())
        run_id = response.run_id
    except Exception:  # noqa: BLE001 -- a failed single-step run may raise; the events are what is under test
        run_id = store.list_runs(limit=1)[0]["id"]

    # A failed step makes the planner revise and retry, so the step runs more than
    # once. Each attempt must have persisted its whole text before its step_failed.
    attempts: list[str] = []
    streamed = ""
    for kind, payload in _events(store, run_id):
        if kind == "step_token":
            streamed += payload["delta"]
        elif kind == "step_failed":
            attempts.append(streamed)
            streamed = ""

    assert attempts
    assert set(attempts) == {"before-tool after-tool"}
    assert streamed == "", "tokens were persisted after the event that ended their step"
