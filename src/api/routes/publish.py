from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from src.api.dependencies import get_publish_service, get_store
from src.api.schemas.publish import (
    PublishActionResponse,
    PublicationResponse,
    XiaohongshuLoginStatusResponse,
    XiaohongshuPublishRequest,
)
from src.api.services.publish_service import PublicationValidationError, PublishService
from src.jobs.queue import JobCapacityError, JobQueueError, create_and_enqueue_job
from src.storage import ContentStore


router = APIRouter()


@router.get("/xiaohongshu/login-status", response_model=XiaohongshuLoginStatusResponse)
async def get_xiaohongshu_login_status(
    publish_service: PublishService = Depends(get_publish_service),
) -> dict:
    try:
        return await publish_service.get_login_status()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/xiaohongshu", response_model=PublishActionResponse, status_code=status.HTTP_202_ACCEPTED)
def create_xiaohongshu_publication(
    request: XiaohongshuPublishRequest,
    background_tasks: BackgroundTasks,
    publish_service: PublishService = Depends(get_publish_service),
    store: ContentStore = Depends(get_store),
) -> dict:
    return _enqueue_publication(request, background_tasks, publish_service, store, require_future=False)


@router.post("/xiaohongshu/schedule", response_model=PublishActionResponse, status_code=status.HTTP_202_ACCEPTED)
def schedule_xiaohongshu_publication(
    request: XiaohongshuPublishRequest,
    background_tasks: BackgroundTasks,
    publish_service: PublishService = Depends(get_publish_service),
    store: ContentStore = Depends(get_store),
) -> dict:
    return _enqueue_publication(request, background_tasks, publish_service, store, require_future=True)


@router.get("/{publication_id}", response_model=PublicationResponse)
def get_publication(publication_id: int, store: ContentStore = Depends(get_store)) -> dict:
    publication = store.get_publication(publication_id)
    if not publication:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Publication not found")
    return publication


@router.get("/content/{content_id}", response_model=list[PublicationResponse])
def list_publications(content_id: int, store: ContentStore = Depends(get_store)) -> list[dict]:
    if not store.get_content(content_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content not found")
    return store.list_publications(content_id)


def _enqueue_publication(
    request: XiaohongshuPublishRequest,
    background_tasks: BackgroundTasks,
    publish_service: PublishService,
    store: ContentStore,
    *,
    require_future: bool,
) -> dict:
    if require_future and not request.scheduled_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scheduled_at is required")
    if require_future and request.scheduled_at and _is_past(request.scheduled_at):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scheduled_at must be in the future")

    try:
        publication = publish_service.create_publication_request(
            content_id=request.content_id,
            publish_type=request.publish_type,
            title=request.title,
            body=request.content,
            media_ids=request.media_ids,
            scheduled_at=request.scheduled_at,
            tags=request.tags,
            visibility=request.visibility,
            is_original=request.is_original,
            status="queued",
        )
        job = create_and_enqueue_job(
            "publish_xiaohongshu",
            {"publication_id": publication["id"]},
            store,
            background_tasks,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PublicationValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except JobCapacityError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except JobQueueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return {"publication": publication, "job_id": job["id"]}


def _is_past(value: datetime) -> bool:
    now = datetime.now(value.tzinfo) if value.tzinfo else datetime.now()
    return value <= now
