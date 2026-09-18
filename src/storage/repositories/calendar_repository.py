"""The publishing calendar: scheduling, listing, and conflict detection."""

import logging
from datetime import date
from typing import Any

from src.storage.models import (
    CalendarEvent,
    Content,
    assigned_pk,
)
from src.storage.repositories.base import RepositoryMixin

logger = logging.getLogger(__name__)


class CalendarRepositoryMixin(RepositoryMixin):
    """See :class:`src.storage.content_store.ContentStore` for the shared contract.

    Mixed into ``ContentStore``; ``session``/``_get_session`` come from the host
    class, which is why this is a mixin rather than a standalone object.
    """

    def save_calendar_event(self, content_id: int, platform: str, scheduled_date: date) -> int:
        session = self._get_session()
        try:
            event = CalendarEvent(
                content_id=content_id, platform=platform, scheduled_date=scheduled_date, status="planned"
            )
            session.add(event)
            session.commit()
            return assigned_pk(event, "id")
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_calendar_events(self, start_date=None, end_date=None) -> list[dict[str, Any]]:
        session = self._get_session()
        try:
            query = session.query(CalendarEvent, Content).join(Content, CalendarEvent.content_id == Content.id)
            if start_date:
                query = query.filter(CalendarEvent.scheduled_date >= start_date)
            if end_date:
                query = query.filter(CalendarEvent.scheduled_date <= end_date)
            query = query.order_by(CalendarEvent.scheduled_date)
            results = query.all()
            return [
                {
                    "event_id": event.id,
                    "content_id": event.content_id,
                    "platform": event.platform,
                    "scheduled_date": event.scheduled_date.isoformat(),
                    "status": event.status,
                    "content_title": content.title,
                    "content_type": content.content_type,
                }
                for event, content in results
            ]
        finally:
            session.close()

    def get_calendar_conflicts(self, start_date: date, end_date: date) -> list[dict[str, Any]]:
        """Return calendar events between [start_date, end_date], minimal shape used
        by the schedule planner to avoid double-booking a date+platform pair."""
        session = self._get_session()
        try:
            rows = (
                session.query(CalendarEvent)
                .filter(
                    CalendarEvent.scheduled_date >= start_date,
                    CalendarEvent.scheduled_date <= end_date,
                )
                .all()
            )
            return [
                {
                    "scheduled_date": r.scheduled_date.isoformat(),
                    "platform": r.platform,
                    "content_id": r.content_id,
                    "status": r.status,
                }
                for r in rows
            ]
        finally:
            session.close()
