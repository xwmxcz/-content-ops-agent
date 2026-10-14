from datetime import date, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status

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
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    store: ContentStore = Depends(get_store),
) -> list[dict]:
    if (start_date is None) != (end_date is None):
        raise HTTPException(status_code=422, detail="start_date and end_date must be provided together")
    if start_date is None:
        start_date = date.today()
        end_date = start_date + timedelta(days=days - 1)
    elif end_date is not None and not 0 <= (end_date - start_date).days <= 365:
        raise HTTPException(status_code=422, detail="Date range must be ordered and no longer than 366 days")
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


@router.put("/events/{event_id}", response_model=dict)
def update_event(
    event_id: int,
    request: CalendarEventCreate,
    store: ContentStore = Depends(get_store),
) -> dict:
    if not store.get_content(request.content_id):
        raise HTTPException(status_code=404, detail="Content not found")
    try:
        updated = store.update_calendar_event(event_id, request.content_id, request.platform, request.scheduled_date)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Calendar event not found")
    return {"event_id": event_id}


@router.delete("/events/{event_id}", status_code=204)
def delete_event(event_id: int, store: ContentStore = Depends(get_store)) -> Response:
    try:
        deleted = store.delete_calendar_event(event_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Calendar event not found")
    return Response(status_code=204)
