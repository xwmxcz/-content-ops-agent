from datetime import date, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from src.api.dependencies import get_store
from src.api.schemas.calendar import CalendarEventCreate, CalendarEventResponse
from src.storage import ContentStore
from src.utils.idempotency import (
    SCOPE_CALENDAR_COMMIT,
    DuplicateRequestInFlight,
    IdempotencyKeyConflict,
    idempotent_write,
)


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
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    store: ContentStore = Depends(get_store),
) -> dict:
    if not store.get_content(request.content_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content not found")
    try:
        event_id = idempotent_write(
            store,
            scope=SCOPE_CALENDAR_COMMIT,
            key=idempotency_key,
            args={
                "content_id": request.content_id,
                "platform": request.platform,
                "scheduled_date": request.scheduled_date.isoformat(),
            },
            write=lambda: store.save_calendar_event(
                request.content_id,
                request.platform,
                request.scheduled_date,
            ),
        )
    except DuplicateRequestInFlight as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IdempotencyKeyConflict as exc:
        # Literal 422: `HTTP_422_UNPROCESSABLE_ENTITY` is deprecated on Starlette
        # 1.6 while `HTTP_422_UNPROCESSABLE_CONTENT` is absent on the older
        # versions that `fastapi>=0.115` still allows.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"event_id": event_id}
