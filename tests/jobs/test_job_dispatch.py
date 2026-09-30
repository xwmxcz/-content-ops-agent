"""Exercise runner dispatch decisions without a database or a live queue."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.jobs.runner import _run_pipeline_job_async, current_worker_id, run_job_async
from src.storage import ContentStore


@pytest.fixture
def dispatch_store():
    store = Mock(spec=ContentStore)
    job = {
        "id": "job_dispatch",
        "job_type": "content_generation",
        "status": "queued",
        "attempts": 0,
        "max_retries": 3,
        "next_retry_at": None,
    }
    store.get_job.return_value = job
    store.acquire_job_lease.return_value = True
    store.start_job.return_value = {**job, "status": "running"}
    return store


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type,attempts", [("permanent", 1), ("transient", 3)])
async def test_terminal_failure_is_not_reexecuted(dispatch_store, error_type, attempts):
    dispatch_store.get_job.return_value.update(status="failed", error_type=error_type, attempts=attempts)

    with patch("src.jobs.runner._execute_job", new_callable=AsyncMock) as execute:
        await run_job_async("job_dispatch", dispatch_store)

    execute.assert_not_awaited()
    dispatch_store.acquire_job_lease.assert_not_called()
    dispatch_store.start_job.assert_not_called()
    dispatch_store.update_job.assert_not_called()


@pytest.mark.asyncio
async def test_future_retry_is_not_executed(dispatch_store):
    dispatch_store.get_job.return_value.update(
        status="failed",
        attempts=1,
        next_retry_at=(datetime.now() + timedelta(hours=1)).isoformat(),
    )

    with patch("src.jobs.runner._execute_job", new_callable=AsyncMock) as execute:
        await run_job_async("job_dispatch", dispatch_store)

    execute.assert_not_awaited()
    dispatch_store.acquire_job_lease.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("status,attempts", [("queued", 0), ("queued", 3), ("failed", 1)])
async def test_queued_job_and_due_retry_execute(dispatch_store, status, attempts):
    dispatch_store.get_job.return_value.update(
        status=status,
        attempts=attempts,
        next_retry_at=(datetime.now() - timedelta(seconds=1)).isoformat() if status == "failed" else None,
    )

    with patch("src.jobs.runner._execute_job", new_callable=AsyncMock) as execute:
        execute.return_value = {"content": "ok"}
        await run_job_async("job_dispatch", dispatch_store)

    execute.assert_awaited_once()
    worker_id = dispatch_store.acquire_job_lease.call_args.args[1]
    assert worker_id.startswith(current_worker_id() + ":")
    dispatch_store.start_job.assert_called_once_with(
        "job_dispatch", attempts=attempts + 1, progress=5, expected_worker_id=worker_id
    )
    dispatch_store.update_job.assert_called_once_with(
        "job_dispatch",
        expected_statuses={"running"},
        expected_worker_id=worker_id,
        status="completed",
        progress=100,
        result={"content": "ok"},
        error=None,
        error_type=None,
        next_retry_at=None,
    )
    dispatch_store.release_job_lease.assert_called_once()


@pytest.mark.parametrize("run_status", ["completed", "failed", "cancelled", None])
async def test_pipeline_delivery_does_not_restart_terminal_or_missing_runs(dispatch_store, run_status):
    dispatch_store.get_run.return_value = {"status": run_status} if run_status else None

    with patch("src.api.services.dynamic_pipeline.DynamicPipeline") as pipeline:
        # Invalid data is deliberate: terminal deliveries must be discarded
        # before validation, client construction, or any planner/LLM call.
        await _run_pipeline_job_async("run_dispatch", {}, dispatch_store)

    pipeline.assert_not_called()
    dispatch_store.transition_run_and_append_event.assert_not_called()


async def test_cancelled_job_delivery_does_not_execute(dispatch_store):
    dispatch_store.get_job.return_value["status"] = "cancelled"

    with patch("src.jobs.runner._execute_job", new_callable=AsyncMock) as execute:
        await run_job_async("job_dispatch", dispatch_store)

    execute.assert_not_awaited()
    dispatch_store.acquire_job_lease.assert_not_called()


async def test_retry_does_not_get_scheduled_after_terminal_write_loses_race(dispatch_store):
    dispatch_store.update_job.return_value = None
    with (
        patch("src.jobs.runner._execute_job", new_callable=AsyncMock, side_effect=TimeoutError("timeout")),
        patch("src.jobs.queue.requeue_job_with_delay") as schedule,
    ):
        await run_job_async("job_dispatch", dispatch_store)

    schedule.assert_not_called()
    assert dispatch_store.update_job.call_args.kwargs["expected_statuses"] == {"running"}
    assert (
        dispatch_store.update_job.call_args.kwargs["expected_worker_id"]
        == dispatch_store.acquire_job_lease.call_args.args[1]
    )


async def test_queue_failure_clears_retry_timestamp_so_pollers_can_stop(dispatch_store):
    with (
        patch("src.jobs.runner._execute_job", new_callable=AsyncMock, side_effect=TimeoutError("timeout")),
        patch("src.jobs.queue.requeue_job_with_delay", side_effect=RuntimeError("queue unavailable")),
    ):
        await run_job_async("job_dispatch", dispatch_store)

    terminal_update = dispatch_store.update_job.call_args.kwargs
    assert terminal_update["expected_statuses"] == {"failed"}
    assert terminal_update["expected_worker_id"] == dispatch_store.acquire_job_lease.call_args.args[1]
    assert terminal_update["next_retry_at"] is None
    assert "retry could not be scheduled" in terminal_update["error"]
