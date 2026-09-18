"""One-time write capabilities proposed by the model and confirmed by the user.

Status transitions are the authorization mechanism: a row moves
proposed -> confirmed -> consumed exactly once, and the executor consumes it
atomically before invoking the tool."""

import json
import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from src.storage.models import (
    ProposedAction,
)
from src.storage.repositories.base import RepositoryMixin
from src.utils import metrics
from src.utils.structured_logging import log_capability_event

logger = logging.getLogger(__name__)


class ActionRepositoryMixin(RepositoryMixin):
    """See :class:`src.storage.content_store.ContentStore` for the shared contract.

    Mixed into ``ContentStore``; ``session``/``_get_session`` come from the host
    class, which is why this is a mixin rather than a standalone object.
    """

    def create_proposed_action(
        self,
        *,
        thread_id: str,
        tool_name: str,
        args: dict[str, Any],
        impact_summary: str,
        ttl_seconds: int,
        requester: str | None = None,
        proposing_message_id: int | None = None,
        action_id: str | None = None,
    ) -> dict[str, Any]:
        """Persist an unconfirmed proposal and return its durable action id."""
        from src.utils.canonical import args_hash, canonical_json

        session = self._get_session()
        try:
            now = datetime.now()
            action = ProposedAction(
                id=action_id or f"act_{uuid4().hex[:20]}",
                thread_id=thread_id,
                requester=requester,
                tool_name=tool_name,
                args_json=canonical_json(args),
                args_hash=args_hash(args),
                impact_summary=impact_summary,
                status="proposed",
                proposing_message_id=proposing_message_id,
                created_at=now,
                expires_at=now + timedelta(seconds=max(1, int(ttl_seconds))),
            )
            session.add(action)
            session.commit()
            # P2-01: Track proposed capabilities
            metrics.capability_proposals_total.labels(tool=tool_name).inc()
            log_capability_event(logger, "proposed", action.id, tool_name, thread_id=thread_id)
            return self._proposed_action_to_dict(action)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_proposed_action(self, action_id: str) -> dict[str, Any] | None:
        session = self._get_session()
        try:
            action = session.query(ProposedAction).filter(ProposedAction.id == action_id).first()
            return self._proposed_action_to_dict(action) if action else None
        finally:
            session.close()

    def list_proposed_actions(
        self,
        thread_id: str,
        *,
        statuses: tuple[str, ...] | set[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        session = self._get_session()
        try:
            query = session.query(ProposedAction).filter(ProposedAction.thread_id == thread_id)
            if statuses:
                query = query.filter(ProposedAction.status.in_(tuple(statuses)))
            rows = query.order_by(ProposedAction.created_at.desc(), ProposedAction.id.desc()).limit(limit).all()
            return [self._proposed_action_to_dict(row) for row in rows]
        finally:
            session.close()

    def latest_pending_proposed_action(
        self,
        thread_id: str,
        *,
        tool_name: str | None = None,
    ) -> dict[str, Any] | None:
        """Most recent unexpired ``proposed`` row for a thread.

        Expiry is evaluated against the stored ``expires_at`` using the same
        application clock that wrote it, not against the recognized transcript,
        so an idle thread resumed after the TTL has no capability to confirm and
        fails closed.
        """
        session = self._get_session()
        try:
            query = session.query(ProposedAction).filter(
                ProposedAction.thread_id == thread_id,
                ProposedAction.status == "proposed",
                ProposedAction.expires_at > datetime.now(),
            )
            if tool_name:
                query = query.filter(ProposedAction.tool_name == tool_name)
            action = query.order_by(ProposedAction.created_at.desc(), ProposedAction.id.desc()).first()
            return self._proposed_action_to_dict(action) if action else None
        finally:
            session.close()

    def confirm_proposed_action(self, action_id: str) -> dict[str, Any] | None:
        """Move exactly one ``proposed`` row to ``confirmed``.

        Two concurrent confirmations of the same proposal serialize on the row
        lock; the loser observes a non-``proposed`` status and returns ``None``,
        so a double-clicked confirm issues one capability, not two.
        """
        session = self._get_session()
        try:
            action = (
                session.query(ProposedAction)
                .filter(ProposedAction.id == action_id, ProposedAction.status == "proposed")
                .with_for_update()
                .first()
            )
            if not action:
                return None
            now = datetime.now()
            if action.expires_at <= now:
                action.status = "expired"
                session.commit()
                return None
            action.status = "confirmed"
            action.confirmed_at = now
            session.commit()
            return self._proposed_action_to_dict(action)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def consume_proposed_action(
        self,
        action_id: str,
        *,
        tool_name: str,
        args: dict[str, Any],
        consuming_message_id: int | None = None,
    ) -> dict[str, Any] | None:
        """Atomically claim a confirmed capability for one tool invocation.

        The row lock plus the ``status == 'confirmed'`` predicate make this the
        once-only gate: replay, a second executor loop iteration, and two racing
        requests all lose the race and receive ``None``. The stored hash is
        re-checked here so arguments tampered with after confirmation cannot be
        executed even though the capability itself is valid.
        """
        from src.utils.canonical import args_hash

        session = self._get_session()
        try:
            action = (
                session.query(ProposedAction)
                .filter(ProposedAction.id == action_id, ProposedAction.status == "confirmed")
                .with_for_update()
                .first()
            )
            if not action:
                return None
            now = datetime.now()
            if action.expires_at <= now:
                action.status = "expired"
                session.commit()
                # P2-01: Track expired capabilities
                metrics.capability_expired_total.labels(tool=action.tool_name).inc()
                log_capability_event(logger, "expired", action_id, tool_name, expired=True)
                return None
            if action.tool_name != tool_name or action.args_hash != args_hash(args):
                # Leave the capability unconsumed: the mismatch is the model
                # substituting a different call, not the user's approved action.
                session.rollback()
                return None
            action.status = "consumed"
            action.consumed_at = now
            action.consuming_message_id = consuming_message_id
            session.commit()
            # P2-01: Track consumed capabilities
            metrics.capability_consumed_total.labels(tool=tool_name).inc()
            log_capability_event(logger, "consumed", action_id, tool_name, consumed=True)
            return self._proposed_action_to_dict(action)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def cancel_proposed_action(self, action_id: str) -> dict[str, Any] | None:
        """Cancel a proposal or an unused confirmation; consumed rows are final."""
        session = self._get_session()
        try:
            action = (
                session.query(ProposedAction)
                .filter(
                    ProposedAction.id == action_id,
                    ProposedAction.status.in_(("proposed", "confirmed")),
                )
                .with_for_update()
                .first()
            )
            if not action:
                return None
            action.status = "cancelled"
            action.cancelled_at = datetime.now()
            session.commit()
            return self._proposed_action_to_dict(action)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def expire_proposed_actions(self, *, thread_id: str | None = None) -> int:
        """Mark overdue pending rows expired. Returns the number updated."""
        session = self._get_session()
        try:
            query = session.query(ProposedAction).filter(
                ProposedAction.status.in_(("proposed", "confirmed")),
                ProposedAction.expires_at <= datetime.now(),
            )
            if thread_id:
                query = query.filter(ProposedAction.thread_id == thread_id)
            updated = query.update({ProposedAction.status: "expired"}, synchronize_session=False)
            session.commit()
            return int(updated or 0)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _proposed_action_to_dict(action: ProposedAction) -> dict[str, Any]:
        try:
            args = json.loads(action.args_json)
        except (TypeError, ValueError):
            args = {}
        return {
            "id": action.id,
            "thread_id": action.thread_id,
            "requester": action.requester,
            "tool_name": action.tool_name,
            "args": args if isinstance(args, dict) else {},
            "args_hash": action.args_hash,
            "impact_summary": action.impact_summary,
            "status": action.status,
            "proposing_message_id": action.proposing_message_id,
            "consuming_message_id": action.consuming_message_id,
            "created_at": action.created_at.isoformat() if action.created_at else None,
            "expires_at": action.expires_at.isoformat() if action.expires_at else None,
            "confirmed_at": action.confirmed_at.isoformat() if action.confirmed_at else None,
            "consumed_at": action.consumed_at.isoformat() if action.consumed_at else None,
            "cancelled_at": action.cancelled_at.isoformat() if action.cancelled_at else None,
        }
