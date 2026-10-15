"""Pipeline run records and their append-only event log.

The event log is what the SSE bridge reads, so appending an event and
transitioning run status must happen in one transaction -- see
``transition_run_and_append_event`` and ``complete_run_with_content``."""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.storage.models import (
    AgentRun,
    AgentRunEvent,
    Content,
    RunStep,
)
from src.storage.repositories.base import RepositoryMixin
from src.utils import config

logger = logging.getLogger(__name__)

# The SSE hub (src/api/services/run_event_hub.py) listens on this channel.
RUN_EVENTS_CHANNEL = "run_events"


class RunLeaseLostError(RuntimeError):
    """An expired or superseded pipeline attempt may no longer write anything."""


def assert_run_lease(run: AgentRun | None, worker_id: str | None, *, allow_finished: bool = False) -> None:
    """Validate a worker fence while the caller holds the parent run row lock."""
    if worker_id is None:
        return
    if run is None or run.worker_id != worker_id:
        raise RunLeaseLostError("Pipeline worker no longer owns this run")
    if allow_finished and run.status in {"completed", "cancelled"}:
        return
    if run.status != "running" or run.lease_expires_at is None or run.lease_expires_at <= datetime.now(timezone.utc):
        raise RunLeaseLostError("Pipeline execution lease expired or the run stopped")


def _notify_run_event(session: Session, run_id: str) -> None:
    """Wake SSE streams of this run once the surrounding transaction commits.

    PostgreSQL delivers a NOTIFY only on commit and drops it on rollback, so a
    stream can never be woken for an event it cannot read yet. That only holds on
    the session's own connection, which is why this does not open another one.

    It goes through the Core connection rather than ``session.execute`` because
    workspace sessions reject non-ORM statements to keep raw SQL away from tenant
    tables. This statement reads and writes no table, so there is nothing for
    that guard to scope; ``tenancy`` uses the same route for its own checks.
    """
    session.connection().execute(select(func.pg_notify(RUN_EVENTS_CHANNEL, run_id)))


class RunRepositoryMixin(RepositoryMixin):
    """See :class:`src.storage.content_store.ContentStore` for the shared contract.

    Mixed into ``ContentStore``; ``session``/``_get_session`` come from the host
    class, which is why this is a mixin rather than a standalone object.
    """

    def create_run(
        self,
        run_id: str,
        topic: str,
        content_type: str,
        style: str,
        provider: str | None = None,
        model: str | None = None,
        thread_id: str | None = None,
        request: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """``request`` is the JSON-safe request the run was started with.

        It is what a resume re-runs; a run created without it is not resumable.
        """
        session = self._get_session()
        try:
            run = AgentRun(
                id=run_id,
                thread_id=thread_id,
                topic=topic,
                content_type=content_type,
                style=style,
                provider=provider,
                model=model,
                request_json=json.dumps(request, ensure_ascii=False) if request is not None else None,
                status="running",
                lease_expires_at=datetime.now(timezone.utc)
                + timedelta(seconds=config.PIPELINE_DISPATCH_TIMEOUT_SECONDS),
            )
            session.add(run)
            session.commit()
            return self._agent_run_to_dict(run)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_run(self, run_id: str, *, expected_worker_id: str | None = None, **fields) -> dict[str, Any] | None:
        if fields.get("status") in {"completed", "failed", "cancelled"}:
            raise ValueError("Terminal run states must use transition_run_and_append_event()")
        session = self._get_session()
        try:
            run = session.query(AgentRun).filter(AgentRun.id == run_id).with_for_update().first()
            assert_run_lease(run, expected_worker_id)
            if not run:
                return None
            if "plan" in fields:
                run.plan_json = json.dumps(fields.pop("plan"), ensure_ascii=False)
            for key, value in fields.items():
                if hasattr(run, key):
                    setattr(run, key, value)
            if fields.get("status") in {"completed", "failed", "cancelled"} or run.status in {
                "completed",
                "failed",
                "cancelled",
            }:
                run.completed_at = run.completed_at or datetime.now()
            session.commit()
            return self._agent_run_to_dict(run)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        session = self._get_session()
        try:
            run = session.query(AgentRun).filter(AgentRun.id == run_id).first()
            return self._agent_run_to_dict(run) if run else None
        finally:
            session.close()

    def list_runs(
        self,
        thread_id: str | None = None,
        limit: int = 30,
        *,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        session = self._get_session()
        try:
            query = session.query(AgentRun)
            if thread_id:
                query = query.filter(AgentRun.thread_id == thread_id)
            if status:
                query = query.filter(AgentRun.status == status)
            runs = query.order_by(AgentRun.created_at.desc(), AgentRun.id.desc()).limit(limit).all()
            return [self._agent_run_to_dict(run) for run in runs]
        finally:
            session.close()

    def append_run_event(
        self, run_id: str, event_type: str, payload: dict[str, Any], *, expected_worker_id: str | None = None
    ) -> int | None:
        """Append a non-terminal event while the run is still active.

        The run-row lock serializes this check with terminal CAS transitions. If
        cancellation/completion/failure already won, the event is discarded so
        the terminal event remains the durable end of the stream.
        """
        session = self._get_session()
        try:
            run = session.query(AgentRun).filter(AgentRun.id == run_id).with_for_update().first()
            assert_run_lease(run, expected_worker_id)
            if not run:
                raise LookupError(f"Run {run_id} was not found")
            if run.status != "running":
                session.rollback()
                return None
            seq = int(run.next_event_seq or 1)
            run.next_event_seq = seq + 1
            session.add(
                AgentRunEvent(
                    user_id=run.user_id,
                    run_id=run_id,
                    seq=seq,
                    event_type=event_type,
                    payload=json.dumps(payload, ensure_ascii=False),
                )
            )
            _notify_run_event(session, run_id)
            session.commit()
            return seq
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def complete_run_with_content(
        self,
        run_id: str,
        *,
        payload: dict[str, Any],
        content_fields: dict[str, Any] | None,
        plan: list[dict[str, Any]],
        revision_count: int,
        total_prompt_tokens: int,
        total_completion_tokens: int,
        total_cost: float,
        expected_worker_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Atomically persist final content, complete the run, and append its event.

        Cancellation and completion serialize on the run row. If cancellation
        already won, no ``agent_final`` content row is inserted.
        """
        session = self._get_session()
        try:
            run = (
                session.query(AgentRun)
                .filter(AgentRun.id == run_id, AgentRun.status == "running")
                .with_for_update()
                .first()
            )
            assert_run_lease(run, expected_worker_id)
            if not run:
                return None

            saved_content_id: int | None = None
            if content_fields:
                content = Content(**content_fields)
                session.add(content)
                session.flush()
                saved_content_id = content.id

            event_payload = json.loads(json.dumps(payload, ensure_ascii=False))
            event_payload["saved_content_id"] = saved_content_id
            run.plan_json = json.dumps(plan, ensure_ascii=False)
            run.revision_count = revision_count
            run.total_prompt_tokens = total_prompt_tokens
            run.total_completion_tokens = total_completion_tokens
            run.total_cost = total_cost
            run.saved_content_id = saved_content_id
            run.status = "completed"
            run.lease_expires_at = None
            run.completed_at = run.completed_at or datetime.now()
            seq = int(run.next_event_seq or 1)
            run.next_event_seq = seq + 1
            session.add(
                AgentRunEvent(
                    user_id=run.user_id,
                    run_id=run_id,
                    seq=seq,
                    event_type="run_complete",
                    payload=json.dumps(event_payload, ensure_ascii=False),
                )
            )
            _notify_run_event(session, run_id)
            session.commit()
            result = self._agent_run_to_dict(run)
            result["event_seq"] = seq
            return result
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def transition_run_and_append_event(
        self,
        run_id: str,
        *,
        expected_statuses: set[str] | tuple[str, ...],
        new_status: str,
        event_type: str,
        payload: dict[str, Any],
        expected_worker_id: str | None = None,
        require_expired_lease: bool = False,
        **fields: Any,
    ) -> dict[str, Any] | None:
        """Compare-and-set a run state and append its event in one transaction.

        Returns ``None`` when another actor already moved the run out of an
        expected state. This is the only supported path for terminal run state
        changes, preventing duplicate terminal events during cancel/fail races.
        """
        session = self._get_session()
        try:
            query = session.query(AgentRun).filter(AgentRun.id == run_id, AgentRun.status.in_(tuple(expected_statuses)))
            if require_expired_lease:
                query = query.filter(AgentRun.lease_expires_at <= datetime.now(timezone.utc))
            run = query.with_for_update().first()
            assert_run_lease(run, expected_worker_id)
            if not run:
                return None
            if require_expired_lease and (
                run.lease_expires_at is None or run.lease_expires_at > datetime.now(timezone.utc)
            ):
                return None
            if "plan" in fields:
                run.plan_json = json.dumps(fields.pop("plan"), ensure_ascii=False)
            for key, value in fields.items():
                if hasattr(run, key):
                    setattr(run, key, value)
            run.status = new_status
            if new_status in {"completed", "failed", "cancelled"}:
                run.completed_at = run.completed_at or datetime.now()
                run.lease_expires_at = None
                if new_status == "cancelled":
                    # A worker may already be stopped or fenced from further
                    # writes, so cancellation owns checkpoint cleanup itself.
                    session.query(RunStep).filter(RunStep.run_id == run_id).delete(synchronize_session=False)
            else:
                # Leaving a terminal state (a resume): the old end time is no longer true.
                run.completed_at = None
                run.worker_id = None
                run.heartbeat_at = None
                run.lease_expires_at = datetime.now(timezone.utc) + timedelta(
                    seconds=config.PIPELINE_DISPATCH_TIMEOUT_SECONDS
                )
            seq = int(run.next_event_seq or 1)
            run.next_event_seq = seq + 1
            session.add(
                AgentRunEvent(
                    user_id=run.user_id,
                    run_id=run_id,
                    seq=seq,
                    event_type=event_type,
                    payload=json.dumps(payload, ensure_ascii=False),
                )
            )
            _notify_run_event(session, run_id)
            session.commit()
            result = self._agent_run_to_dict(run)
            result["event_seq"] = seq
            return result
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def acquire_run_lease(self, run_id: str, worker_id: str, duration_seconds: int) -> bool:
        """Claim one delivery once; expired attempts must first fail and resume."""
        session = self._get_session()
        try:
            now = datetime.now(timezone.utc)
            claimed = (
                session.query(AgentRun)
                .filter(
                    AgentRun.id == run_id,
                    AgentRun.status == "running",
                    AgentRun.worker_id.is_(None),
                    AgentRun.lease_expires_at > now,
                )
                .update(
                    {
                        AgentRun.worker_id: worker_id,
                        AgentRun.heartbeat_at: now,
                        AgentRun.lease_expires_at: now + timedelta(seconds=duration_seconds),
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

    def extend_run_lease(self, run_id: str, worker_id: str, duration_seconds: int) -> bool:
        """An expired lease cannot be revived, even before the reaper finds it."""
        session = self._get_session()
        try:
            now = datetime.now(timezone.utc)
            changed = (
                session.query(AgentRun)
                .filter(
                    AgentRun.id == run_id,
                    AgentRun.status == "running",
                    AgentRun.worker_id == worker_id,
                    AgentRun.lease_expires_at > now,
                )
                .update(
                    {
                        AgentRun.heartbeat_at: now,
                        AgentRun.lease_expires_at: now + timedelta(seconds=duration_seconds),
                    },
                    synchronize_session=False,
                )
            )
            session.commit()
            return changed == 1
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def find_expired_run_leases(self, limit: int = 50) -> list[dict[str, Any]]:
        session = self._get_session()
        try:
            runs = (
                session.query(AgentRun)
                .filter(AgentRun.status == "running", AgentRun.lease_expires_at <= datetime.now(timezone.utc))
                .order_by(AgentRun.lease_expires_at)
                .limit(limit)
                .all()
            )
            return [self._agent_run_to_dict(run) for run in runs]
        finally:
            session.close()

    def fail_expired_run(self, run_id: str) -> dict[str, Any] | None:
        error = "Pipeline execution lease expired; resume the run to continue from its checkpoints"
        return self.transition_run_and_append_event(
            run_id,
            expected_statuses={"running"},
            require_expired_lease=True,
            new_status="failed",
            event_type="run_failed",
            payload={"error": error, "code": "worker_lost"},
            error=error,
        )

    def list_run_events(
        self,
        run_id: str,
        after_seq: int = 0,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        session = self._get_session()
        try:
            events = (
                session.query(AgentRunEvent)
                .filter(AgentRunEvent.run_id == run_id, AgentRunEvent.seq > after_seq)
                .order_by(AgentRunEvent.seq)
                .limit(limit)
                .all()
            )
            return [
                {
                    "seq": e.seq,
                    "event_type": e.event_type,
                    "payload": e.payload,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in events
            ]
        finally:
            session.close()

    @staticmethod
    def _agent_run_to_dict(run: AgentRun) -> dict[str, Any]:
        return {
            "id": run.id,
            "user_id": run.user_id,
            "thread_id": run.thread_id,
            "topic": run.topic,
            "content_type": run.content_type,
            "style": run.style,
            "provider": run.provider,
            "model": run.model,
            "plan": json.loads(run.plan_json) if run.plan_json else [],
            "request": json.loads(run.request_json) if run.request_json else None,
            "revision_count": run.revision_count or 0,
            "total_prompt_tokens": run.total_prompt_tokens or 0,
            "total_completion_tokens": run.total_completion_tokens or 0,
            "total_cost": run.total_cost or 0.0,
            "saved_content_id": run.saved_content_id,
            "status": run.status,
            "error": run.error,
            "next_event_seq": run.next_event_seq or 1,
            "worker_id": run.worker_id,
            "lease_expires_at": run.lease_expires_at.isoformat() if run.lease_expires_at else None,
            "heartbeat_at": run.heartbeat_at.isoformat() if run.heartbeat_at else None,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }
