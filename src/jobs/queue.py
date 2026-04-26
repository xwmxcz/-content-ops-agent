"""Queue adapter for background and RQ execution modes."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import BackgroundTasks

from src.api.services.content_service import resolve_provider
from src.jobs.runner import run_job
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
