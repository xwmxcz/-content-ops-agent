"""Real graph routing with fake LLMs and PostgreSQL as the sole recovery journal."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_store
from src.api.main import app
from src.api.schemas.agent import PipelineRunRequest
from src.api.services import dynamic_pipeline, pipeline_graph
from src.api.services.dynamic_pipeline import DynamicPipeline
from src.api.services.pipeline_engine import ENGINE_REQUEST_KEY
from src.jobs import runner
from src.jobs.checkpoint import load_checkpoint
from src.llm.litellm_client import LLMConfigurationError
from src.storage.models import User
from src.utils import config


def _plan(agents=("strategy", "writer", "editor")):
    return [
        {
            "index": i,
            "agent_id": agent,
            "description": agent,
            "instruction": "go",
            "inputs_from": [i - 1] if i > 1 else [],
        }
        for i, agent in enumerate(agents, 1)
    ]


class Planner:
    def __init__(self, plans=None):
        self.plans = list(plans or [_plan()])
        self.calls = 0

    async def generate_from_prompts(self, **kwargs):
        self.calls += 1
        return json.dumps(self.plans.pop(0)) if self.plans else "null"


class Agents:
    def __init__(self, hook=None, prefix=""):
        self.calls = []
        self.hook = hook
        self.prefix = prefix

    async def run(self, spec, token_sink=None, tool_sink=None, **kwargs):
        self.calls.append(spec.id)
        if self.hook:
            await self.hook(spec.id)
        if tool_sink and spec.id == "strategy":
            await tool_sink("tool_call_result", {"name": "fixture", "args": {}, "preview": self.prefix + "evidence"})
        return self.prefix + spec.id + " output", 10, 5, 1, 0.0


def _request(**overrides):
    return PipelineRunRequest(
        **{
            "topic": "hiking guide",
            "content_type": "blog",
            "style": "professional",
            "provider": "siliconflow",
            **overrides,
        }
    )


def _create(store, run_id="graph_run", engine="langgraph_v1"):
    data = _request().model_dump(mode="json")
    if engine is not None:
        data[ENGINE_REQUEST_KEY] = engine
    store.create_run(run_id=run_id, topic="hiking guide", content_type="blog", style="professional", request=data)
    return run_id


def _transition(store, run_id, status):
    return store.transition_run_and_append_event(
        run_id,
        expected_statuses={"failed"} if status == "running" else {"running"},
        new_status=status,
        event_type={"running": "run_resumed", "failed": "run_failed", "cancelled": "run_cancelled"}[status],
        payload={},
        error=None,
    )


def _event_types(store, run_id):
    return [event["event_type"] for event in store.list_run_events(run_id, limit=500)]


def _observe_graph(monkeypatch):
    visited = []

    async def observe(pipeline, execution):
        graph = pipeline_graph.build_pipeline_graph(pipeline)
        assert graph.checkpointer is None, "run_steps must remain the only durable checkpoint source"
        response = None
        async for update in graph.astream(
            {"execution": execution},
            config={"recursion_limit": pipeline_graph.GRAPH_RECURSION_LIMIT},
            stream_mode="updates",
        ):
            visited.extend(update)
            if "finish" in update:
                response = update["finish"]["response"]
        return response

    monkeypatch.setattr(pipeline_graph, "run_pipeline_graph", observe)
    return visited


async def test_new_run_uses_real_graph_nodes_and_conditional_finish(store, monkeypatch):
    monkeypatch.setattr(config, "PIPELINE_ENGINE", "langgraph_v1")
    visited = _observe_graph(monkeypatch)
    agents = Agents()
    result = await DynamicPipeline(store, llm=Planner(), runner=agents).run(_request())
    assert result.status == "completed"
    assert store.get_run(result.run_id)["request"][ENGINE_REQUEST_KEY] == "langgraph_v1"
    assert visited == ["prepare", "select"] + ["execute_step", "revise", "select"] * 3 + ["finish"]
    assert agents.calls == ["strategy", "writer", "editor"]
    assert result.total_prompt_tokens == 30
    assert result.plan[0].tool_events[0].preview == "evidence"
    assert len(store.list_contents()) == 1


@pytest.mark.parametrize("engine", [None, "legacy", "langgraph_v1"])
async def test_resume_keeps_persisted_engine_and_old_checkpoints_after_config_switch(store, monkeypatch, engine):
    run_id = _create(store, engine=engine)
    planner = Planner()

    async def stop_at_writer(agent):
        if agent == "writer":
            raise LLMConfigurationError("provider offline")

    with pytest.raises(LLMConfigurationError):
        await DynamicPipeline(store, llm=planner, runner=Agents(stop_at_writer)).run(_request(), run_id)
    assert [step["step_name"] for step in load_checkpoint(store, run_id)] == ["strategy"]
    _transition(store, run_id, "failed")
    _transition(store, run_id, "running")
    monkeypatch.setattr(config, "PIPELINE_ENGINE", "legacy" if engine == "langgraph_v1" else "langgraph_v1")
    visited = _observe_graph(monkeypatch)
    healthy = Agents()
    result = await DynamicPipeline(store, llm=planner, runner=healthy).run(_request(), run_id)
    assert bool(visited) == (engine == "langgraph_v1")
    assert healthy.calls == ["writer", "editor"]
    assert planner.calls == 1
    assert result.total_prompt_tokens == 30
    assert result.plan[0].tool_events[0].preview == "evidence"
    assert len(store.list_contents()) == 1
    types = _event_types(store, run_id)
    assert types[types.index("run_failed") + 1 :][:2] == ["run_resumed", "plan_ready"]


@pytest.mark.parametrize("engine", ["legacy", "langgraph_v1"])
def test_api_creation_pins_engine_and_resume_preserves_it(store, monkeypatch, engine):
    monkeypatch.setattr(config, "PIPELINE_ENGINE", engine)
    delivered = []
    monkeypatch.setattr("src.api.routes.agent.enqueue_pipeline_run", lambda *args: delivered.append(args))
    app.dependency_overrides[get_store] = lambda: store
    try:
        with TestClient(app) as client:
            # Client fields cannot choose the private engine version.
            response = client.post(
                "/api/agent/runs", json={**_request().model_dump(mode="json"), ENGINE_REQUEST_KEY: "bad"}
            )
            assert response.status_code == 202
            run_id = response.json()["run_id"]
            assert delivered[-1][1][ENGINE_REQUEST_KEY] == engine
            assert store.get_run(run_id)["request"] == delivered[-1][1]
            _transition(store, run_id, "failed")
            monkeypatch.setattr(config, "PIPELINE_ENGINE", "legacy" if engine == "langgraph_v1" else "langgraph_v1")
            assert client.post(f"/api/agent/runs/{run_id}/resume").status_code == 202
            assert delivered[-1][1][ENGINE_REQUEST_KEY] == engine
    finally:
        app.dependency_overrides.pop(get_store, None)


def test_resume_rejects_unknown_engine_before_reopening_run(store, monkeypatch):
    run_id = _create(store, engine="future_v9")
    _transition(store, run_id, "failed")
    monkeypatch.setattr("src.api.routes.agent.enqueue_pipeline_run", lambda *args: pytest.fail("must not enqueue"))
    app.dependency_overrides[get_store] = lambda: store
    try:
        with TestClient(app) as client:
            assert client.post(f"/api/agent/runs/{run_id}/resume").status_code == 409
    finally:
        app.dependency_overrides.pop(get_store, None)
    assert store.get_run(run_id)["status"] == "failed"
    assert _event_types(store, run_id) == ["run_failed"]


async def test_checkpoint_before_event_crash_is_restored_without_repeating_work(store, monkeypatch):
    run_id = _create(store)
    pipeline = DynamicPipeline(store, llm=Planner(), runner=Agents())
    original_emit = pipeline._emit

    async def lose_event(run_id, event_type, payload):
        if event_type == "step_complete":
            raise LLMConfigurationError("simulated process exit after checkpoint")
        await original_emit(run_id, event_type, payload)

    monkeypatch.setattr(pipeline, "_emit", lose_event)
    with pytest.raises(LLMConfigurationError):
        await pipeline.run(_request(), run_id)
    assert "step_complete" not in _event_types(store, run_id)
    assert load_checkpoint(store, run_id)[0]["step_name"] == "strategy"
    _transition(store, run_id, "failed")
    _transition(store, run_id, "running")
    agents = Agents()
    result = await DynamicPipeline(store, llm=Planner(), runner=agents).run(_request(), run_id)
    assert agents.calls == ["writer", "editor"]
    assert result.total_prompt_tokens == 30
    assert result.plan[0].tool_events[0].preview == "evidence"


async def test_graph_allows_eight_steps_and_two_revisions_without_unbounded_routing(store):
    plan = _plan(("strategy", "researcher", "fact_checker", "strategy", "reviewer", "reviewer", "editor", "writer"))
    # Failing the last step forces the two revisions to revisit the final
    # pending node, while seven completed checkpoints are kept intact.
    attempts = 0

    async def fail_twice(agent):
        nonlocal attempts
        if agent == "writer":
            attempts += 1
            if attempts < 3:
                raise RuntimeError("temporary provider failure")

    planner = Planner([plan, None, None, plan, plan])
    agents = Agents(fail_twice)
    result = await DynamicPipeline(store, llm=planner, runner=agents).run(_request())
    assert result.status == "completed"
    assert len(result.plan) == 8
    assert result.revision_count == 2
    assert len(agents.calls) == 10
    assert result.total_prompt_tokens == 80
    assert _event_types(store, result.run_id).count("step_failed") == 2


async def test_runner_graph_does_not_save_again_after_finalize_commit_then_exception(store, monkeypatch):
    run_id = _create(store)
    agents, planner = Agents(), Planner()
    monkeypatch.setattr(runner, "create_litellm_client", lambda: planner)
    monkeypatch.setattr(dynamic_pipeline, "DynamicPipeline", lambda **kwargs: DynamicPipeline(runner=agents, **kwargs))
    original_complete = store.complete_run_with_content

    def commit_then_disconnect(*args, **kwargs):
        original_complete(*args, **kwargs)
        raise RuntimeError("connection lost after committed result")

    monkeypatch.setattr(store, "complete_run_with_content", commit_then_disconnect)
    await runner._run_pipeline_job_async(run_id, _request().model_dump(), store)
    await runner._run_pipeline_job_async(run_id, _request().model_dump(), store)
    assert store.get_run(run_id)["status"] == "completed"
    assert agents.calls == ["strategy", "writer", "editor"]
    assert len(store.list_contents()) == 1
    assert _event_types(store, run_id).count("run_complete") == 1
    assert "run_failed" not in _event_types(store, run_id)


async def test_duplicate_deliveries_do_not_start_a_second_live_graph(store, monkeypatch):
    run_id = _create(store)
    started, release = asyncio.Event(), asyncio.Event()

    async def wait_at_writer(agent):
        if agent == "writer":
            started.set()
            await release.wait()

    agents, planner = Agents(wait_at_writer), Planner()
    monkeypatch.setattr(runner, "create_litellm_client", lambda: planner)
    monkeypatch.setattr(dynamic_pipeline, "DynamicPipeline", lambda **kwargs: DynamicPipeline(runner=agents, **kwargs))
    first = asyncio.create_task(runner._run_pipeline_job_async(run_id, _request().model_dump(), store))
    await asyncio.wait_for(started.wait(), 5)
    owner = store.get_run(run_id)["worker_id"]
    try:
        await runner._run_pipeline_job_async(run_id, _request().model_dump(), store)
        assert store.get_run(run_id)["worker_id"] == owner
        assert agents.calls == ["strategy", "writer"]
    finally:
        release.set()
        await asyncio.wait_for(first, 5)
    assert agents.calls == ["strategy", "writer", "editor"]
    assert planner.calls == 1
    assert len(store.list_contents()) == 1
    assert _event_types(store, run_id).count("run_complete") == 1


@pytest.mark.parametrize("outcome", ["cancel", "lease_loss", "interrupt"])
async def test_real_graph_runner_stops_without_routing_failure_or_saving(store, monkeypatch, outcome):
    run_id = _create(store)
    started, stopped = asyncio.Event(), asyncio.Event()

    async def wait_at_writer(agent):
        if agent == "writer":
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

    agents = Agents(wait_at_writer)
    monkeypatch.setattr(config, "JOB_HEARTBEAT_INTERVAL_SECONDS", 0.02)
    monkeypatch.setattr(runner, "create_litellm_client", Planner)
    monkeypatch.setattr(dynamic_pipeline, "DynamicPipeline", lambda **kwargs: DynamicPipeline(runner=agents, **kwargs))
    task = asyncio.create_task(runner._run_pipeline_job_async(run_id, _request().model_dump(), store))
    await asyncio.wait_for(started.wait(), 5)
    assert len(load_checkpoint(store, run_id)) == 1
    if outcome == "cancel":
        _transition(store, run_id, "cancelled")
    elif outcome == "lease_loss":
        store.update_run(run_id, lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        assert store.fail_expired_run(run_id)
        _transition(store, run_id, "running")
        assert store.acquire_run_lease(run_id, "new-owner", 60)
    else:
        task.cancel()
    if outcome == "interrupt":
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)
    else:
        await asyncio.wait_for(task, 5)
    assert stopped.is_set()
    assert agents.calls == ["strategy", "writer"]
    assert store.list_contents() == []
    assert "step_failed" not in _event_types(store, run_id)
    assert "run_complete" not in _event_types(store, run_id)
    if outcome == "cancel":
        assert load_checkpoint(store, run_id) == []
        assert store.get_run(run_id)["status"] == "cancelled"
    elif outcome == "lease_loss":
        assert store.get_run(run_id)["worker_id"] == "new-owner"
        assert store.get_run(run_id)["status"] == "running"
        assert len(load_checkpoint(store, run_id)) == 1
    else:
        assert store.get_run(run_id)["status"] == "failed"


async def test_concurrent_graphs_keep_tenant_context_and_worker_tokens_separate(store):
    other_id = "33333333333333333333333333333333"
    with store._get_session() as session:
        session.add(User(id=other_id, username="graph_other_owner", password_hash="!", is_active=True))
        session.commit()
    other = store.for_user(other_id)
    first_id, second_id = _create(store, "first_graph"), _create(other, "second_graph")
    assert store.acquire_run_lease(first_id, "first-worker", 60)
    assert other.acquire_run_lease(second_id, "second-worker", 60)
    first, second = await asyncio.gather(
        DynamicPipeline(store, llm=Planner(), runner=Agents(prefix="FIRST "), worker_id="first-worker").run(
            _request(), first_id
        ),
        DynamicPipeline(other, llm=Planner(), runner=Agents(prefix="SECOND "), worker_id="second-worker").run(
            _request(), second_id
        ),
    )
    assert first.final_content.content == "FIRST editor output"
    assert second.final_content.content == "SECOND editor output"
    assert len(store.list_contents()) == len(other.list_contents()) == 1
    assert store.get_run(second_id) is None
    assert other.get_run(first_id) is None
    assert store.list_run_events(second_id) == other.list_run_events(first_id) == []
