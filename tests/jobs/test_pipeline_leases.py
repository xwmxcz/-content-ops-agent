"""Real PostgreSQL fencing, abandoned-run recovery, and checkpoint resumption."""

from __future__ import annotations

import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_store
from src.api.main import app
from src.api.schemas.agent import PipelineRunRequest
from src.api.services import dynamic_pipeline
from src.api.services.dynamic_pipeline import DynamicPipeline
from src.jobs import reaper, runner
from src.jobs.checkpoint import load_checkpoint, save_step_checkpoint
from src.storage import ContentStore
from src.storage.models import User
from src.storage.repositories.run_repository import RunLeaseLostError
from src.utils import config


def _request():
    return PipelineRunRequest(topic="hiking guide", content_type="blog", style="professional", provider="siliconflow")


def _create(store, run_id="run_lease", engine=None):
    request_data = _request().model_dump(mode="json")
    if engine is not None:
        request_data["_pipeline_engine"] = engine
    store.create_run(
        run_id=run_id,
        topic="hiking guide",
        content_type="blog",
        style="professional",
        request=request_data,
    )
    return run_id


def _expire(store, run_id):
    store.update_run(run_id, lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))


def _resume(store, run_id):
    return store.transition_run_and_append_event(
        run_id, expected_statuses={"failed"}, new_status="running", event_type="run_resumed", payload={}, error=None
    )


def _complete(store, run_id, worker_id):
    return store.complete_run_with_content(
        run_id,
        expected_worker_id=worker_id,
        payload={"run_id": run_id},
        content_fields={"title": "Final", "content": "Final text", "content_type": "blog", "style": "professional"},
        plan=[],
        revision_count=0,
        total_prompt_tokens=1,
        total_completion_tokens=1,
        total_cost=0,
    )


def test_pipeline_delivery_claim_has_exactly_one_concurrent_winner(store):
    run_id = _create(store)
    before = store.get_run(run_id)
    assert before["worker_id"] is None
    assert datetime.fromisoformat(before["lease_expires_at"]) > datetime.now(timezone.utc)
    barrier = threading.Barrier(8)

    def claim(index):
        barrier.wait()
        return store.acquire_run_lease(run_id, f"delivery_{index}", 60)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(claim, range(8)))

    assert sum(results) == 1
    owner = f"delivery_{results.index(True)}"
    assert store.get_run(run_id)["worker_id"] == owner
    assert store.acquire_run_lease(run_id, owner, 60) is False, "even the same delivery must not execute twice"


@pytest.mark.parametrize("claimed", [False, True])
def test_reaper_fails_unclaimed_and_abandoned_runs_and_preserves_checkpoints(store, claimed):
    run_id = _create(store)
    if claimed:
        assert store.acquire_run_lease(run_id, "dead", 60)
        save_step_checkpoint(store, run_id, 1, "strategy", {"output": "KEEP"}, expected_worker_id="dead")
    _expire(store, run_id)

    preview = reaper.reap_expired_leases(store)
    assert preview["pipeline_found"] == 1
    assert store.get_run(run_id)["status"] == "running"
    assert store.acquire_run_lease(run_id, "too_late", 60) is False
    result = reaper.reap_expired_leases(store, dry_run=False)
    assert result["pipeline_failed"] == 1
    assert store.get_run(run_id)["status"] == "failed"
    assert len(load_checkpoint(store, run_id)) == int(claimed)
    assert reaper.reap_expired_leases(store, dry_run=False)["pipeline_failed"] == 0
    events = store.list_run_events(run_id)
    assert [e["event_type"] for e in events] == ["run_failed"]
    assert json.loads(events[0]["payload"])["code"] == "worker_lost"

    resumed = _resume(store, run_id)
    assert resumed["worker_id"] is None
    assert resumed["heartbeat_at"] is None
    assert resumed["completed_at"] is None
    assert store.acquire_run_lease(run_id, "new", 60)


def test_heartbeat_extends_live_lease_and_cannot_revive_an_expired_one(store):
    run_id = _create(store)
    assert store.acquire_run_lease(run_id, "worker", 60)
    before = store.get_run(run_id)
    assert store.extend_run_lease(run_id, "worker", 180)
    assert store.get_run(run_id)["lease_expires_at"] > before["lease_expires_at"]
    assert store.extend_run_lease(run_id, "intruder", 180) is False
    assert store.fail_expired_run(run_id) is None
    _expire(store, run_id)
    assert store.extend_run_lease(run_id, "worker", 180) is False


@pytest.mark.parametrize("resumed", [False, True])
def test_expired_worker_cannot_modify_any_run_artifact_even_after_resume(store, resumed):
    run_id = _create(store)
    assert store.acquire_run_lease(run_id, "old", 60)
    save_step_checkpoint(store, run_id, 1, "strategy", {"output": "KEEP"}, expected_worker_id="old")
    _expire(store, run_id)
    if resumed:
        store.fail_expired_run(run_id)
        _resume(store, run_id)
        assert store.acquire_run_lease(run_id, "new", 60)

    before = store.get_run(run_id)
    operations = [
        lambda: store.update_run(run_id, expected_worker_id="old", plan=[{"index": 99}]),
        lambda: store.append_run_event(run_id, "step_token", {"delta": "stale"}, expected_worker_id="old"),
        lambda: save_step_checkpoint(store, run_id, 1, "strategy", {"output": "STALE"}, expected_worker_id="old"),
        lambda: store.clear_run_step_checkpoints(run_id, expected_worker_id="old"),
        lambda: _complete(store, run_id, "old"),
        lambda: store.transition_run_and_append_event(
            run_id,
            expected_statuses={"running"},
            expected_worker_id="old",
            new_status="failed",
            event_type="run_failed",
            payload={"error": "stale"},
        ),
    ]
    for operation in operations:
        with pytest.raises(RunLeaseLostError):
            operation()

    assert store.get_run(run_id) == before
    assert load_checkpoint(store, run_id)[0]["result_data"]["output"] == "KEEP"
    assert store.list_contents() == []


def test_concurrent_completion_can_save_only_one_content_row(store):
    run_id = _create(store)
    assert store.acquire_run_lease(run_id, "owner", 60)
    barrier = threading.Barrier(2)

    def complete():
        barrier.wait()
        try:
            return _complete(store, run_id, "owner")
        except RunLeaseLostError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(complete) for _ in range(2)]
        assert sum(future.result() is not None for future in futures) == 1
    assert len(store.list_contents()) == 1
    assert [e["event_type"] for e in store.list_run_events(run_id)] == ["run_complete"]


async def test_duplicate_queue_deliveries_execute_only_one_pipeline(store, monkeypatch):
    run_id = _create(store)
    started, release = asyncio.Event(), asyncio.Event()
    executions = []

    async def execute(self, request, run_id):
        executions.append(self.worker_id)
        started.set()
        await release.wait()
        _complete(store, run_id, self.worker_id)

    monkeypatch.setattr(DynamicPipeline, "run", execute)
    first = asyncio.create_task(runner._run_pipeline_job_async(run_id, _request().model_dump(), store))
    await asyncio.wait_for(started.wait(), timeout=5)
    await runner._run_pipeline_job_async(run_id, _request().model_dump(), store)
    release.set()
    await asyncio.wait_for(first, timeout=5)
    assert len(executions) == 1
    assert len(store.list_contents()) == 1


async def test_monitor_heartbeats_and_cancels_work_after_lease_loss(store, monkeypatch):
    run_id = _create(store)
    monkeypatch.setattr(config, "JOB_HEARTBEAT_INTERVAL_SECONDS", 0.02)
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def execute(self, request, run_id):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(DynamicPipeline, "run", execute)
    task = asyncio.create_task(runner._run_pipeline_job_async(run_id, _request().model_dump(), store))
    await asyncio.wait_for(started.wait(), timeout=5)
    first_heartbeat = store.get_run(run_id)["heartbeat_at"]
    for _ in range(100):
        await asyncio.sleep(0.02)
        if store.get_run(run_id)["heartbeat_at"] != first_heartbeat:
            break
    assert store.get_run(run_id)["heartbeat_at"] != first_heartbeat
    _expire(store, run_id)
    assert store.fail_expired_run(run_id)
    _resume(store, run_id)
    assert store.acquire_run_lease(run_id, "replacement", 60)
    await asyncio.wait_for(task, timeout=5)
    assert cancelled.is_set()
    assert store.get_run(run_id)["status"] == "running"
    assert store.get_run(run_id)["worker_id"] == "replacement"


async def test_graceful_worker_interruption_fails_the_owned_run(store, monkeypatch):
    run_id = _create(store)
    started = asyncio.Event()

    async def execute(self, request, run_id):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(DynamicPipeline, "run", execute)
    task = asyncio.create_task(runner._run_pipeline_job_async(run_id, _request().model_dump(), store))
    await asyncio.wait_for(started.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert store.get_run(run_id)["status"] == "failed"
    assert store.list_run_events(run_id)[-1]["event_type"] == "run_failed"


@pytest.mark.parametrize("engine", [None, "langgraph_v1"])
async def test_expired_pipeline_resumes_from_durable_step_without_replanning(store, monkeypatch, engine):
    run_id = _create(store, engine=engine)

    class Planner:
        calls = 0

        async def generate_from_prompts(self, **kwargs):
            self.calls += 1
            return json.dumps(
                [
                    {
                        "index": i,
                        "agent_id": agent,
                        "description": agent,
                        "instruction": "go",
                        "inputs_from": [i - 1] if i > 1 else [],
                    }
                    for i, agent in enumerate(("strategy", "writer", "editor"), 1)
                ]
            )

    class Agents:
        def __init__(self, expires=False):
            self.expires = expires
            self.calls = []

        async def run(self, spec, **kwargs):
            self.calls.append(spec.id)
            if self.expires and spec.id == "writer":
                _expire(store, run_id)
            return f"{spec.id} OUTPUT", 2, 3, 1, 0.0

    planner, broken, healthy = Planner(), Agents(expires=True), Agents()
    monkeypatch.setattr(runner, "create_litellm_client", lambda: planner)
    monkeypatch.setattr(dynamic_pipeline, "DynamicPipeline", lambda **kwargs: DynamicPipeline(runner=broken, **kwargs))
    await runner._run_pipeline_job_async(run_id, _request().model_dump(), store)
    assert broken.calls == ["strategy", "writer"]
    assert [s["step_name"] for s in load_checkpoint(store, run_id)] == ["strategy"]
    assert reaper.reap_expired_leases(store, dry_run=False)["pipeline_failed"] == 1
    _resume(store, run_id)

    monkeypatch.setattr(dynamic_pipeline, "DynamicPipeline", lambda **kwargs: DynamicPipeline(runner=healthy, **kwargs))
    await runner._run_pipeline_job_async(run_id, _request().model_dump(), store)

    assert healthy.calls == ["writer", "editor"]
    assert planner.calls == 1
    assert store.get_run(run_id)["status"] == "completed"
    assert store.get_run(run_id)["total_prompt_tokens"] == 6
    assert len(store.list_contents()) == 1
    assert load_checkpoint(store, run_id) == []
    events = [e["event_type"] for e in store.list_run_events(run_id)]
    failure = events.index("run_failed")
    assert events[failure + 1 : failure + 3] == ["run_resumed", "plan_ready"]
    assert events[-1] == "run_complete"


def test_system_reaper_creates_expiry_events_in_each_runs_own_workspace(store):
    other_id = "33333333333333333333333333333333"
    with store._get_session() as session:
        session.add(User(id=other_id, username="other_worker_owner", password_hash="!", is_active=True))
        session.commit()
    other = store.for_user(other_id)
    _expire(store, _create(store, "first_run"))
    _expire(other, _create(other, "second_run"))
    system = ContentStore(database_url=store.database_url, initialize_schema=False)
    try:
        result = reaper.reap_expired_leases(system, dry_run=False)
    finally:
        system.engine.dispose()
    assert result["pipeline_failed"] == 2
    assert store.get_run("first_run")["status"] == "failed"
    assert other.get_run("second_run")["status"] == "failed"
    assert store.get_run("second_run") is None
    assert other.list_run_events("first_run") == []
    assert store.list_run_events("first_run")[0]["event_type"] == "run_failed"
    assert other.list_run_events("second_run")[0]["event_type"] == "run_failed"


async def test_cancelling_real_worker_cleans_checkpoints_and_stops_execution(store, monkeypatch):
    run_id = _create(store)
    monkeypatch.setattr(config, "JOB_HEARTBEAT_INTERVAL_SECONDS", 0.02)
    started, stopped = asyncio.Event(), asyncio.Event()

    async def execute(self, request, run_id):
        save_step_checkpoint(store, run_id, 1, "strategy", {"output": "done"}, expected_worker_id=self.worker_id)
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    monkeypatch.setattr(DynamicPipeline, "run", execute)
    task = asyncio.create_task(runner._run_pipeline_job_async(run_id, _request().model_dump(), store))
    await asyncio.wait_for(started.wait(), timeout=5)
    store.transition_run_and_append_event(
        run_id, expected_statuses={"running"}, new_status="cancelled", event_type="run_cancelled", payload={}
    )
    assert load_checkpoint(store, run_id) == [], "cleanup cannot depend on the stopped worker"
    await asyncio.wait_for(task, timeout=5)
    assert stopped.is_set()
    assert store.get_run(run_id)["status"] == "cancelled"
    assert store.list_contents() == []
    assert [event["event_type"] for event in store.list_run_events(run_id)] == ["run_cancelled"]


@pytest.mark.parametrize("endpoint", ["snapshot", "stream", "resume"])
def test_user_read_and_resume_recover_expired_runs_without_a_reaper(store, monkeypatch, endpoint):
    run_id = _create(store)
    _expire(store, run_id)
    monkeypatch.setattr("src.api.routes.agent.enqueue_pipeline_run", lambda *args: None)
    app.dependency_overrides[get_store] = lambda: store
    try:
        with TestClient(app) as client:
            if endpoint == "resume":
                response = client.post(f"/api/agent/runs/{run_id}/resume")
                assert response.status_code == 202
                assert store.get_run(run_id)["status"] == "running"
            elif endpoint == "stream":
                response = client.get(f"/api/agent/runs/{run_id}/stream")
                assert response.status_code == 200
                assert "event: run_failed" in response.text
                assert '"code": "worker_lost"' in response.text
            else:
                response = client.get(f"/api/agent/runs/{run_id}")
                assert response.status_code == 200
                assert response.json()["status"] == "failed"
    finally:
        app.dependency_overrides.pop(get_store, None)
    assert store.list_run_events(run_id)[0]["event_type"] == "run_failed"
