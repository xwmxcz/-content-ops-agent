"""The durable ledger that makes a keyed write replayable instead of repeatable."""

import json
import logging
from datetime import datetime
from typing import Any

from src.storage.models import (
    IdempotencyRecord,
)
from src.storage.repositories.base import RepositoryMixin
from src.utils import metrics
from src.utils.structured_logging import log_idempotency_event

logger = logging.getLogger(__name__)


class IdempotencyRepositoryMixin(RepositoryMixin):
    """See :class:`src.storage.content_store.ContentStore` for the shared contract.

    Mixed into ``ContentStore``; ``session``/``_get_session`` come from the host
    class, which is why this is a mixin rather than a standalone object.
    """

    def claim_idempotency_key(
        self,
        *,
        scope: str,
        key: str,
        args: dict[str, Any],
        external_request_id: str | None = None,
    ) -> dict[str, Any]:
        """Claim ``(user_id, scope, key)`` or report this user's prior outcome.

        The claim is an INSERT guarded by the unique constraint, so two racing
        requests cannot both win: PostgreSQL rejects the loser, which then reads
        the existing row and reacts to its status. An application-level
        "SELECT then INSERT if absent" would leave a window where both callers see
        no row and both write.

        Returns a dict with ``outcome``:

        - ``claimed``: caller owns this attempt and must do the work, then call
          :meth:`complete_idempotency_key`.
        - ``replay``: the work already completed; ``result`` holds the original
          result and the caller must not write again.

        Raises :class:`DuplicateRequestInFlight` when another attempt holds the
        key, and :class:`IdempotencyKeyConflict` when the key is reused with
        different arguments.
        """
        from sqlalchemy.exc import IntegrityError

        from src.utils.canonical import args_hash
        from src.utils.idempotency import DuplicateRequestInFlight, IdempotencyKeyConflict

        digest = args_hash(args)
        session = self._get_session()
        try:
            record = IdempotencyRecord(
                scope=scope,
                idempotency_key=key,
                args_hash=digest,
                status="in_progress",
                external_request_id=external_request_id,
                created_at=datetime.now(),
            )
            session.add(record)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
            else:
                # P2-01: Metrics and logging
                metrics.idempotency_requests_total.labels(scope=scope, outcome="claimed").inc()
                log_idempotency_event(logger, "claimed", scope, key, record_id=record.id, args_hash=digest)
                return {
                    "outcome": "claimed",
                    "record_id": record.id,
                    "scope": scope,
                    "key": key,
                    "external_request_id": record.external_request_id,
                }

            # Lost the insert race, or this is a retry. Lock the surviving row so
            # a concurrent completion cannot change status under this read.
            existing = (
                session.query(IdempotencyRecord)
                .filter(
                    IdempotencyRecord.scope == scope,
                    IdempotencyRecord.idempotency_key == key,
                )
                .with_for_update()
                .first()
            )
            if existing is None:
                # The row was deleted between the failed insert and this read.
                raise DuplicateRequestInFlight(f"Idempotency key for {scope} could not be claimed; retry the request")
            # Check args compatibility based on current status:
            # - failed: retryable with any args (previous attempt didn't succeed)
            # - completed/in_progress: args must match (can't change a success or in-flight request)
            if existing.status != "failed" and existing.args_hash != digest:
                # P2-01: Metrics and logging
                metrics.idempotency_conflicts_total.labels(scope=scope).inc()
                metrics.idempotency_requests_total.labels(scope=scope, outcome="conflict").inc()
                log_idempotency_event(
                    logger, "conflict", scope, key, record_id=existing.id, args_hash=digest, conflict=True
                )
                raise IdempotencyKeyConflict(f"Idempotency key was already used for {scope} with different arguments")
            if existing.status == "completed":
                # P2-01: Metrics and logging
                metrics.idempotency_requests_total.labels(scope=scope, outcome="replay").inc()
                metrics.idempotency_replay_rate.labels(scope=scope).inc()
                log_idempotency_event(logger, "replay", scope, key, record_id=existing.id, args_hash=existing.args_hash)
                return {
                    "outcome": "replay",
                    "record_id": existing.id,
                    "scope": scope,
                    "key": key,
                    "result": self._idempotency_result(existing),
                    "external_request_id": existing.external_request_id,
                }
            if existing.status == "failed":
                # A failed attempt is retryable: reclaim the same row rather than
                # inserting a second one, which the unique constraint forbids.
                # Update args_hash to reflect the new attempt's arguments.
                existing.status = "in_progress"
                existing.args_hash = digest
                existing.result_json = None
                existing.completed_at = None
                if external_request_id is not None:
                    existing.external_request_id = external_request_id
                session.commit()
                return {
                    "outcome": "claimed",
                    "record_id": existing.id,
                    "scope": scope,
                    "key": key,
                    "external_request_id": existing.external_request_id,
                }
            raise DuplicateRequestInFlight(f"Another request is already processing this {scope} key")
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def complete_idempotency_key(
        self,
        record_id: int,
        *,
        result: Any,
    ) -> bool:
        """Record the result of a claimed attempt so retries can replay it."""
        session = self._get_session()
        try:
            record = (
                session.query(IdempotencyRecord)
                .filter(
                    IdempotencyRecord.id == record_id,
                    IdempotencyRecord.status == "in_progress",
                )
                .with_for_update()
                .first()
            )
            if not record:
                return False
            record.status = "completed"
            record.result_json = json.dumps(result, ensure_ascii=False, default=str)
            record.completed_at = datetime.now()
            session.commit()
            # P2-01: Log completion
            log_idempotency_event(logger, "completed", record.scope, record.idempotency_key, record_id=record.id)
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def fail_idempotency_key(self, record_id: int) -> bool:
        """Release a claimed attempt that raised, leaving the key retryable.

        Without this a transient provider error would burn the key permanently and
        the user could never retry that request.
        """
        session = self._get_session()
        try:
            record = (
                session.query(IdempotencyRecord)
                .filter(
                    IdempotencyRecord.id == record_id,
                    IdempotencyRecord.status == "in_progress",
                )
                .with_for_update()
                .first()
            )
            if not record:
                return False
            record.status = "failed"
            record.completed_at = datetime.now()
            session.commit()
            # P2-01: Log failure
            log_idempotency_event(logger, "failed", record.scope, record.idempotency_key, record_id=record.id)
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_idempotency_record(self, *, scope: str, key: str) -> dict[str, Any] | None:
        session = self._get_session()
        try:
            record = (
                session.query(IdempotencyRecord)
                .filter(
                    IdempotencyRecord.scope == scope,
                    IdempotencyRecord.idempotency_key == key,
                )
                .first()
            )
            if not record:
                return None
            return {
                "id": record.id,
                "scope": record.scope,
                "key": record.idempotency_key,
                "args_hash": record.args_hash,
                "status": record.status,
                "result": self._idempotency_result(record),
                "external_request_id": record.external_request_id,
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "completed_at": record.completed_at.isoformat() if record.completed_at else None,
            }
        finally:
            session.close()

    @staticmethod
    def _idempotency_result(record: IdempotencyRecord) -> Any:
        if record.result_json is None:
            return None
        try:
            return json.loads(record.result_json)
        except (TypeError, ValueError):
            return None
