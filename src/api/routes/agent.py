import asyncio
import json
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from src.api.dependencies import get_chat_agent_service, get_litellm_client, get_store
from src.api.schemas.agent import (
    AgentMessageResponse,
    AgentRunRequest,
    AgentRunResponse,
    AgentThreadResponse,
    ChatRequest,
    ChatResponse,
    PipelineRunHandle,
    PipelineRunRequest,
)
from src.api.services.chat_agent import ChatAgentExecutionError, ChatAgentService
from src.api.services.agent_pipeline import PipelineExecutionError, run_agent_pipeline
from src.api.services.dynamic_pipeline import DynamicPipeline
from src.llm.litellm_client import LiteLLMClient
from src.storage import ContentStore


router = APIRouter()


@router.post("/run", response_model=AgentRunResponse, status_code=status.HTTP_201_CREATED)
async def run(
    request: AgentRunRequest,
    llm: LiteLLMClient = Depends(get_litellm_client),
    store: ContentStore = Depends(get_store),
) -> AgentRunResponse:
    try:
        return await run_agent_pipeline(request, llm, store)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PipelineExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": str(exc),
                "steps": [step.model_dump() for step in exc.steps],
            },
        ) from exc


@router.post("/runs", response_model=PipelineRunHandle, status_code=status.HTTP_202_ACCEPTED)
async def create_pipeline_run(
    request: PipelineRunRequest,
    background_tasks: BackgroundTasks,
    llm: LiteLLMClient = Depends(get_litellm_client),
    store: ContentStore = Depends(get_store),
) -> PipelineRunHandle:
    """Kick off a dynamic pipeline run; client subscribes to /runs/{id}/stream for events.

    Returns immediately with a run_id. The pipeline runs as a FastAPI BackgroundTask;
    SSE consumers read events from the agent_run_events table.
    """
    from src.api.services.content_service import resolve_provider
    from src.utils import config

    provider = resolve_provider(request.provider)
    model = request.model or config.get_model(provider)

    import uuid
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    thread_id = request.thread_id or run_id

    # Pre-create so the SSE GET handler doesn't 404 between accept and pipeline boot.
    store.create_run(
        run_id=run_id,
        topic=request.topic,
        content_type=request.content_type.value,
        style=request.style.value,
        provider=provider,
        model=model,
        thread_id=thread_id,
    )

    background_tasks.add_task(_run_pipeline_background, request, store.database_url, run_id)

    return PipelineRunHandle(run_id=run_id, thread_id=thread_id, provider=provider, model=model)


def _run_pipeline_background(request: PipelineRunRequest, database_url: str, run_id: str) -> None:
    """Sync wrapper invoked by BackgroundTasks (which runs sync callables in a threadpool).

    We open our own ContentStore so we don't share the request's session; this matches
    the pattern used in src/jobs/runner.py.
    """
    store = ContentStore(database_url=database_url)
    try:
        asyncio.run(_run_pipeline_async(request, store, run_id))
    finally:
        store.engine.dispose()


async def _run_pipeline_async(request: PipelineRunRequest, store: ContentStore, run_id: str) -> None:
    pipeline = DynamicPipeline(store=store, llm=LiteLLMClient())
    try:
        await pipeline.run(request, run_id=run_id)
    except Exception as exc:
        store.update_run(run_id, status="failed", error=str(exc))
        store.append_run_event(run_id, "run_failed", {"error": str(exc) or exc.__class__.__name__})


@router.get("/runs/{run_id}", response_model=dict)
def get_pipeline_run(run_id: str, store: ContentStore = Depends(get_store)) -> dict:
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} was not found")
    return run


@router.get("/runs/{run_id}/stream")
async def stream_pipeline_run(run_id: str, store: ContentStore = Depends(get_store)):
    if not store.get_run(run_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} was not found")

    async def event_stream():
        last_seq = 0
        deadline = time.time() + 600
        terminal = {"run_complete", "run_failed"}
        yield "event: hello\ndata: {}\n\n"
        while time.time() < deadline:
            events = store.list_run_events(run_id, after_seq=last_seq, limit=100)
            for evt in events:
                last_seq = evt["seq"]
                yield f"event: {evt['event_type']}\ndata: {evt['payload']}\n\n"
                if evt["event_type"] in terminal:
                    return
            await asyncio.sleep(0.4)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    agent_service: ChatAgentService = Depends(get_chat_agent_service),
) -> ChatResponse:
    try:
        return await agent_service.chat(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ChatAgentExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/threads", response_model=list[AgentThreadResponse])
def list_threads(store: ContentStore = Depends(get_store)) -> list[dict]:
    return store.list_agent_threads()


@router.get("/threads/{thread_id}/messages", response_model=list[AgentMessageResponse])
def list_thread_messages(thread_id: str, store: ContentStore = Depends(get_store)) -> list[dict]:
    if not store.get_agent_thread(thread_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Thread {thread_id} was not found")
    return store.list_agent_messages(thread_id, limit=200)


@router.delete("/threads/{thread_id}", response_model=dict)
def delete_thread(thread_id: str, store: ContentStore = Depends(get_store)) -> dict:
    if not store.delete_agent_thread(thread_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Thread {thread_id} was not found")
    return {"deleted": True}


@router.get("/stream")
async def legacy_stream(message: str, thread_id: str = "default"):
    async def events():
        yield "event: message\ndata: Streaming transport is ready. Use POST /api/agent/runs for full pipeline streaming.\n\n"
        yield f"event: done\ndata: {thread_id}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
