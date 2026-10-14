"""The publishing calendar: scheduling, listing, and conflict detection."""

import logging
from datetime import date
from typing import Any, Literal

from sqlalchemy import case, exists, func

from src.storage.models import CalendarEvent, Content, PlatformPublication
from src.storage.repositories.base import RepositoryMixin, assigned_pk

logger = logging.getLogger(__name__)


def _platform_schedule_exists():
    # Before the status fix, accepted platform schedules were saved as planned.
    # Conservatively protect matching legacy rows, including their UI actions.
    return (
        exists()
        .where(
            PlatformPublication.content_id == CalendarEvent.content_id,
            PlatformPublication.platform == CalendarEvent.platform,
            PlatformPublication.status == "scheduled",
            func.date(PlatformPublication.scheduled_at) == CalendarEvent.scheduled_date,
        )
        .correlate(CalendarEvent)
    )


class CalendarRepositoryMixin(RepositoryMixin):
    """See :class:`src.storage.content_store.ContentStore` for the shared contract.

    Mixed into ``ContentStore``; ``session``/``_get_session`` come from the host
    class, which is why this is a mixin rather than a standalone object.
    """

    def save_calendar_event(
        self,
        content_id: int,
        platform: str,
        scheduled_date: date,
        *,
        status: Literal["planned", "scheduled"] = "planned",
    ) -> int:
        session = self._get_session()
        try:
            event = CalendarEvent(
                content_id=content_id, platform=platform, scheduled_date=scheduled_date, status=status
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
            effective_status = case(
                ((CalendarEvent.status == "planned") & _platform_schedule_exists(), "scheduled"),
                else_=CalendarEvent.status,
            )
            query = session.query(CalendarEvent, Content, effective_status).join(
                Content, CalendarEvent.content_id == Content.id
            )
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
                    "status": event_status,
                    "content_title": content.title,
                    "content_type": content.content_type,
                }
                for event, content, event_status in results
            ]
        finally:
            session.close()

    def update_calendar_event(self, event_id: int, content_id: int, platform: str, scheduled_date: date) -> bool:
        with self._get_session() as session:
            event = session.query(CalendarEvent).filter(CalendarEvent.id == event_id).with_for_update().first()
            if event is None:
                return False
            if (
                event.status != "planned"
                or session.query(CalendarEvent.id)
                .filter(CalendarEvent.id == event_id, _platform_schedule_exists())
                .first()
            ):
                raise ValueError("Only local planned events can be edited; manage platform schedules on the platform")
            event.content_id = content_id
            event.platform = platform
            event.scheduled_date = scheduled_date
            session.commit()
            return True

    def delete_calendar_event(self, event_id: int) -> bool:
        with self._get_session() as session:
            event = session.query(CalendarEvent).filter(CalendarEvent.id == event_id).with_for_update().first()
            if event is None:
                return False
            if (
                event.status != "planned"
                or session.query(CalendarEvent.id)
                .filter(CalendarEvent.id == event_id, _platform_schedule_exists())
                .first()
            ):
                raise ValueError("Only local planned events can be deleted; manage platform schedules on the platform")
            session.delete(event)
            session.commit()
            return True

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
