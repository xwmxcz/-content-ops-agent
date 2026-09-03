"""Tests for P1-04: lease-based job deduplication, recovery, and checkpoints."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from src.jobs import checkpoint, reaper
from src.jobs.runner import current_worker_id, run_job_async
from src.storage import ContentStore
from src.utils import config


def _make_job(store: ContentStore, job_type: str = "content_generation") -> str:
    job = store.create_job(
        job_id=f"job_{uuid.uuid4().hex[:12]}",
        job_type=job_type,
        payload={"topic": "test", "content_type": "blog"},
        provider="openai",
        model="gpt-4",
    )
    return job["id"]


def _expire_lease(store: ContentStore, job_id: str, seconds_ago: int = 30) -> None:
    """Force a held lease to look lapsed, as a SIGKILLed worker would leave it."""
    store.update_job(
        job_id,
        status="running",
        lease_expires_at=datetime.now() - timedelta(seconds=seconds_ago),
    )


class TestLeaseAcquisition:
    """Only one worker may hold a live lease on a job."""

    def test_acquire_lease_on_unheld_job(self, store: ContentStore):
        job_id = _make_job(store)
        assert store.acquire_job_lease(job_id, "worker-1", 300) is True

        job = store.get_job(job_id)
        assert job["worker_id"] == "worker-1"
        assert job["lease_expires_at"] is not None
        assert job["heartbeat_at"] is not None

    def test_second_worker_cannot_acquire_live_lease(self, store: ContentStore):
        job_id = _make_job(store)
        assert store.acquire_job_lease(job_id, "worker-1", 300) is True
        assert store.acquire_job_lease(job_id, "worker-2", 300) is False

        # Ownership must not change on a refused acquisition.
        assert store.get_job(job_id)["worker_id"] == "worker-1"

    def test_same_worker_reacquire_is_allowed(self, store: ContentStore):
        """A retry landing on the same worker must not deadlock against itself."""
        job_id = _make_job(store)
        assert store.acquire_job_lease(job_id, "worker-1", 300) is True
        assert store.acquire_job_lease(job_id, "worker-1", 300) is True

    def test_expired_lease_is_stealable(self, store: ContentStore):
        """An expired lease is the only signal a SIGKILLed worker leaves behind."""
        job_id = _make_job(store)
        store.acquire_job_lease(job_id, "worker-dead", 300)
        _expire_lease(store, job_id)

        assert store.acquire_job_lease(job_id, "worker-new", 300) is True
        assert store.get_job(job_id)["worker_id"] == "worker-new"

    def test_lease_expiry_is_pushed_into_the_future(self, store: ContentStore):
        job_id = _make_job(store)
        store.acquire_job_lease(job_id, "worker-1", 120)

        expires_at = datetime.fromisoformat(store.get_job(job_id)["lease_expires_at"])
        delta = (expires_at - datetime.now()).total_seconds()
        assert 100 < delta <= 120

    def test_acquire_on_missing_job_returns_false(self, store: ContentStore):
        assert store.acquire_job_lease("job_does_not_exist", "worker-1", 300) is False

    def test_concurrent_acquisition_yields_exactly_one_winner(self, store: ContentStore):
        """The unique winner must come from the database, not application ordering."""
        job_id = _make_job(store)
        results = [store.acquire_job_lease(job_id, f"worker-{i}", 300) for i in range(8)]
        assert sum(results) == 1
        assert results[0] is True


class TestLeaseHeartbeat:
    """Heartbeats keep a live lease alive and reveal a lost one."""

    def test_extend_lease_pushes_expiry_out(self, store: ContentStore):
        job_id = _make_job(store)
        store.acquire_job_lease(job_id, "worker-1", 60)
        first = datetime.fromisoformat(store.get_job(job_id)["lease_expires_at"])

        assert store.extend_job_lease(job_id, "worker-1", 600) is True
        second = datetime.fromisoformat(store.get_job(job_id)["lease_expires_at"])
        assert second > first

    def test_extend_updates_heartbeat_timestamp(self, store: ContentStore):
        job_id = _make_job(store)
        store.acquire_job_lease(job_id, "worker-1", 300)
        store.update_job(job_id, heartbeat_at=datetime.now() - timedelta(seconds=120))
        stale = datetime.fromisoformat(store.get_job(job_id)["heartbeat_at"])

        store.extend_job_lease(job_id, "worker-1", 300)
        fresh = datetime.fromisoformat(store.get_job(job_id)["heartbeat_at"])
        assert fresh > stale

    def test_non_owner_cannot_extend(self, store: ContentStore):
        """A worker whose lease was reaped must learn it, not extend the new owner's."""
        job_id = _make_job(store)
        store.acquire_job_lease(job_id, "worker-1", 300)
        assert store.extend_job_lease(job_id, "worker-2", 300) is False

    def test_extend_after_lease_stolen_reports_loss(self, store: ContentStore):
        job_id = _make_job(store)
        store.acquire_job_lease(job_id, "worker-old", 300)
        _expire_lease(store, job_id)
        store.acquire_job_lease(job_id, "worker-new", 300)

        assert store.extend_job_lease(job_id, "worker-old", 300) is False
        assert store.extend_job_lease(job_id, "worker-new", 300) is True


class TestLeaseRelease:
    """Releasing frees the job for immediate retry, scoped to the owner."""

    def test_release_clears_lease_fields(self, store: ContentStore):
        job_id = _make_job(store)
        store.acquire_job_lease(job_id, "worker-1", 300)

        assert store.release_job_lease(job_id, "worker-1") is True
        job = store.get_job(job_id)
        assert job["worker_id"] is None
        assert job["lease_expires_at"] is None
        assert job["heartbeat_at"] is None

    def test_non_owner_release_is_refused(self, store: ContentStore):
        """A late worker must not clear the lease of whoever took over."""
        job_id = _make_job(store)
        store.acquire_job_lease(job_id, "worker-1", 300)

        assert store.release_job_lease(job_id, "worker-2") is False
        assert store.get_job(job_id)["worker_id"] == "worker-1"

    def test_released_job_is_immediately_acquirable(self, store: ContentStore):
        job_id = _make_job(store)
        store.acquire_job_lease(job_id, "worker-1", 300)
        store.release_job_lease(job_id, "worker-1")

        assert store.acquire_job_lease(job_id, "worker-2", 300) is True


class TestExpiredLeaseDiscovery:
    """The reaper's scan must find abandoned jobs and only those."""

    def test_finds_running_job_with_lapsed_lease(self, store: ContentStore):
        job_id = _make_job(store)
        store.acquire_job_lease(job_id, "worker-dead", 300)
        _expire_lease(store, job_id)

        assert [job["id"] for job in store.find_expired_lease_jobs()] == [job_id]

    def test_ignores_live_lease(self, store: ContentStore):
        job_id = _make_job(store)
        store.acquire_job_lease(job_id, "worker-1", 300)
        store.update_job(job_id, status="running")

        assert store.find_expired_lease_jobs() == []

    def test_ignores_queued_job_without_lease(self, store: ContentStore):
        _make_job(store)
        assert store.find_expired_lease_jobs() == []

    def test_ignores_completed_job_with_lapsed_lease(self, store: ContentStore):
        """A finished job is not abandoned work, even if its lease was never cleared."""
        job_id = _make_job(store)
        store.acquire_job_lease(job_id, "worker-1", 300)
        store.update_job(
            job_id,
            status="completed",
            lease_expires_at=datetime.now() - timedelta(seconds=60),
        )

        assert store.find_expired_lease_jobs() == []

    def test_scan_respects_limit(self, store: ContentStore):
        for _ in range(5):
            job_id = _make_job(store)
            store.acquire_job_lease(job_id, "worker-dead", 300)
            _expire_lease(store, job_id)

        assert len(store.find_expired_lease_jobs(limit=3)) == 3


class TestLeaseReclaim:
    """Reclaiming requeues abandoned work without charging a retry."""

    def test_reclaim_returns_job_to_queued(self, store: ContentStore):
        job_id = _make_job(store)
        store.acquire_job_lease(job_id, "worker-dead", 300)
        _expire_lease(store, job_id)

        reclaimed = store.reclaim_job_lease(job_id, "worker-dead")
        assert reclaimed is not None
        assert reclaimed["status"] == "queued"
        assert reclaimed["worker_id"] is None
        assert reclaimed["lease_expires_at"] is None

    def test_reclaim_does_not_consume_a_retry_attempt(self, store: ContentStore):
        """Worker eviction is not a job error; it must not burn the retry budget."""
        job_id = _make_job(store)
        store.acquire_job_lease(job_id, "worker-dead", 300)
        store.update_job(job_id, attempts=2)
        _expire_lease(store, job_id)

        reclaimed = store.reclaim_job_lease(job_id, "worker-dead")
        assert reclaimed["attempts"] == 2

    def test_reclaim_refused_when_lease_is_still_live(self, store: ContentStore):
        """A worker that heartbeated after the scan keeps its job."""
        job_id = _make_job(store)
        store.acquire_job_lease(job_id, "worker-1", 300)
        store.update_job(job_id, status="running")

        assert store.reclaim_job_lease(job_id, "worker-1") is None
        assert store.get_job(job_id)["status"] == "running"

    def test_reclaim_refused_for_a_different_worker(self, store: ContentStore):
        job_id = _make_job(store)
        store.acquire_job_lease(job_id, "worker-1", 300)
        _expire_lease(store, job_id)

        assert store.reclaim_job_lease(job_id, "worker-other") is None


class TestReaperService:
    """End-to-end sweep behaviour."""

    def test_dry_run_reports_without_mutating(self, store: ContentStore):
        job_id = _make_job(store)
        store.acquire_job_lease(job_id, "worker-dead", 300)
        _expire_lease(store, job_id)

        result = reaper.reap_expired_leases(store, dry_run=True)
        assert result["found"] == 1
        assert result["reclaimed"] == 0
        assert store.get_job(job_id)["status"] == "running"

    def test_execute_reclaims_expired_jobs(self, store: ContentStore):
        job_id = _make_job(store)
        store.acquire_job_lease(job_id, "worker-dead", 300)
        _expire_lease(store, job_id)

        result = reaper.reap_expired_leases(store, dry_run=False)
        assert result["found"] == 1
        assert result["reclaimed"] == 1
        assert store.get_job(job_id)["status"] == "queued"

    def test_sweep_is_a_noop_when_nothing_expired(self, store: ContentStore):
        job_id = _make_job(store)
        store.acquire_job_lease(job_id, "worker-1", 300)
        store.update_job(job_id, status="running")

        result = reaper.reap_expired_leases(store, dry_run=False)
        assert result == {"found": 0, "reclaimed": 0, "requeued": 0, "job_ids": []}
        assert store.get_job(job_id)["status"] == "running"

    def test_sweep_recovers_several_jobs(self, store: ContentStore):
        job_ids = []
        for _ in range(3):
            job_id = _make_job(store)
            store.acquire_job_lease(job_id, "worker-dead", 300)
            _expire_lease(store, job_id)
            job_ids.append(job_id)

        result = reaper.reap_expired_leases(store, dry_run=False)
        assert result["reclaimed"] == 3
        assert all(store.get_job(jid)["status"] == "queued" for jid in job_ids)

    @pytest.mark.asyncio
    async def test_reaper_loop_stops_on_event(self, store: ContentStore):
        job_id = _make_job(store)
        store.acquire_job_lease(job_id, "worker-dead", 300)
        _expire_lease(store, job_id)

        stop = asyncio.Event()
        task = asyncio.ensure_future(run_reaper_with_stop(store, stop))
        await asyncio.sleep(0.2)
        stop.set()
        await asyncio.wait_for(task, timeout=5)

        assert store.get_job(job_id)["status"] == "queued"


async def run_reaper_with_stop(store: ContentStore, stop: asyncio.Event) -> None:
    await reaper.run_reaper_loop(store, interval_seconds=1, stop_event=stop)


class TestCheckpoints:
    """Checkpoints let a retry resume rather than replay committed work."""

    def test_empty_run_resumes_at_first_step(self, store: ContentStore):
        assert checkpoint.get_resume_point(store, "run_none") == 1

    def test_resume_point_follows_completed_steps(self, store: ContentStore):
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        checkpoint.save_step_checkpoint(store, run_id, 1, "researcher", {"facts": []})
        checkpoint.save_step_checkpoint(store, run_id, 2, "writer", {"draft": "x"})

        assert checkpoint.get_resume_point(store, run_id) == 3

    def test_gap_is_reexecuted_not_skipped(self, store: ContentStore):
        """A hole from a failed step must be rerun, or its work is silently lost."""
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        checkpoint.save_step_checkpoint(store, run_id, 1, "researcher", {"facts": []})
        checkpoint.save_step_checkpoint(store, run_id, 3, "editor", {"final": "y"})

        assert checkpoint.get_resume_point(store, run_id) == 2

    def test_running_step_does_not_count_as_completed(self, store: ContentStore):
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        checkpoint.save_step_checkpoint(store, run_id, 1, "writer", None, status="running")

        assert checkpoint.is_step_completed(store, run_id, 1) is False
        assert checkpoint.get_resume_point(store, run_id) == 1

    def test_step_result_round_trips(self, store: ContentStore):
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        payload = {"facts": ["a", "b"], "count": 2}
        checkpoint.save_step_checkpoint(store, run_id, 1, "researcher", payload)

        assert checkpoint.get_step_result(store, run_id, 1) == payload

    def test_incomplete_step_exposes_no_result(self, store: ContentStore):
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        checkpoint.save_step_checkpoint(store, run_id, 1, "writer", {"partial": True}, status="running")

        assert checkpoint.get_step_result(store, run_id, 1) is None

    def test_resaving_a_step_does_not_duplicate_it(self, store: ContentStore):
        """UNIQUE(run_id, step_index) makes the checkpoint write itself idempotent."""
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        checkpoint.save_step_checkpoint(store, run_id, 1, "writer", None, status="running")
        checkpoint.save_step_checkpoint(store, run_id, 1, "writer", {"draft": "final"})

        steps = checkpoint.load_checkpoint(store, run_id)
        assert len(steps) == 1
        assert steps[0]["status"] == "completed"
        assert steps[0]["result_data"] == {"draft": "final"}

    def test_checkpoints_are_scoped_per_run(self, store: ContentStore):
        run_a = f"run_{uuid.uuid4().hex[:8]}"
        run_b = f"run_{uuid.uuid4().hex[:8]}"
        checkpoint.save_step_checkpoint(store, run_a, 1, "writer", {"r": "a"})

        assert checkpoint.get_resume_point(store, run_a) == 2
        assert checkpoint.get_resume_point(store, run_b) == 1

    def test_completed_steps_lookup_excludes_running(self, store: ContentStore):
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        checkpoint.save_step_checkpoint(store, run_id, 1, "researcher", {"r": 1})
        checkpoint.save_step_checkpoint(store, run_id, 2, "writer", None, status="running")

        completed = checkpoint.load_completed_steps(store, run_id)
        assert set(completed) == {1}

    def test_clear_removes_only_that_run(self, store: ContentStore):
        run_a = f"run_{uuid.uuid4().hex[:8]}"
        run_b = f"run_{uuid.uuid4().hex[:8]}"
        checkpoint.save_step_checkpoint(store, run_a, 1, "writer", {"r": "a"})
        checkpoint.save_step_checkpoint(store, run_b, 1, "writer", {"r": "b"})

        assert checkpoint.clear_checkpoints(store, run_a) == 1
        assert checkpoint.get_resume_point(store, run_a) == 1
        assert checkpoint.get_resume_point(store, run_b) == 2

    def test_resume_summary_reports_state(self, store: ContentStore):
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        checkpoint.save_step_checkpoint(store, run_id, 1, "researcher", {"r": 1})
        checkpoint.save_step_checkpoint(store, run_id, 2, "writer", {"r": 2})

        summary = checkpoint.resume_summary(store, run_id)
        assert summary["completed_steps"] == [1, 2]
        assert summary["resume_from_index"] == 3
        assert summary["total_checkpoints"] == 2


class TestRunnerLeaseIntegration:
    """The runner must take, hold, and release the lease around execution."""

    @pytest.mark.asyncio
    async def test_successful_run_releases_the_lease(self, store: ContentStore):
        job_id = _make_job(store)

        with patch("src.jobs.runner._execute_job", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"content": "ok"}
            await run_job_async(job_id, store)

        job = store.get_job(job_id)
        assert job["status"] == "completed"
        assert job["worker_id"] is None
        assert job["lease_expires_at"] is None

    @pytest.mark.asyncio
    async def test_lease_is_held_during_execution(self, store: ContentStore):
        job_id = _make_job(store)
        observed: dict[str, object] = {}

        async def capture(*args, **kwargs):
            snapshot = store.get_job(job_id)
            observed["worker_id"] = snapshot["worker_id"]
            observed["lease_expires_at"] = snapshot["lease_expires_at"]
            return {"content": "ok"}

        with patch("src.jobs.runner._execute_job", new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = capture
            await run_job_async(job_id, store)

        assert observed["worker_id"] == current_worker_id()
        assert observed["lease_expires_at"] is not None

    @pytest.mark.asyncio
    async def test_job_held_by_another_worker_is_skipped(self, store: ContentStore):
        """Deduplication: a second runner must not execute a leased job."""
        job_id = _make_job(store)
        store.acquire_job_lease(job_id, "worker-elsewhere", 300)

        with patch("src.jobs.runner._execute_job", new_callable=AsyncMock) as mock_execute:
            await run_job_async(job_id, store)
            mock_execute.assert_not_called()

        job = store.get_job(job_id)
        assert job["status"] == "queued"
        assert job["worker_id"] == "worker-elsewhere"

    @pytest.mark.asyncio
    async def test_failed_run_releases_the_lease(self, store: ContentStore):
        """A stuck lease after failure would block every future retry."""
        job_id = _make_job(store)

        with patch("src.jobs.runner._execute_job", new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = TimeoutError("transient")
            await run_job_async(job_id, store)

        job = store.get_job(job_id)
        assert job["status"] == "failed"
        assert job["worker_id"] is None
        assert job["lease_expires_at"] is None

    @pytest.mark.asyncio
    async def test_expired_lease_job_can_be_rerun_after_reclaim(self, store: ContentStore):
        """The full recovery path: abandoned job is reaped, then executes."""
        job_id = _make_job(store)
        store.acquire_job_lease(job_id, "worker-dead", 300)
        _expire_lease(store, job_id)

        assert reaper.reap_expired_leases(store, dry_run=False)["reclaimed"] == 1

        with patch("src.jobs.runner._execute_job", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"content": "recovered"}
            await run_job_async(job_id, store)

        job = store.get_job(job_id)
        assert job["status"] == "completed"
        assert job["result"] == {"content": "recovered"}

    @pytest.mark.asyncio
    async def test_lost_lease_aborts_without_writing_job_state(
        self, store: ContentStore, monkeypatch
    ):
        """Another worker owns the job now; writing a result here would clobber it."""
        monkeypatch.setattr(config, "JOB_HEARTBEAT_INTERVAL_SECONDS", 1)
        job_id = _make_job(store)

        async def slow_steal(*args, **kwargs):
            # Simulate the reaper handing this job to a different worker mid-run.
            store.update_job(job_id, worker_id="worker-other")
            await asyncio.sleep(10)
            return {"content": "should never be written"}

        with patch("src.jobs.runner._execute_job", new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = slow_steal
            await asyncio.wait_for(run_job_async(job_id, store), timeout=15)

        job = store.get_job(job_id)
        assert job["status"] == "running"
        assert job["result"] is None
        assert job["worker_id"] == "worker-other"

    @pytest.mark.asyncio
    async def test_cancellation_stops_execution_and_keeps_cancelled_state(
        self, store: ContentStore, monkeypatch
    ):
        monkeypatch.setattr(config, "JOB_HEARTBEAT_INTERVAL_SECONDS", 1)
        job_id = _make_job(store)

        async def slow_cancel(*args, **kwargs):
            store.update_job(job_id, status="cancelled")
            await asyncio.sleep(10)
            return {"content": "should never be written"}

        with patch("src.jobs.runner._execute_job", new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = slow_cancel
            await asyncio.wait_for(run_job_async(job_id, store), timeout=15)

        job = store.get_job(job_id)
        assert job["status"] == "cancelled"
        assert job["result"] is None

    @pytest.mark.asyncio
    async def test_heartbeat_extends_lease_during_long_run(
        self, store: ContentStore, monkeypatch
    ):
        monkeypatch.setattr(config, "JOB_HEARTBEAT_INTERVAL_SECONDS", 1)
        monkeypatch.setattr(config, "JOB_LEASE_DURATION_SECONDS", 60)
        job_id = _make_job(store)
        seen: list[str] = []

        async def slow_ok(*args, **kwargs):
            seen.append(store.get_job(job_id)["lease_expires_at"])
            await asyncio.sleep(2.5)
            seen.append(store.get_job(job_id)["lease_expires_at"])
            return {"content": "ok"}

        with patch("src.jobs.runner._execute_job", new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = slow_ok
            await asyncio.wait_for(run_job_async(job_id, store), timeout=20)

        assert datetime.fromisoformat(seen[1]) > datetime.fromisoformat(seen[0])
        assert store.get_job(job_id)["status"] == "completed"


class TestRetryInteraction:
    """P1-04 must not disturb the P1-03 retry contract."""

    @pytest.mark.asyncio
    async def test_early_retry_is_skipped_without_taking_a_lease(self, store: ContentStore):
        job_id = _make_job(store)
        store.update_job(
            job_id,
            status="failed",
            next_retry_at=datetime.now() + timedelta(hours=1),
            error_type="transient",
        )

        await run_job_async(job_id, store)

        job = store.get_job(job_id)
        assert job["status"] == "failed"
        assert job["worker_id"] is None

    @pytest.mark.asyncio
    async def test_due_retry_acquires_lease_and_runs(self, store: ContentStore):
        job_id = _make_job(store)
        store.update_job(
            job_id,
            status="failed",
            next_retry_at=datetime.now() - timedelta(seconds=1),
            error_type="transient",
            attempts=1,
        )

        with patch("src.jobs.runner._execute_job", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"content": "retried"}
            await run_job_async(job_id, store)

        job = store.get_job(job_id)
        assert job["status"] == "completed"
        assert job["attempts"] == 2
        assert job["worker_id"] is None
