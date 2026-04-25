from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.dependencies import get_store
from src.api.schemas.calendar import CalendarEventCreate, CalendarEventResponse
from src.storage import ContentStore


router = APIRouter()


@router.get("/events", response_model=list[CalendarEventResponse])
def list_events(
    days: int = Query(default=7, ge=1, le=365),
    store: ContentStore = Depends(get_store),
) -> list[dict]:
    start_date = date.today()
    end_date = start_date + timedelta(days=days)
    return store.get_calendar_events(start_date, end_date)


@router.post("/events", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_event(
    request: CalendarEventCreate,
    store: ContentStore = Depends(get_store),
) -> dict:
    if not store.get_content(request.content_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content not found")
    event_id = store.save_calendar_event(
        request.content_id,
        request.platform,
        request.scheduled_date,
    )
    return {"event_id": event_id}
