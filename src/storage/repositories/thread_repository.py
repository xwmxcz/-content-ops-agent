"""Chat threads and their messages, including cross-thread session search."""

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from src.storage.models import (
    AgentMessage,
    AgentThread,
    ProposedAction,
    assigned_pk,
)
from src.storage.repositories.base import RepositoryMixin

logger = logging.getLogger(__name__)


class ThreadRepositoryMixin(RepositoryMixin):
    """See :class:`src.storage.content_store.ContentStore` for the shared contract.

    Mixed into ``ContentStore``; ``session``/``_get_session`` come from the host
    class, which is why this is a mixin rather than a standalone object.
    """

    def upsert_agent_thread(
        self,
        thread_id: str,
        title: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Create or touch a thread row.

        Auto-title path: `title` is only written when the thread is brand-new
        OR the existing thread has neither a title nor a manual lock. Once
        `title_pinned=1` (set via `update_agent_thread`), title is never
        overwritten here. Provider/model always refresh to reflect the latest
        turn.
        """
        session = self._get_session()
        try:
            thread = session.query(AgentThread).filter(AgentThread.id == thread_id).first()
            now = datetime.now()
            if not thread:
                thread = AgentThread(
                    id=thread_id,
                    title=title,
                    last_provider=provider,
                    last_model=model,
                    created_at=now,
                    updated_at=now,
                )
                session.add(thread)
            else:
                if title and not thread.title and not thread.title_pinned:
                    thread.title = title
                thread.last_provider = provider or thread.last_provider
                thread.last_model = model or thread.last_model
                thread.updated_at = now
            session.commit()
            return self._agent_thread_to_dict(thread, session)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_agent_threads(
        self,
        limit: int = 30,
        offset: int = 0,
        include_archived: bool = False,
        q: str | None = None,
    ) -> list[dict[str, Any]]:
        """List threads with pin-first ordering, optional archived filter, optional title/id search.

        Uses a single LEFT JOIN + GROUP BY to fetch message_count, replacing the
        previous N+1 (one COUNT per thread) pattern.
        """
        session = self._get_session()
        try:
            query = session.query(
                AgentThread,
                func.count(AgentMessage.id).label("message_count"),
            ).outerjoin(AgentMessage, AgentMessage.thread_id == AgentThread.id)

            if not include_archived:
                query = query.filter(AgentThread.archived.is_(False))
            if q and q.strip():
                pattern = f"%{q.strip()}%"
                query = query.filter(or_(AgentThread.title.ilike(pattern), AgentThread.id.ilike(pattern)))

            query = (
                query.group_by(AgentThread.id)
                .order_by(AgentThread.pinned.desc(), AgentThread.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
            rows = query.all()
            return [
                self._agent_thread_to_dict(thread, session, message_count=message_count)
                for thread, message_count in rows
            ]
        finally:
            session.close()

    def get_agent_thread(self, thread_id: str) -> dict[str, Any] | None:
        session = self._get_session()
        try:
            thread = session.query(AgentThread).filter(AgentThread.id == thread_id).first()
            if not thread:
                return None
            return self._agent_thread_to_dict(thread, session)
        finally:
            session.close()

    def update_agent_thread(
        self,
        thread_id: str,
        *,
        title: str | None = None,
        pinned: bool | None = None,
        archived: bool | None = None,
    ) -> dict[str, Any] | None:
        """Manual edits to a thread row.

        - Passing `title` writes it and sets `title_pinned=True`, which locks
          out the auto-title path in `upsert_agent_thread` / `save_agent_message`.
        - All three fields are independently optional; pass only what changes.
        - Returns the refreshed dict, or None if the thread doesn't exist.
        """
        if title is None and pinned is None and archived is None:
            raise ValueError("update_agent_thread requires at least one field")
        session = self._get_session()
        try:
            thread = session.query(AgentThread).filter(AgentThread.id == thread_id).first()
            if not thread:
                return None
            if title is not None:
                thread.title = title.strip() or None
                thread.title_pinned = True
            if pinned is not None:
                thread.pinned = bool(pinned)
            if archived is not None:
                thread.archived = bool(archived)
            thread.updated_at = datetime.now()
            session.commit()
            return self._agent_thread_to_dict(thread, session)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def save_agent_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        provider: str | None = None,
        model: str | None = None,
        intent: dict | None = None,
        tool_events: list[dict] | None = None,
        plan: list[dict] | None = None,
        status: str = "completed",
    ) -> int:
        session = self._get_session()
        try:
            thread = session.query(AgentThread).filter(AgentThread.id == thread_id).first()
            if not thread:
                thread = AgentThread(
                    id=thread_id,
                    title=self._make_thread_title(content) if role == "user" else None,
                    last_provider=provider,
                    last_model=model,
                )
                session.add(thread)
                session.flush()
            elif role == "user" and not thread.title and not thread.title_pinned:
                thread.title = self._make_thread_title(content)

            thread.last_provider = provider or thread.last_provider
            thread.last_model = model or thread.last_model
            thread.updated_at = datetime.now()

            message = AgentMessage(
                thread_id=thread_id,
                role=role,
                content=content,
                provider=provider,
                model=model,
                intent=json.dumps(intent, ensure_ascii=False) if intent else None,
                tool_events=json.dumps(tool_events or [], ensure_ascii=False),
                plan=json.dumps(plan, ensure_ascii=False) if plan else None,
                status=status,
            )
            session.add(message)
            session.commit()
            return assigned_pk(message, "id")
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_agent_messages(
        self,
        thread_id: str,
        limit: int = 50,
        before_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """List messages oldest-first.

        Without `before_id`, returns the most recent `limit` messages.
        With `before_id`, returns the `limit` messages with id < before_id
        (cursor-style "load older history"), still oldest-first within the slice.
        """
        session = self._get_session()
        try:
            query = session.query(AgentMessage).filter(AgentMessage.thread_id == thread_id)
            if before_id is not None:
                query = query.filter(AgentMessage.id < before_id)
            messages = query.order_by(AgentMessage.created_at.desc()).limit(limit).all()
            return [self._agent_message_to_dict(message) for message in reversed(messages)]
        finally:
            session.close()

    def search_agent_messages(
        self,
        query: str,
        limit: int = 10,
        thread_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Substring search over agent_messages content using ILIKE."""
        query = (query or "").strip()
        if not query:
            return []
        session = self._get_session()
        try:
            q = session.query(AgentMessage).filter(AgentMessage.content.ilike(f"%{query}%"))
            if thread_id:
                q = q.filter(AgentMessage.thread_id == thread_id)
            messages = q.order_by(AgentMessage.created_at.desc()).limit(limit).all()
            return [self._agent_message_to_dict(m) for m in messages]
        finally:
            session.close()

    def delete_agent_thread(self, thread_id: str) -> bool:
        session = self._get_session()
        try:
            thread = session.query(AgentThread).filter(AgentThread.id == thread_id).first()
            if not thread:
                return False
            session.query(AgentMessage).filter(AgentMessage.thread_id == thread_id).delete()
            # proposed_actions.thread_id is a NO ACTION foreign key, so its rows must
            # be cleared here or deleting a thread that ever proposed a write fails.
            session.query(ProposedAction).filter(ProposedAction.thread_id == thread_id).delete()
            session.delete(thread)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _make_thread_title(content: str) -> str:
        title = " ".join(content.strip().split())
        return title[:40] or "Untitled thread"

    @staticmethod
    def _agent_message_to_dict(message: AgentMessage) -> dict[str, Any]:
        return {
            "id": message.id,
            "thread_id": message.thread_id,
            "role": message.role,
            "content": message.content,
            "provider": message.provider,
            "model": message.model,
            "intent": json.loads(message.intent) if message.intent else None,
            "tool_events": json.loads(message.tool_events) if message.tool_events else [],
            "plan": json.loads(message.plan) if message.plan else [],
            "status": message.status,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }

    @staticmethod
    def _agent_thread_to_dict(
        thread: AgentThread,
        session: Session,
        message_count: int | None = None,
    ) -> dict[str, Any]:
        if message_count is None:
            message_count = session.query(AgentMessage).filter(AgentMessage.thread_id == thread.id).count()
        return {
            "id": thread.id,
            "title": thread.title,
            "last_provider": thread.last_provider,
            "last_model": thread.last_model,
            "pinned": bool(thread.pinned),
            "archived": bool(thread.archived),
            "title_pinned": bool(thread.title_pinned),
            "message_count": message_count,
            "created_at": thread.created_at.isoformat() if thread.created_at else None,
            "updated_at": thread.updated_at.isoformat() if thread.updated_at else None,
        }
