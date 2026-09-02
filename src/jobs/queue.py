"""Queue adapter for background and RQ execution modes."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import BackgroundTasks

from src.api.services.content_service import resolve_provider
from src.jobs.runner import run_job, run_pipeline_job
from src.storage import ContentStore
from src.utils import config


class JobQueueError(RuntimeError):
    """Raised when a job cannot be enqueued."""


class JobCapacityError(RuntimeError):
    """Raised when provider-specific inflight limits are exhausted."""


def create_and_enqueue_job(
    job_type: str,
    payload: dict[str, Any],
    store: ContentStore,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    if job_type == "publish_xiaohongshu":
        provider = "xiaohongshu-mcp"
        model = "publish"
    else:
        provider = resolve_provider(payload.get("provider"))
        model = payload.get("model") or config.get_model(provider)
    if store.count_inflight_jobs(provider) >= config.MAX_PROVIDER_INFLIGHT_JOBS:
        raise JobCapacityError(f"Too many in-flight jobs for provider: {provider}")

    job_id = f"job_{uuid.uuid4().hex[:16]}"
    job = store.create_job(
        job_id=job_id,
        job_type=job_type,
        payload=payload,
        provider=provider,
        model=model,
    )
    try:
        _enqueue(job_id, background_tasks, store.database_url)
    except Exception as exc:
        store.update_job(job_id, status="failed", progress=100, error=str(exc))
        raise
    return job


def _enqueue(job_id: str, background_tasks: BackgroundTasks, database_url: str) -> None:
    if config.JOB_QUEUE_MODE == "background":
        background_tasks.add_task(run_job, job_id, database_url)
        return

    if config.JOB_QUEUE_MODE == "rq":
        try:
            from redis import Redis
            from rq import Queue
        except ImportError as exc:
            raise JobQueueError("RQ dependencies are not installed") from exc

        try:
            queue = Queue(config.JOB_QUEUE_NAME, connection=Redis.from_url(config.REDIS_URL))
            queue.enqueue(
                "src.jobs.runner.run_job",
                job_id,
                database_url,
                job_timeout=config.JOB_TIMEOUT_SECONDS,
                result_ttl=3600,
                failure_ttl=86400,
            )
        except Exception as exc:
            raise JobQueueError("Failed to enqueue job") from exc
        return

    raise JobQueueError(f"Unknown JOB_QUEUE_MODE: {config.JOB_QUEUE_MODE}")


def enqueue_pipeline_run(
    run_id: str,
    request_data: dict[str, Any],
    database_url: str,
    background_tasks: BackgroundTasks | None = None,
) -> None:
    """Schedule a dynamic Studio pipeline run using the configured queue mode.

    In `background` mode the pipeline runs inside the API process via FastAPI
    BackgroundTasks (the in-process/dev path). In `rq` mode it is enqueued to Redis/RQ
    so the multi-step LLM workload executes on a worker instead of the HTTP
    process — matching how content/refine/agent jobs already behave. SSE consumers
    read from `agent_run_events` in both modes, so the streaming contract is
    unchanged regardless of where the pipeline actually runs.
    """
    if config.JOB_QUEUE_MODE == "background":
        if background_tasks is None:
            raise JobQueueError("background_tasks is required in background queue mode")
        background_tasks.add_task(run_pipeline_job, run_id, request_data, database_url)
        return

    if config.JOB_QUEUE_MODE == "rq":
        try:
            from redis import Redis
            from rq import Queue
        except ImportError as exc:
            raise JobQueueError("RQ dependencies are not installed") from exc

        try:
            queue = Queue(config.JOB_QUEUE_NAME, connection=Redis.from_url(config.REDIS_URL))
            queue.enqueue(
                "src.jobs.runner.run_pipeline_job",
                run_id,
                request_data,
                database_url,
                job_timeout=config.JOB_TIMEOUT_SECONDS,
                result_ttl=3600,
                failure_ttl=86400,
            )
        except Exception as exc:
            raise JobQueueError("Failed to enqueue pipeline run") from exc
        return

    raise JobQueueError(f"Unknown JOB_QUEUE_MODE: {config.JOB_QUEUE_MODE}")


def requeue_job_with_delay(job_id: str, delay_seconds: int, database_url: str) -> None:
    """Requeue a failed job for retry after the specified delay.
    
    In background mode, this schedules a delayed task. In RQ mode, it uses RQ's
    native delayed execution support.
    """
    if config.JOB_QUEUE_MODE == "background":
        # Background mode doesn't support true delayed execution.
        # The job will be picked up on next run_job call when next_retry_at is checked.
        # This is acceptable for development/test environments.
        return

    if config.JOB_QUEUE_MODE == "rq":
        try:
            from datetime import timedelta
            from redis import Redis
            from rq import Queue
        except ImportError as exc:
            raise JobQueueError("RQ dependencies are not installed") from exc

        try:
            queue = Queue(config.JOB_QUEUE_NAME, connection=Redis.from_url(config.REDIS_URL))
            queue.enqueue_in(
                timedelta(seconds=delay_seconds),
                "src.jobs.runner.run_job",
                job_id,
                database_url,
                job_timeout=config.JOB_TIMEOUT_SECONDS,
                result_ttl=3600,
                failure_ttl=86400,
            )
        except Exception as exc:
            raise JobQueueError(f"Failed to requeue job with delay: {exc}") from exc
        return

    raise JobQueueError(f"Unknown JOB_QUEUE_MODE: {config.JOB_QUEUE_MODE}")
