"""Tests for the dynamic plan-then-execute Studio pipeline.

Uses a FakeLLMClient that drives the planner + sub-agents deterministically.
Real streaming is mocked at the SubAgentRunner.run() level by injecting a
FakeRunner — keeps the test suite fast and avoids depending on litellm.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_store
from src.api.main import app
from src.api.schemas.agent import PipelineRunRequest, SubAgentId
from src.api.services.dynamic_pipeline import DynamicPipeline
from src.api.services.sub_agents import SubAgentSpec
from src.models import ContentType, ContentStyle
from src.storage import ContentStore


# ---------- fakes -------------------------------------------------------------


class FakePlannerLLM:
    """Captures generate_from_prompts calls; first call returns the planner JSON,
    subsequent ones return revision JSON / null. generate_stream is unused (FakeRunner
    bypasses it)."""

    def __init__(self):
        self.calls: list[dict] = []
        self.responses: list[str] = []

    def queue(self, *responses: str):
        self.responses.extend(responses)

    async def generate_from_prompts(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            return "null"
        return self.responses.pop(0)

    async def generate(self, **kwargs):
        return "Agent reply"

    async def generate_stream(self, **kwargs):
        # Not used in tests — FakeRunner.run is what gets invoked.
        text = await self.generate_from_prompts(**kwargs)
        async def _gen():
            yield type("C", (), {"delta": text, "usage": (10, 5)})()
            yield type("C", (), {"delta": "", "usage": (10, 5)})()
        async for c in _gen():
            yield c


class FakeRunner:
    """Stand-in for SubAgentRunner that returns scripted outputs per agent_id."""

    def __init__(self, store, llm=None, model_factory=None, scripted: dict[SubAgentId, str] | None = None):
        self.store = store
        self.llm = llm
        self.scripted = scripted or {}
        self.calls: list[tuple[str, str, tuple[str, ...] | None]] = []  # (agent_id, prompt, allowed_tools)
        self.token_emissions: list[tuple[int, str]] = []  # (step_index?, delta) — index unknown here, but sink knows it

    async def run(self, spec: SubAgentSpec, user_prompt: str, provider: str, model: str,
                  max_tokens: int = 2048, token_sink=None, tool_sink=None, allowed_tools: tuple[str, ...] | None = None):
        self.calls.append((spec.id, user_prompt, allowed_tools))
        text = self.scripted.get(spec.id, f"[{spec.id} default output]")
        if token_sink is not None:
            # Emit two tokens so the test for `step_token` event presence passes.
            await token_sink(text[: max(1, len(text) // 2)])
            await token_sink(text[max(1, len(text) // 2):])
        return text, 10, 5, 12, 0.0001


# ---------- fixtures ----------------------------------------------------------


@pytest.fixture
def store():
    db_path = Path("data/test_dynamic_pipeline.db")
    if db_path.exists():
        db_path.unlink()
    s = ContentStore(db_path=str(db_path))
    yield s
    s.engine.dispose()
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def planner_llm():
    return FakePlannerLLM()


def _make_pipeline(store, planner_llm, scripted=None):
    runner = FakeRunner(store=store, scripted=scripted)
    return DynamicPipeline(store=store, llm=planner_llm, runner=runner), runner


def _request(topic="周末徒步路线推荐", **overrides: Any):
    payload = {
        "topic": topic,
        "content_type": ContentType.XIAOHONGSHU,
        "style": ContentStyle.PROFESSIONAL,
        "keywords": ["徒步", "户外"],
        "provider": "siliconflow",
        "model": "Qwen/Qwen2.5-7B-Instruct",
    }
    payload.update(overrides)
    return PipelineRunRequest(**payload)


# ---------- tests -------------------------------------------------------------


@pytest.mark.asyncio
async def test_planner_produces_3_step_plan(store, planner_llm):
    plan_json = json.dumps([
        {"index": 1, "agent_id": "strategy", "description": "Plan", "instruction": "go", "inputs_from": []},
        {"index": 2, "agent_id": "writer", "description": "Draft", "instruction": "go", "inputs_from": [1]},
        {"index": 3, "agent_id": "editor", "description": "Polish", "instruction": "go", "inputs_from": [2]},
    ])
    planner_llm.queue(plan_json, "null")  # planner call + one possible revision call (won't trigger because no reviewer)

    pipeline, runner = _make_pipeline(store, planner_llm,
                                      scripted={"strategy": "S", "writer": "W", "editor": "E"})

    response = await pipeline.run(_request())

    assert len(response.plan) == 3
    assert [s.agent_id for s in response.plan] == ["strategy", "writer", "editor"]
    assert all(s.status == "completed" for s in response.plan)
    assert response.final_content.content == "E"  # editor output preferred
    assert response.revision_count == 0


@pytest.mark.asyncio
async def test_planner_fallback_on_invalid_json(store, planner_llm):
    planner_llm.queue("I'll just wing it", "null")

    pipeline, runner = _make_pipeline(store, planner_llm,
                                      scripted={"researcher": "R", "strategy": "S", "writer": "W",
                                                "fact_checker": "F", "editor": "E"})

    response = await pipeline.run(_request())

    # Dynamic is the research-oriented track; the fallback default plan now leads
    # with researcher and inserts fact_checker before the editor.
    assert [s.agent_id for s in response.plan] == [
        "researcher", "strategy", "writer", "fact_checker", "editor",
    ]
    assert all(s.status == "completed" for s in response.plan)


@pytest.mark.asyncio
async def test_pipeline_rejects_when_all_research_sources_are_disabled(store, planner_llm):
    pipeline, _ = _make_pipeline(store, planner_llm)

    with pytest.raises(ValueError, match="At least one research source must be enabled"):
        await pipeline.run(_request(use_web_search=False, use_history_search=False))


@pytest.mark.asyncio
async def test_pipeline_hard_limits_research_sources_in_prompts_and_runner(store, planner_llm):
    planner_llm.queue("not-json", "null")
    pipeline, runner = _make_pipeline(
        store,
        planner_llm,
        scripted={
            "researcher": "R",
            "strategy": "S",
            "writer": "W",
            "fact_checker": "F",
            "editor": "E",
        },
    )

    await pipeline.run(_request(use_web_search=False, use_history_search=True))

    planner_prompt = planner_llm.calls[0]["user_prompt"]
    assert "Available tools to researcher/fact_checker: search_history, view_content, list_recent_contents" in planner_prompt
    assert "Available tools to researcher/fact_checker: search_history, view_content, list_recent_contents, web_search" not in planner_prompt

    research_calls = [call for call in runner.calls if call[0] in {"researcher", "fact_checker"}]
    assert research_calls
    assert all(call[2] == ("search_history", "view_content", "list_recent_contents") for call in research_calls)
    assert any("Do not call web_search in this run; public web search is disabled." in call[1] for call in research_calls)


def test_plan_coercion_remaps_inputs_after_dropping_steps():
    plan = DynamicPipeline._coerce_plan([
        {"index": 1, "agent_id": "strategy", "description": "Plan", "inputs_from": []},
        {"index": 2, "agent_id": "not_real", "description": "Drop me", "inputs_from": [1]},
        {"index": 3, "agent_id": "writer", "description": "Draft", "inputs_from": [1, 2]},
        {"index": 5, "agent_id": "editor", "description": "Polish", "inputs_from": [3, 99]},
    ])

    assert [step.index for step in plan] == [1, 2, 3]
    assert [step.agent_id for step in plan] == ["strategy", "writer", "editor"]
    assert [step.inputs_from for step in plan] == [[], [1], [2]]


@pytest.mark.asyncio
async def test_pipeline_emits_events_in_order(store, planner_llm):
    plan_json = json.dumps([
        {"index": 1, "agent_id": "strategy", "description": "Plan", "instruction": "go", "inputs_from": []},
        {"index": 2, "agent_id": "writer", "description": "Draft", "instruction": "go", "inputs_from": [1]},
    ])
    planner_llm.queue(plan_json, "null")

    pipeline, _ = _make_pipeline(store, planner_llm,
                                 scripted={"strategy": "S", "writer": "W"})
    response = await pipeline.run(_request())

    events = store.list_run_events(response.run_id)
    types = [e["event_type"] for e in events]

    assert types[0] == "plan_ready"
    # Each step: step_start + at least one step_token + step_complete
    assert types.count("step_start") == 2
    assert types.count("step_complete") == 2
    assert types.count("step_token") >= 2  # at least one per step
    assert types[-1] == "run_complete"


@pytest.mark.asyncio
async def test_pipeline_revises_after_low_review_score(store, planner_llm):
    # Initial plan has a reviewer at the end so revision is triggered.
    initial_plan = json.dumps([
        {"index": 1, "agent_id": "strategy", "description": "Plan", "instruction": "go", "inputs_from": []},
        {"index": 2, "agent_id": "writer", "description": "Draft", "instruction": "go", "inputs_from": [1]},
        {"index": 3, "agent_id": "reviewer", "description": "Score", "instruction": "go", "inputs_from": [2]},
    ])
    revised_plan = json.dumps([
        {"index": 1, "agent_id": "strategy", "description": "Plan", "instruction": "go", "inputs_from": []},
        {"index": 2, "agent_id": "writer", "description": "Draft", "instruction": "go", "inputs_from": [1]},
        {"index": 3, "agent_id": "reviewer", "description": "Score", "instruction": "go", "inputs_from": [2]},
        {"index": 4, "agent_id": "editor", "description": "Fix", "instruction": "improve", "inputs_from": [2, 3]},
    ])
    planner_llm.queue(initial_plan, revised_plan, "null")

    pipeline, runner = _make_pipeline(store, planner_llm,
                                      scripted={"strategy": "S", "writer": "W",
                                                "reviewer": "Score: 60\nNeeds polish",
                                                "editor": "Polished"})
    response = await pipeline.run(_request())

    assert response.revision_count == 1
    # The final plan must include the new editor step
    agent_ids = [s.agent_id for s in response.plan]
    assert agent_ids[-1] == "editor"
    # The editor's output should be the final content
    assert response.final_content.content == "Polished"

    events = store.list_run_events(response.run_id)
    assert any(e["event_type"] == "plan_revised" for e in events)


@pytest.mark.asyncio
async def test_pipeline_persists_tokens_and_cost(store, planner_llm):
    plan_json = json.dumps([
        {"index": 1, "agent_id": "strategy", "description": "Plan", "instruction": "go", "inputs_from": []},
        {"index": 2, "agent_id": "writer", "description": "Draft", "instruction": "go", "inputs_from": [1]},
    ])
    planner_llm.queue(plan_json, "null")
    pipeline, _ = _make_pipeline(store, planner_llm, scripted={"strategy": "S", "writer": "W"})

    response = await pipeline.run(_request())

    assert response.total_prompt_tokens == 20  # 2 steps * 10 tokens
    assert response.total_completion_tokens == 10  # 2 steps * 5 tokens
    # Cost is positive (estimate_cost was called with non-zero tokens) and
    # reflects 2 steps' contributions equally; per-step cost recorded in plan.
    assert response.total_cost > 0
    assert all(s.cost_estimate > 0 for s in response.plan)
    assert abs(response.total_cost - sum(s.cost_estimate for s in response.plan)) < 1e-9

    # Persisted run row reflects the same totals
    row = store.get_run(response.run_id)
    assert row["total_prompt_tokens"] == 20
    assert row["total_completion_tokens"] == 10
    assert abs(row["total_cost"] - response.total_cost) < 1e-9

    # Saved content row exists
    saved = store.get_content(response.saved_content_id)
    assert saved is not None


@pytest.mark.asyncio
async def test_sse_stream_replays_persisted_events(store, planner_llm):
    plan_json = json.dumps([
        {"index": 1, "agent_id": "writer", "description": "Draft", "instruction": "go", "inputs_from": []},
    ])
    planner_llm.queue(plan_json, "null")
    pipeline, _ = _make_pipeline(store, planner_llm, scripted={"writer": "W"})
    response = await pipeline.run(_request())

    # All events from this run, replayed via list_run_events
    events = store.list_run_events(response.run_id, after_seq=0, limit=1000)
    assert len(events) >= 4  # plan_ready + step_start + step_token + step_complete + run_complete
    assert events[0]["event_type"] == "plan_ready"
    assert events[-1]["event_type"] == "run_complete"

    # after_seq pagination works
    mid = events[len(events) // 2]["seq"]
    tail = store.list_run_events(response.run_id, after_seq=mid)
    assert all(e["seq"] > mid for e in tail)


def test_sse_stream_resumes_from_last_event_id(store, planner_llm):
    plan_json = json.dumps([
        {"index": 1, "agent_id": "writer", "description": "Draft", "instruction": "go", "inputs_from": []},
    ])
    planner_llm.queue(plan_json, "null")
    pipeline, _ = _make_pipeline(store, planner_llm, scripted={"writer": "W"})
    response = asyncio.run(pipeline.run(_request()))
    events = store.list_run_events(response.run_id)
    first_seq = events[0]["seq"]

    from src.api.dependencies import get_store as real_get_store

    app.dependency_overrides[real_get_store] = lambda: store
    try:
        with TestClient(app) as client:
            stream = client.get(
                f"/api/agent/runs/{response.run_id}/stream",
                headers={"Last-Event-ID": str(first_seq)},
            )
        assert stream.status_code == 200
        assert f"id: {first_seq}\n" not in stream.text
        assert f"id: {first_seq + 1}\n" in stream.text
        assert "event: run_complete" in stream.text
    finally:
        app.dependency_overrides.pop(real_get_store, None)


@pytest.mark.asyncio
async def test_pipeline_observes_cancellation_at_step_boundary(store, planner_llm):
    """DELETE /api/agent/runs/{id} flips status to 'cancelled'; the running
    pipeline must notice that at the next step boundary and stop scheduling
    further steps. Already-completed steps are kept."""
    plan_json = json.dumps([
        {"index": 1, "agent_id": "strategy", "description": "Plan", "instruction": "go", "inputs_from": []},
        {"index": 2, "agent_id": "writer", "description": "Draft", "instruction": "go", "inputs_from": [1]},
        {"index": 3, "agent_id": "editor", "description": "Polish", "instruction": "go", "inputs_from": [2]},
    ])
    planner_llm.queue(plan_json, "null")

    import uuid
    run_id = f"run_{uuid.uuid4().hex[:12]}"

    runner = FakeRunner(store=store, scripted={"strategy": "S", "writer": "W", "editor": "E"})
    original_run = runner.run

    async def cancel_after_first(*args, **kwargs):
        result = await original_run(*args, **kwargs)
        if len(runner.calls) == 1:
            store.update_run(run_id, status="cancelled")
        return result

    runner.run = cancel_after_first  # type: ignore[assignment]

    pipeline = DynamicPipeline(store=store, llm=planner_llm, runner=runner)
    response = await pipeline.run(_request(), run_id=run_id)

    assert response.status == "cancelled"
    statuses = [s.status for s in response.plan]
    assert statuses[0] == "completed"
    assert statuses[1] == "pending"
    assert statuses[2] == "pending"
    assert response.saved_content_id is None
    assert store.get_run(run_id)["status"] == "cancelled"


def test_delete_run_cancels_and_emits_event(store):
    """DELETE /api/agent/runs/{id} flips the row, emits run_cancelled, and is
    idempotent against terminal runs."""
    from src.api.dependencies import get_store as real_get_store

    app.dependency_overrides[real_get_store] = lambda: store
    client = TestClient(app)
    try:
        store.create_run(
            run_id="run_cancel_me",
            topic="t",
            content_type="xiaohongshu",
            style="professional",
        )

        resp = client.delete("/api/agent/runs/run_cancel_me")
        assert resp.status_code == 200
        body = resp.json()
        assert body["cancelled"] is True
        assert body["status"] == "cancelled"

        assert store.get_run("run_cancel_me")["status"] == "cancelled"
        events = store.list_run_events("run_cancel_me")
        assert any(e["event_type"] == "run_cancelled" for e in events)

        resp2 = client.delete("/api/agent/runs/run_cancel_me")
        assert resp2.status_code == 200
        assert resp2.json()["cancelled"] is False

        resp3 = client.delete("/api/agent/runs/run_does_not_exist")
        assert resp3.status_code == 404
    finally:
        app.dependency_overrides.pop(real_get_store, None)


def test_create_pipeline_run_rejects_when_all_research_sources_are_disabled(store):
    from src.api.dependencies import get_litellm_client as real_get_litellm_client
    from src.api.dependencies import get_store as real_get_store

    app.dependency_overrides[real_get_store] = lambda: store
    app.dependency_overrides[real_get_litellm_client] = lambda: object()
    client = TestClient(app)
    try:
        resp = client.post(
            "/api/agent/runs",
            json={
                "topic": "写一篇模型横评",
                "content_type": "blog",
                "style": "professional",
                "length": "medium",
                "keywords": ["模型"],
                "provider": "siliconflow",
                "model": "Qwen/Qwen2.5-7B-Instruct",
                "temperature": 0.7,
                "max_tokens": 2048,
                "save_final": True,
                "use_web_search": False,
                "use_history_search": False,
            },
        )

        assert resp.status_code == 400
        assert "At least one research source must be enabled" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(real_get_store, None)
        app.dependency_overrides.pop(real_get_litellm_client, None)
