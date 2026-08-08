"""Job runner shared by FastAPI background tasks and RQ workers."""
from __future__ import annotations

import asyncio
from typing import Any

from src.api.schemas.agent import AgentRunRequest
from src.api.schemas.content import GenerateRequest, RefineRequest, SeoRequest, TitleRequest
from src.api.services import content_service
from src.api.services.agent_pipeline import PipelineExecutionError, run_agent_pipeline
from src.api.services.publish_service import PublicationValidationError, create_publish_service
from src.integrations.mcp_client import McpClientError
from src.llm.litellm_client import LLMConfigurationError, LLMGenerationError, LiteLLMClient
from src.storage import ContentStore
from src.utils import config


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
        store.update_run(run_id, status="failed", error=str(exc))
        store.append_run_event(run_id, "run_failed", {"error": str(exc) or exc.__class__.__name__})


async def run_job_async(job_id: str, store: ContentStore) -> None:
    job = store.get_job(job_id)
    if not job:
        return
    if job["status"] not in {"queued", "failed"}:
        return

    attempts = int(job.get("attempts") or 0) + 1
    job = store.start_job(job_id, attempts=attempts, progress=5)
    if not job:
        return
    llm = create_litellm_client()

    try:
        result = await _execute_job(job, llm, store)
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
        store.update_job(job_id, status="failed", progress=100, error=str(exc))
    except Exception as exc:
        if _is_cancelled(job_id, store):
            return
        message = str(exc).strip() or "Job failed unexpectedly"
        store.update_job(job_id, status="failed", progress=100, error=message)
    else:
        if _is_cancelled(job_id, store):
            return
        store.update_job(job_id, status="completed", progress=100, result=result, error=None)


def _is_cancelled(job_id: str, store: ContentStore) -> bool:
    current = store.get_job(job_id)
    return bool(current and current.get("status") == "cancelled")


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
