from datetime import date
from typing import Optional

from pydantic import BaseModel


class CalendarEventCreate(BaseModel):
    content_id: int
    platform: str
    scheduled_date: date


class CalendarEventResponse(BaseModel):
    event_id: int
    content_id: int
    platform: str
    scheduled_date: str
    status: str
    content_title: Optional[str] = None
    content_type: Optional[str] = None
