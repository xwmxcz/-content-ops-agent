"""Exercise runner dispatch decisions without a database or a live queue."""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.jobs.runner import run_job_async
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
    dispatch_store.get_job.return_value.update(
        status="failed", error_type=error_type, attempts=attempts
    )

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
        next_retry_at=(datetime.now() - timedelta(seconds=1)).isoformat()
        if status == "failed" else None,
    )

    with patch("src.jobs.runner._execute_job", new_callable=AsyncMock) as execute:
        execute.return_value = {"content": "ok"}
        await run_job_async("job_dispatch", dispatch_store)

    execute.assert_awaited_once()
    dispatch_store.start_job.assert_called_once_with(
        "job_dispatch", attempts=attempts + 1, progress=5
    )
    dispatch_store.update_job.assert_called_once_with(
        "job_dispatch", status="completed", progress=100, result={"content": "ok"}, error=None
    )
    dispatch_store.release_job_lease.assert_called_once()
