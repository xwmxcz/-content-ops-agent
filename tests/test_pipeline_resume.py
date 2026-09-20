"""Resuming a failed pipeline run from its step checkpoints.

What is pinned here is the money: a step whose result is already durable must
not be executed, or billed, a second time, and a run that produced no content
must end as ``failed`` (and therefore resumable) instead of completing with the
topic saved as the article.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.schemas.agent import PipelineRunRequest
from src.api.services.dynamic_pipeline import DynamicPipeline
from src.jobs.checkpoint import load_checkpoint, save_step_checkpoint
from src.llm.litellm_client import LLMConfigurationError
from src.models import ContentStyle, ContentType

PLAN = json.dumps(
    [
        {"index": 1, "agent_id": "strategy", "description": "Plan", "instruction": "go", "inputs_from": []},
        {"index": 2, "agent_id": "writer", "description": "Draft", "instruction": "go", "inputs_from": [1]},
        {"index": 3, "agent_id": "editor", "description": "Polish", "instruction": "go", "inputs_from": [2]},
    ]
)
OUTPUTS = {"strategy": "STRATEGY", "writer": "DRAFT", "editor": "FINAL"}


class _Planner:
    """Answers the first call with the plan and declines every revision."""

    def __init__(self):
        self.calls = 0

    async def generate_from_prompts(self, **kwargs):
        self.calls += 1
        return PLAN if self.calls == 1 else "null"


class _Runner:
    """Scripted sub-agents; ``broken`` maps an agent to the error it raises."""

    def __init__(self, broken: dict[str, Exception] | None = None):
        self.broken = broken or {}
        self.calls: list[str] = []
        self.prompts: dict[str, str] = {}

    async def run(
        self, spec, user_prompt, provider, model, max_tokens=2048, token_sink=None, tool_sink=None, allowed_tools=None
    ):
        self.calls.append(spec.id)
        self.prompts[spec.id] = user_prompt
        if spec.id in self.broken:
            raise self.broken[spec.id]
        return OUTPUTS[spec.id], 10, 5, 12, 0.0


def _request(**overrides) -> PipelineRunRequest:
    payload = {
        "topic": "周末徒步路线推荐",
        "content_type": ContentType.XIAOHONGSHU,
        "style": ContentStyle.PROFESSIONAL,
        "keywords": ["徒步"],
        "provider": "siliconflow",
        "model": "Qwen/Qwen2.5-7B-Instruct",
        "length": "long",
    }
    payload.update(overrides)
    return PipelineRunRequest(**payload)


def _events(store, run_id):
    return [(e["event_type"], json.loads(e["payload"])) for e in store.list_run_events(run_id, limit=500)]


def _mark_failed(store, run_id, error="boom"):
    """What the job wrapper does when ``run()`` raises."""
    return store.transition_run_and_append_event(
        run_id,
        expected_statuses={"running"},
        new_status="failed",
        event_type="run_failed",
        payload={"error": error},
        error=error,
    )


def _mark_resumed(store, run_id):
    """What POST /runs/{id}/resume does before it enqueues the run again."""
    return store.transition_run_and_append_event(
        run_id,
        expected_statuses={"failed"},
        new_status="running",
        event_type="run_resumed",
        payload={},
        error=None,
    )


async def _fail_at_writer(store, planner) -> str:
    """A run that completes ``strategy`` and then dies in ``writer``."""
    store.create_run(run_id="run_resume", topic="t", content_type="xiaohongshu", style="professional")
    broken = _Runner({"writer": LLMConfigurationError("API key rejected")})
    with pytest.raises(LLMConfigurationError):
        await DynamicPipeline(store=store, llm=planner, runner=broken).run(_request(), run_id="run_resume")
    assert broken.calls == ["strategy", "writer"]
    assert _mark_failed(store, "run_resume") is not None
    return "run_resume"


# ---------- the pipeline ----------------------------------------------------


async def test_resume_executes_only_the_steps_without_a_checkpoint(store):
    planner = _Planner()
    run_id = await _fail_at_writer(store, planner)
    assert _mark_resumed(store, run_id) is not None

    healthy = _Runner()
    response = await DynamicPipeline(store=store, llm=planner, runner=healthy).run(_request(), run_id=run_id)

    assert healthy.calls == ["writer", "editor"], "a checkpointed step was executed again"
    assert planner.calls == 1, "the plan was made again instead of being restored"
    assert response.status == "completed"
    assert response.final_content.content == "FINAL"
    assert [s.status for s in response.plan] == ["completed"] * 3
    # The restored step still feeds the steps that depend on it...
    assert "STRATEGY" in healthy.prompts["writer"]
    # ...and still counts towards what the run cost.
    assert response.total_prompt_tokens == 30
    assert store.get_run(run_id)["total_prompt_tokens"] == 30


async def test_resume_tells_clients_what_was_already_done(store):
    planner = _Planner()
    run_id = await _fail_at_writer(store, planner)
    _mark_resumed(store, run_id)
    await DynamicPipeline(store=store, llm=planner, runner=_Runner()).run(_request(), run_id=run_id)

    events = _events(store, run_id)
    resumed_at = [kind for kind, _ in events].index("run_resumed")
    after = events[resumed_at + 1 :]

    kind, payload = after[0]
    assert kind == "plan_ready"
    first = payload["plan"][0]
    assert (first["status"], first["output"]) == ("completed", "STRATEGY")
    assert [s["status"] for s in payload["plan"][1:]] == ["pending", "pending"]
    assert [p["index"] for k, p in after if k == "step_start"] == [2, 3]
    assert after[-1][0] == "run_complete"


async def test_checkpoints_are_dropped_once_the_result_is_durable(store):
    planner = _Planner()
    run_id = await _fail_at_writer(store, planner)
    assert [c["step_index"] for c in load_checkpoint(store, run_id)] == [1]

    _mark_resumed(store, run_id)
    await DynamicPipeline(store=store, llm=planner, runner=_Runner()).run(_request(), run_id=run_id)

    assert load_checkpoint(store, run_id) == []


async def test_a_checkpoint_from_a_different_plan_is_not_trusted(store):
    planner = _Planner()
    run_id = await _fail_at_writer(store, planner)
    # Index 2 belongs to the writer in this plan; a checkpoint claiming a
    # researcher finished there describes some other plan.
    save_step_checkpoint(store, run_id, 2, "researcher", {"output": "NOT A DRAFT"})
    _mark_resumed(store, run_id)

    healthy = _Runner()
    response = await DynamicPipeline(store=store, llm=planner, runner=healthy).run(_request(), run_id=run_id)

    assert healthy.calls == ["writer", "editor"]
    assert response.plan[1].output == "DRAFT"


async def test_a_run_without_content_fails_instead_of_saving_the_topic(store):
    outage = RuntimeError("provider unavailable")
    broken = _Runner({"writer": outage, "editor": outage})

    response = await DynamicPipeline(store=store, llm=_Planner(), runner=broken).run(_request())

    assert response.status == "failed"
    assert response.saved_content_id is None
    run = store.get_run(response.run_id)
    assert run["status"] == "failed"
    assert "no content" in run["error"]
    assert store.list_contents() == [], "a run with no draft saved something as its article"
    kind, payload = _events(store, response.run_id)[-1]
    assert (kind, payload["code"]) == ("run_failed", "no_content")
    # What did succeed is kept, which is the point of failing rather than completing.
    assert [c["step_name"] for c in load_checkpoint(store, response.run_id)] == ["strategy"]


async def test_a_failed_step_runs_again_on_resume(store):
    outage = RuntimeError("provider unavailable")
    planner = _Planner()
    first = await DynamicPipeline(store=store, llm=planner, runner=_Runner({"writer": outage, "editor": outage})).run(
        _request()
    )
    assert first.status == "failed"
    _mark_resumed(store, first.run_id)

    healthy = _Runner()
    response = await DynamicPipeline(store=store, llm=planner, runner=healthy).run(_request(), run_id=first.run_id)

    assert healthy.calls == ["writer", "editor"]
    assert response.status == "completed"
    assert response.final_content.content == "FINAL"
    assert len(store.list_contents()) == 1


async def test_the_run_remembers_the_request_it_was_started_with(store):
    response = await DynamicPipeline(store=store, llm=_Planner(), runner=_Runner()).run(
        _request(length="long", use_web_search=False)
    )

    stored = store.get_run(response.run_id)["request"]
    assert stored["length"] == "long"
    assert stored["use_web_search"] is False
    assert PipelineRunRequest(**stored) == _request(length="long", use_web_search=False)


# ---------- the endpoint ----------------------------------------------------


@pytest.fixture
def client(store, monkeypatch):
    from src.api.dependencies import get_store as real_get_store

    enqueued: list[tuple[str, dict]] = []

    def record(run_id, request_data, database_url, background_tasks=None):
        enqueued.append((run_id, request_data))

    monkeypatch.setattr("src.api.routes.agent.enqueue_pipeline_run", record)
    app.dependency_overrides[real_get_store] = lambda: store
    try:
        yield TestClient(app), enqueued
    finally:
        app.dependency_overrides.pop(real_get_store, None)


def _failed_run(store, run_id="run_api", *, with_request=True):
    request = _request().model_dump(mode="json") if with_request else None
    store.create_run(run_id=run_id, topic="t", content_type="xiaohongshu", style="professional", request=request)
    _mark_failed(store, run_id, error="API key rejected")
    return request


def test_resume_reopens_the_run_and_enqueues_its_original_request(store, client):
    http, enqueued = client
    request = _failed_run(store)

    response = http.post("/api/agent/runs/run_api/resume")

    assert response.status_code == 202
    assert response.json()["run_id"] == "run_api"
    assert enqueued == [("run_api", request)]
    run = store.get_run("run_api")
    assert (run["status"], run["error"], run["completed_at"]) == ("running", None, None)
    assert [e["event_type"] for e in store.list_run_events("run_api")] == ["run_failed", "run_resumed"]


def test_resuming_twice_enqueues_once(store, client):
    http, enqueued = client
    _failed_run(store)

    assert http.post("/api/agent/runs/run_api/resume").status_code == 202
    second = http.post("/api/agent/runs/run_api/resume")

    assert second.status_code == 409
    assert len(enqueued) == 1


def test_only_a_failed_run_can_be_resumed(store, client):
    http, enqueued = client
    store.create_run(
        run_id="run_live",
        topic="t",
        content_type="xiaohongshu",
        style="professional",
        request=_request().model_dump(mode="json"),
    )

    assert http.post("/api/agent/runs/run_live/resume").status_code == 409
    assert http.post("/api/agent/runs/run_missing/resume").status_code == 404
    assert enqueued == []


def test_a_run_from_before_requests_were_stored_is_refused_not_guessed(store, client):
    http, enqueued = client
    _failed_run(store, with_request=False)

    response = http.post("/api/agent/runs/run_api/resume")

    assert response.status_code == 409
    assert "start a new run" in response.json()["detail"]
    assert store.get_run("run_api")["status"] == "failed"
    assert enqueued == []


def test_a_queue_failure_puts_the_run_back_to_failed(store, client, monkeypatch):
    from src.jobs.queue import JobQueueError

    http, _ = client
    _failed_run(store)

    def refuse(*args, **kwargs):
        raise JobQueueError("Redis is unreachable")

    monkeypatch.setattr("src.api.routes.agent.enqueue_pipeline_run", refuse)

    response = http.post("/api/agent/runs/run_api/resume")

    assert response.status_code == 503
    run = store.get_run("run_api")
    assert (run["status"], run["error"]) == ("failed", "Redis is unreachable")
    assert store.list_run_events("run_api")[-1]["event_type"] == "run_failed"
