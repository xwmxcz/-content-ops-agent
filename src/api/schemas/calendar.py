from datetime import date

from pydantic import BaseModel, Field, field_validator


class CalendarEventCreate(BaseModel):
    content_id: int = Field(..., gt=0)
    platform: str = Field(..., min_length=1, max_length=50)
    scheduled_date: date

    @field_validator("platform")
    @classmethod
    def normalize_platform(cls, value: str) -> str:
        value = value.strip().lower()
        if not value:
            raise ValueError("Platform must not be blank")
        return value


class CalendarEventResponse(BaseModel):
    event_id: int
    content_id: int
    platform: str
    scheduled_date: str
    status: str
    content_title: str | None = None
    content_type: str | None = None
