"""Job state, worker leases, and per-step checkpoints.

Leases are the concurrency control for job execution: exactly one worker owns a
running job, and recovery keys off an expired ``lease_expires_at`` rather than
any explicit signal, because a SIGKILLed worker never releases anything.
Checkpoints share this module because a resume decision is meaningless without
the lease that authorises it."""

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_

from src.storage.models import (
    Job,
    RunStep,
)
from src.storage.repositories.base import RepositoryMixin

logger = logging.getLogger(__name__)


class JobRepositoryMixin(RepositoryMixin):
    """See :class:`src.storage.content_store.ContentStore` for the shared contract.

    Mixed into ``ContentStore``; ``session``/``_get_session`` come from the host
    class, which is why this is a mixin rather than a standalone object.
    """

    def create_job(
        self,
        job_id: str,
        job_type: str,
        payload: dict,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        session = self._get_session()
        try:
            now = datetime.now()
            job = Job(
                id=job_id,
                job_type=job_type,
                status="queued",
                payload=json.dumps(payload, ensure_ascii=False),
                provider=provider,
                model=model,
                progress=0,
                attempts=0,
                created_at=now,
                updated_at=now,
            )
            session.add(job)
            session.commit()
            return self._job_to_dict(job)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        session = self._get_session()
        try:
            job = session.query(Job).filter(Job.id == job_id).first()
            if not job:
                return None
            return self._job_to_dict(job)
        finally:
            session.close()

    def update_job(self, job_id: str, **fields) -> dict[str, Any] | None:
        session = self._get_session()
        try:
            job = session.query(Job).filter(Job.id == job_id).first()
            if not job:
                return None

            now = datetime.now()
            status = fields.pop("status", None)
            if status:
                job.status = status
                if status == "running" and not job.started_at:
                    job.started_at = now
                if status in {"completed", "failed", "cancelled"}:
                    job.completed_at = now

            if "payload" in fields:
                job.payload = json.dumps(fields.pop("payload"), ensure_ascii=False)
            if "result" in fields:
                result = fields.pop("result")
                job.result = json.dumps(result, ensure_ascii=False) if result is not None else None
            if "error" in fields:
                job.error = fields.pop("error")

            for key, value in fields.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            job.updated_at = now
            session.commit()
            return self._job_to_dict(job)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def start_job(self, job_id: str, attempts: int, progress: int = 5) -> dict[str, Any] | None:
        """Mark a queued/failed job as running without reviving a cancelled job."""
        session = self._get_session()
        try:
            job = session.query(Job).filter(Job.id == job_id, Job.status.in_(["queued", "failed"])).first()
            if not job:
                return None
            now = datetime.now()
            job.status = "running"
            job.progress = progress
            job.attempts = attempts
            job.started_at = job.started_at or now
            job.completed_at = None
            job.updated_at = now
            session.commit()
            return self._job_to_dict(job)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ------------------------------------------------------------------
    # P1-04 job leases
    #
    # Every method here mutates the lease with a single conditional UPDATE and
    # branches on the reported rowcount. A read-then-write version would let two
    # workers both observe a free lease and both proceed; the predicate has to
    # live in the WHERE clause so PostgreSQL resolves the race.
    def acquire_job_lease(
        self,
        job_id: str,
        worker_id: str,
        lease_duration_seconds: int,
    ) -> bool:
        """Claim the lease on a job. Returns False if another worker holds a live one.

        Acquisition succeeds when the lease is unheld, already owned by this same
        worker (re-entrant retry of the same job on the same worker), or expired.
        An expired lease is stealable precisely because its previous owner may have
        been SIGKILLed and can never release it.
        """
        session = self._get_session()
        try:
            now = datetime.now()
            expires_at = now + timedelta(seconds=lease_duration_seconds)
            claimed = (
                session.query(Job)
                .filter(
                    Job.id == job_id,
                    or_(
                        Job.worker_id.is_(None),
                        Job.worker_id == worker_id,
                        Job.lease_expires_at.is_(None),
                        Job.lease_expires_at < now,
                    ),
                )
                .update(
                    {
                        Job.worker_id: worker_id,
                        Job.lease_expires_at: expires_at,
                        Job.heartbeat_at: now,
                        Job.updated_at: now,
                    },
                    synchronize_session=False,
                )
            )
            session.commit()
            return claimed == 1
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def extend_job_lease(
        self,
        job_id: str,
        worker_id: str,
        lease_duration_seconds: int,
    ) -> bool:
        """Heartbeat: push the lease expiry out. False means the lease was lost.

        The ``worker_id`` predicate matters: if the reaper already reclaimed this
        job and another worker took it, this worker must learn that its lease is
        gone rather than silently extending someone else's.
        """
        session = self._get_session()
        try:
            now = datetime.now()
            expires_at = now + timedelta(seconds=lease_duration_seconds)
            extended = (
                session.query(Job)
                .filter(Job.id == job_id, Job.worker_id == worker_id)
                .update(
                    {
                        Job.lease_expires_at: expires_at,
                        Job.heartbeat_at: now,
                        Job.updated_at: now,
                    },
                    synchronize_session=False,
                )
            )
            session.commit()
            return extended == 1
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def release_job_lease(self, job_id: str, worker_id: str) -> bool:
        """Drop this worker's lease so a retry can start immediately.

        Scoped to ``worker_id`` so a slow worker whose lease was already reaped
        cannot clear the new owner's claim on its way out.
        """
        session = self._get_session()
        try:
            now = datetime.now()
            released = (
                session.query(Job)
                .filter(Job.id == job_id, Job.worker_id == worker_id)
                .update(
                    {
                        Job.worker_id: None,
                        Job.lease_expires_at: None,
                        Job.heartbeat_at: None,
                        Job.updated_at: now,
                    },
                    synchronize_session=False,
                )
            )
            session.commit()
            return released == 1
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def find_expired_lease_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        """Running jobs whose lease lapsed, i.e. the owning worker stopped heartbeating."""
        session = self._get_session()
        try:
            now = datetime.now()
            jobs = (
                session.query(Job)
                .filter(
                    Job.status == "running",
                    Job.lease_expires_at.isnot(None),
                    Job.lease_expires_at < now,
                )
                .order_by(Job.lease_expires_at)
                .limit(limit)
                .all()
            )
            return [self._job_to_dict(job) for job in jobs]
        finally:
            session.close()

    def reclaim_job_lease(self, job_id: str, worker_id: str) -> dict[str, Any] | None:
        """Move an expired-lease job back to ``queued`` so it can be retried.

        The ``lease_expires_at < now`` predicate stays in the WHERE clause: between
        the reaper's scan and this write the original worker may have recovered and
        heartbeated, and in that case the job must not be yanked out from under it.
        Attempts are left untouched — this is not an error, and reclaiming should
        not consume a retry budget that P1-03 owns.
        """
        session = self._get_session()
        try:
            now = datetime.now()
            reclaimed = (
                session.query(Job)
                .filter(
                    Job.id == job_id,
                    Job.status == "running",
                    Job.worker_id == worker_id,
                    Job.lease_expires_at.isnot(None),
                    Job.lease_expires_at < now,
                )
                .update(
                    {
                        Job.status: "queued",
                        Job.worker_id: None,
                        Job.lease_expires_at: None,
                        Job.heartbeat_at: None,
                        Job.completed_at: None,
                        Job.updated_at: now,
                    },
                    synchronize_session=False,
                )
            )
            session.commit()
            if reclaimed != 1:
                return None
            return self.get_job(job_id)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ------------------------------------------------------------------
    # P1-04 run-step checkpoints
    def save_run_step_checkpoint(
        self,
        run_id: str,
        step_index: int,
        step_name: str,
        status: str = "completed",
        result_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Upsert one step's checkpoint.

        Upsert rather than insert because a step may be checkpointed twice: once
        as ``running`` on entry and again as ``completed`` on exit, and because a
        retry that re-enters a step must not trip the unique constraint.
        """
        session = self._get_session()
        try:
            now = datetime.now()
            step = session.query(RunStep).filter(RunStep.run_id == run_id, RunStep.step_index == step_index).first()
            if step is None:
                step = RunStep(
                    run_id=run_id,
                    step_index=step_index,
                    step_name=step_name,
                    status=status,
                    started_at=now,
                )
                session.add(step)
            else:
                step.step_name = step_name
                step.status = status
                step.started_at = step.started_at or now
            if result_data is not None:
                step.result_data = json.dumps(result_data, ensure_ascii=False)
            step.completed_at = now if status == "completed" else None
            session.commit()
            return self._run_step_to_dict(step)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def load_run_step_checkpoints(self, run_id: str) -> list[dict[str, Any]]:
        """All persisted steps for a run, ordered by step index."""
        session = self._get_session()
        try:
            steps = session.query(RunStep).filter(RunStep.run_id == run_id).order_by(RunStep.step_index).all()
            return [self._run_step_to_dict(step) for step in steps]
        finally:
            session.close()

    def get_run_step_checkpoint(self, run_id: str, step_index: int) -> dict[str, Any] | None:
        session = self._get_session()
        try:
            step = session.query(RunStep).filter(RunStep.run_id == run_id, RunStep.step_index == step_index).first()
            return self._run_step_to_dict(step) if step else None
        finally:
            session.close()

    def get_run_resume_index(self, run_id: str) -> int:
        """Index of the first step that still needs to run.

        Returns the lowest index not recorded as ``completed``, so a gap left by a
        step that failed mid-run is re-executed rather than skipped. A run with no
        checkpoints resumes at 1, matching the 1-based step numbering the planner
        emits.
        """
        session = self._get_session()
        try:
            completed = {
                index
                for (index,) in session.query(RunStep.step_index)
                .filter(RunStep.run_id == run_id, RunStep.status == "completed")
                .all()
            }
            if not completed:
                return 1
            candidate = 1
            while candidate in completed:
                candidate += 1
            return candidate
        finally:
            session.close()

    def clear_run_step_checkpoints(self, run_id: str) -> int:
        """Drop a run's checkpoints once its result is durable."""
        session = self._get_session()
        try:
            deleted = session.query(RunStep).filter(RunStep.run_id == run_id).delete(synchronize_session=False)
            session.commit()
            return int(deleted)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _run_step_to_dict(step: RunStep) -> dict[str, Any]:
        return {
            "id": step.id,
            "run_id": step.run_id,
            "step_index": step.step_index,
            "step_name": step.step_name,
            "status": step.status,
            "result_data": json.loads(step.result_data) if step.result_data else None,
            "started_at": step.started_at.isoformat() if step.started_at else None,
            "completed_at": step.completed_at.isoformat() if step.completed_at else None,
        }

    def count_inflight_jobs(self, provider: str | None = None) -> int:
        session = self._get_session()
        try:
            query = session.query(Job).filter(Job.status.in_(["queued", "running"]))
            if provider:
                query = query.filter(Job.provider == provider)
            return query.count()
        finally:
            session.close()

    @staticmethod
    def _job_to_dict(job: Job) -> dict[str, Any]:
        return {
            "id": job.id,
            "user_id": job.user_id,
            "job_type": job.job_type,
            "status": job.status,
            "payload": json.loads(job.payload) if job.payload else {},
            "result": json.loads(job.result) if job.result else None,
            "error": job.error,
            "provider": job.provider,
            "model": job.model,
            "progress": job.progress or 0,
            "attempts": job.attempts or 0,
            "max_retries": job.max_retries or 5,
            "next_retry_at": job.next_retry_at.isoformat() if job.next_retry_at else None,
            "error_type": job.error_type,
            "worker_id": job.worker_id,
            "lease_expires_at": job.lease_expires_at.isoformat() if job.lease_expires_at else None,
            "heartbeat_at": job.heartbeat_at.isoformat() if job.heartbeat_at else None,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }
