from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from src.api.dependencies import get_store
from src.api.schemas.jobs import (
    AgentRunJobRequest,
    ContentGenerationJobRequest,
    JobResponse,
    RefineJobRequest,
    SeoJobRequest,
    TitlesJobRequest,
)
from src.jobs.queue import JobCapacityError, JobQueueError, create_and_enqueue_job
from src.storage import ContentStore


router = APIRouter()


@router.post("/content-generation", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_content_generation_job(
    request: ContentGenerationJobRequest,
    background_tasks: BackgroundTasks,
    store: ContentStore = Depends(get_store),
) -> dict:
    return _create_job("content_generation", request.model_dump(mode="json"), background_tasks, store)


@router.post("/agent-run", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_agent_run_job(
    request: AgentRunJobRequest,
    background_tasks: BackgroundTasks,
    store: ContentStore = Depends(get_store),
) -> dict:
    return _create_job("agent_run", request.model_dump(mode="json"), background_tasks, store)


@router.post("/refine", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_refine_job(
    request: RefineJobRequest,
    background_tasks: BackgroundTasks,
    store: ContentStore = Depends(get_store),
) -> dict:
    return _create_job("refine", request.model_dump(mode="json"), background_tasks, store)


@router.post("/titles", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_titles_job(
    request: TitlesJobRequest,
    background_tasks: BackgroundTasks,
    store: ContentStore = Depends(get_store),
) -> dict:
    return _create_job("titles", request.model_dump(mode="json"), background_tasks, store)


@router.post("/seo", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_seo_job(
    request: SeoJobRequest,
    background_tasks: BackgroundTasks,
    store: ContentStore = Depends(get_store),
) -> dict:
    return _create_job("seo", request.model_dump(mode="json"), background_tasks, store)


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, store: ContentStore = Depends(get_store)) -> dict:
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} was not found")
    return job


@router.delete("/{job_id}", response_model=JobResponse)
def cancel_job(job_id: str, store: ContentStore = Depends(get_store)) -> dict:
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} was not found")
    if job["status"] in {"completed", "failed", "cancelled"}:
        return job
    updated = store.update_job(
        job_id,
        status="cancelled",
        progress=100,
        error="Cancelled by user",
    )
    return updated or job


def _create_job(
    job_type: str,
    payload: dict,
    background_tasks: BackgroundTasks,
    store: ContentStore,
) -> dict:
    try:
        return create_and_enqueue_job(job_type, payload, store, background_tasks)
    except JobCapacityError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
            headers={"Retry-After": "10"},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except JobQueueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
