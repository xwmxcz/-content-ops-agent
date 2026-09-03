"""Job runner shared by FastAPI background tasks and RQ workers."""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from contextlib import suppress
from datetime import datetime, timedelta
from typing import Any

from src.api.schemas.agent import AgentRunRequest
from src.api.schemas.content import GenerateRequest, RefineRequest, SeoRequest, TitleRequest
from src.api.services import content_service
from src.api.services.agent_pipeline import PipelineExecutionError, run_agent_pipeline
from src.api.services.publish_service import PublicationValidationError, create_publish_service
from src.integrations.mcp_client import McpClientError
from src.jobs.error_classifier import ErrorClassifier
from src.llm.litellm_client import LLMConfigurationError, LLMGenerationError, LiteLLMClient
from src.storage import ContentStore
from src.utils import config, metrics
from src.utils.structured_logging import log_event, log_job_event


logger = logging.getLogger(__name__)


# Identifies this process as a lease holder. Host and PID alone are not enough:
# a restarted worker can reuse a PID and would then look like the previous owner
# of a lease it never took, so a random suffix makes the identity per-process.
_WORKER_ID = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


def current_worker_id() -> str:
    """Lease identity of this worker process."""
    return _WORKER_ID


def run_job(job_id: str, database_url: str | None = None) -> None:
    """Run one persisted job. RQ imports this function by dotted path."""
    store = ContentStore(database_url=database_url or config.DATABASE_URL, initialize_schema=False)
    try:
        asyncio.run(run_job_async(job_id, store))
    finally:
        store.engine.dispose()


def run_pipeline_job(run_id: str, request_data: dict[str, Any], database_url: str | None = None) -> None:
    """Run one dynamic Studio pipeline. RQ imports this function by dotted path.

    `request_data` is a JSON-safe dict (``PipelineRunRequest.model_dump(mode="json")``)
    so it survives RQ's pickle serialization without carrying live Pydantic/enum
    objects. The run row and its SSE event stream are keyed by `run_id`, which the
    caller pre-creates so the SSE endpoint never 404s between enqueue and boot.
    """
    store = ContentStore(database_url=database_url or config.DATABASE_URL, initialize_schema=False)
    try:
        asyncio.run(_run_pipeline_job_async(run_id, request_data, store))
    finally:
        store.engine.dispose()


async def _run_pipeline_job_async(run_id: str, request_data: dict[str, Any], store: ContentStore) -> None:
    from src.api.schemas.agent import PipelineRunRequest
    from src.api.services.dynamic_pipeline import DynamicPipeline

    try:
        request = PipelineRunRequest(**request_data)
        pipeline = DynamicPipeline(store=store, llm=create_litellm_client())
        await pipeline.run(request, run_id=run_id)
    except Exception as exc:
        # The run row was pre-created by the API before enqueue. Any failure here
        # — bad payload, LLM/config error, unexpected crash — must land as a terminal
        # run_failed event, otherwise SSE consumers hang until the stream deadline.
        error = str(exc) or exc.__class__.__name__
        store.transition_run_and_append_event(
            run_id,
            expected_statuses={"running"},
            new_status="failed",
            event_type="run_failed",
            payload={"error": error},
            error=error,
        )
        log_event(
            logger,
            "pipeline_job_failed",
            level=logging.ERROR,
            run_id=run_id,
            error_class=exc.__class__.__name__,
        )


async def run_job_async(job_id: str, store: ContentStore) -> None:
    job = store.get_job(job_id)
    if not job:
        return
    
    # Check if job should be retried based on next_retry_at
    if job["status"] == "failed" and job.get("next_retry_at"):
        next_retry_at = datetime.fromisoformat(job["next_retry_at"])
        if datetime.now() < next_retry_at:
            # Too early to retry, skip this execution
            return
    
    if job["status"] not in {"queued", "failed"}:
        return

    job_type = job["job_type"]
    lease_duration = config.JOB_LEASE_DURATION_SECONDS
    # P1-04: take the lease before marking the job running. The reverse order
    # would leave a running row with no lease holder, which the reaper cannot
    # recognise as abandoned because it sweeps on a non-null expiry.
    if not store.acquire_job_lease(job_id, _WORKER_ID, lease_duration):
        metrics.job_lease_conflicts_total.labels(job_type=job_type).inc()
        log_event(
            logger,
            "job_lease_conflict",
            job_id=job_id,
            job_type=job_type,
            worker_id=_WORKER_ID,
        )
        return
    metrics.job_lease_acquired_total.labels(job_type=job_type).inc()

    attempts = int(job.get("attempts") or 0) + 1
    max_retries = int(job.get("max_retries") or config.JOB_MAX_RETRIES)
    job = store.start_job(job_id, attempts=attempts, progress=5)
    if not job:
        store.release_job_lease(job_id, _WORKER_ID)
        return
    log_event(
        logger,
        "job_started",
        job_id=job_id,
        job_type=job["job_type"],
        provider=job.get("provider"),
        model=job.get("model"),
        attempt=attempts,
        worker_id=_WORKER_ID,
    )
    llm = create_litellm_client()

    # The monitor both heartbeats the lease and watches for cancellation, so one
    # poll interval serves both and long-running work does not need to cooperate.
    monitor_state: dict[str, str | None] = {"reason": None}
    exec_task = asyncio.ensure_future(_execute_job(job, llm, store))
    monitor_task = asyncio.ensure_future(
        _monitor_job_lease(job_id, job_type, store, exec_task, monitor_state)
    )

    try:
        try:
            result = await exec_task
        except asyncio.CancelledError:
            reason = monitor_state.get("reason")
            if reason == "lease_lost":
                # The reaper already requeued this job and another worker may own
                # it now. Writing a terminal state here would clobber that owner,
                # so this worker exits without touching job state.
                metrics.job_lease_lost_total.labels(job_type=job_type).inc()
                log_event(
                    logger,
                    "job_lease_lost",
                    level=logging.WARNING,
                    job_id=job_id,
                    job_type=job_type,
                    worker_id=_WORKER_ID,
                )
                return
            if reason == "cancelled":
                metrics.job_cancellations_total.labels(job_type=job_type).inc()
                log_event(
                    logger,
                    "job_cancelled",
                    job_id=job_id,
                    job_type=job_type,
                    worker_id=_WORKER_ID,
                )
                return
            raise
        except (
            LLMConfigurationError,
            LLMGenerationError,
            ValueError,
            LookupError,
            PipelineExecutionError,
            PublicationValidationError,
            McpClientError,
        ) as exc:
            if _is_cancelled(job_id, store):
                return
            _handle_job_error(job_id, exc, attempts, max_retries, store, job["job_type"])
        except Exception as exc:
            if _is_cancelled(job_id, store):
                return
            _handle_job_error(job_id, exc, attempts, max_retries, store, job["job_type"])
        else:
            if _is_cancelled(job_id, store):
                return
            store.update_job(job_id, status="completed", progress=100, result=result, error=None)
            # P2-01: Log completion
            log_job_event(logger, "completed", job_id, job_type=job["job_type"])
            log_event(logger, "job_completed", job_id=job_id, job_type=job["job_type"])
    finally:
        monitor_task.cancel()
        with suppress(asyncio.CancelledError):
            await monitor_task
        # Scoped to this worker id, so a no-op when the lease was already reaped.
        store.release_job_lease(job_id, _WORKER_ID)


async def _monitor_job_lease(
    job_id: str,
    job_type: str,
    store: ContentStore,
    exec_task: "asyncio.Future[Any]",
    state: dict[str, str | None],
) -> None:
    """Heartbeat the lease and propagate cancellation into the running job.

    Cancelling ``exec_task`` is what carries a cancel or a lost lease into
    in-flight HTTP/LLM/tool awaits; without it the job would keep running and
    could still write its result after another worker took ownership.
    """
    interval = max(1, config.JOB_HEARTBEAT_INTERVAL_SECONDS)
    lease_duration = config.JOB_LEASE_DURATION_SECONDS
    while True:
        await asyncio.sleep(interval)
        if exec_task.done():
            return
        if _is_cancelled(job_id, store):
            state["reason"] = "cancelled"
            exec_task.cancel()
            return
        if not store.extend_job_lease(job_id, _WORKER_ID, lease_duration):
            state["reason"] = "lease_lost"
            exec_task.cancel()
            return
        log_event(
            logger,
            "job_lease_heartbeat",
            level=logging.DEBUG,
            job_id=job_id,
            job_type=job_type,
            worker_id=_WORKER_ID,
        )


def _is_cancelled(job_id: str, store: ContentStore) -> bool:
    current = store.get_job(job_id)
    return bool(current and current.get("status") == "cancelled")


def _calculate_backoff_delay(attempt: int) -> int:
    """Calculate exponential backoff delay in seconds.
    
    Delays: 30s, 60s, 120s, 240s, 480s (capped at max)
    """
    base_delay = config.JOB_RETRY_INITIAL_DELAY_SECONDS
    max_delay = config.JOB_RETRY_MAX_DELAY_SECONDS
    
    # Exponential: 30 * 2^(attempt-1)
    delay = base_delay * (2 ** (attempt - 1))
    return min(delay, max_delay)


def _handle_job_error(
    job_id: str,
    exc: Exception,
    current_attempt: int,
    max_retries: int,
    store: ContentStore,
    job_type: str = "unknown",
) -> None:
    """Handle job errors with smart retry logic based on error classification."""
    error_message = str(exc).strip() or "Job failed unexpectedly"
    error_type = ErrorClassifier.classify(exc)
    
    should_retry = ErrorClassifier.should_retry(exc, current_attempt, max_retries)
    
    if should_retry:
        # Calculate backoff and schedule retry
        delay_seconds = _calculate_backoff_delay(current_attempt)
        next_retry_at = datetime.now() + timedelta(seconds=delay_seconds)
        
        store.update_job(
            job_id,
            status="failed",  # Keep as failed but with next_retry_at set
            progress=100,
            error=error_message,
            error_type=error_type,
            next_retry_at=next_retry_at,
        )
        
        # P2-01: Metrics and logging
        metrics.job_retry_attempts_total.labels(error_type=error_type).inc()
        log_job_event(
            logger, "retry_scheduled", job_id, job_type,
            error_type=error_type, retry_count=current_attempt, next_retry_at=next_retry_at.isoformat()
        )
        
        log_event(
            logger,
            "job_retry_scheduled",
            level=logging.WARNING,
            job_id=job_id,
            error_class=exc.__class__.__name__,
            error_type=error_type,
            attempt=current_attempt,
            max_retries=max_retries,
            next_retry_in_seconds=delay_seconds,
        )
        
        # Requeue the job for delayed execution
        from src.jobs.queue import requeue_job_with_delay
        try:
            requeue_job_with_delay(job_id, delay_seconds, store.database_url)
        except Exception as requeue_error:
            log_event(
                logger,
                "job_requeue_failed",
                level=logging.ERROR,
                job_id=job_id,
                requeue_error=str(requeue_error),
            )
    else:
        # Permanent error or max retries exceeded - mark as permanently failed
        store.update_job(
            job_id,
            status="failed",
            progress=100,
            error=error_message,
            error_type=error_type,
            next_retry_at=None,  # Clear any scheduled retry
        )
        
        # P2-01: Metrics and logging
        if current_attempt >= max_retries:
            metrics.job_retry_exhausted_total.inc()
        metrics.job_failures_total.labels(error_type=error_type).inc()
        log_job_event(
            logger, "failed_permanently", job_id, job_type,
            error_type=error_type, retry_count=current_attempt, max_retries=max_retries
        )
        
        log_event(
            logger,
            "job_failed",
            level=logging.ERROR,
            job_id=job_id,
            error_class=exc.__class__.__name__,
            error_type=error_type,
            attempt=current_attempt,
            reason="permanent_error" if error_type == "permanent" else "max_retries_exceeded",
        )


async def _execute_job(job: dict[str, Any], llm: LiteLLMClient, store: ContentStore) -> dict[str, Any]:
    job_type = job["job_type"]
    payload = job["payload"]
    job_id = job["id"]

    if job_type == "content_generation":
        request = GenerateRequest(**payload)
        content_id, generated, provider, model = await content_service.generate_content(request, llm, store)
        return {
            "content": {
                "id": content_id,
                "title": generated.title,
                "content": generated.content,
                "content_type": generated.content_type.value if generated.content_type else request.content_type.value,
                "style": request.style.value,
                "tags": generated.tags or [],
                "status": "draft",
                "created_at": generated.created_at.isoformat() if generated.created_at else None,
                "updated_at": None,
                "provider": provider,
                "model": model,
            }
        }

    if job_type == "agent_run":
        request = AgentRunRequest(**payload)
        store.update_job(job_id, progress=20)
        result = await run_agent_pipeline(request, llm, store)
        return {"agent_run": result.model_dump()}

    if job_type == "refine":
        request = RefineRequest(**payload)
        content_id, refined, provider, model = await content_service.refine_content(request, llm, store)
        stored = store.get_content(content_id) or {}
        return {
            "content": {
                "id": content_id,
                "title": refined.title,
                "content": refined.content,
                "content_type": refined.content_type.value if refined.content_type else stored.get("content_type", "unknown"),
                "style": stored.get("style", request.new_style.value if request.new_style else "casual"),
                "tags": refined.tags or [],
                "status": stored.get("status", "refined"),
                "created_at": stored.get("created_at"),
                "updated_at": stored.get("updated_at"),
                "provider": provider,
                "model": model,
            }
        }

    if job_type == "titles":
        request = TitleRequest(**payload)
        return {"text": await content_service.generate_titles(request, llm, store)}

    if job_type == "seo":
        request = SeoRequest(**payload)
        return {"text": await content_service.analyze_seo(request, llm, store)}

    if job_type == "publish_xiaohongshu":
        publication_id = int(payload["publication_id"])
        store.update_job(job_id, progress=20)
        publication = await create_publish_service(store).execute_publication(publication_id)
        return {"publication": publication}

    raise ValueError(f"Unknown job type: {job_type}")


def create_litellm_client() -> LiteLLMClient:
    return LiteLLMClient()
