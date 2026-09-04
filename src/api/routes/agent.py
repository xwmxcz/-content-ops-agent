import asyncio
import time

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from src.api.dependencies import get_chat_agent_service, get_litellm_client, get_store
from src.api.schemas.agent import (
    AgentMessageResponse,
    AgentRunRequest,
    AgentRunResponse,
    AgentSearchHit,
    AgentThreadResponse,
    AgentThreadUpdateRequest,
    ChatRequest,
    ChatResponse,
    PipelineRunHandle,
    PipelineRunRequest,
    ProposedActionCreate,
    ProposedActionResponse,
)
from src.api.services.chat_agent import ChatAgentExecutionError, ChatAgentService
from src.api.services.agent_pipeline import PipelineExecutionError, run_agent_pipeline
from src.api.services.dynamic_pipeline import DynamicPipeline
from src.api.services.tool_policy import SIDE_EFFECT_TOOLS
from src.jobs.queue import JobQueueError, enqueue_pipeline_run
from src.llm.litellm_client import LiteLLMClient
from src.storage import ContentStore
from src.utils import config


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

    Returns immediately with a run_id. The pipeline is dispatched via the job queue:
    FastAPI BackgroundTasks in `background` mode, or Redis/RQ in `rq` mode so the
    long multi-step LLM workload runs on a worker rather than the API process.
    SSE consumers read events from the agent_run_events table either way.
    """
    from src.api.services.content_service import resolve_provider
    from src.utils import config

    try:
        DynamicPipeline._validate_research_sources(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

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

    try:
        enqueue_pipeline_run(
            run_id,
            request.model_dump(mode="json"),
            store.database_url,
            background_tasks,
        )
    except JobQueueError as exc:
        # The run row was pre-created; flip it to failed and emit a terminal event
        # so any SSE consumer that already subscribed sees the failure instead of
        # hanging until the stream deadline.
        store.transition_run_and_append_event(
            run_id,
            expected_statuses={"running"},
            new_status="failed",
            event_type="run_failed",
            payload={"error": str(exc)},
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return PipelineRunHandle(run_id=run_id, thread_id=thread_id, provider=provider, model=model)


@router.get("/runs/{run_id}", response_model=dict)
def get_pipeline_run(run_id: str, store: ContentStore = Depends(get_store)) -> dict:
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} was not found")
    return run


@router.get("/runs/{run_id}/stream")
async def stream_pipeline_run(
    run_id: str,
    store: ContentStore = Depends(get_store),
    after_seq: int | None = Query(default=None, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    if not store.get_run(run_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} was not found")

    async def event_stream():
        last_seq = after_seq if after_seq is not None else _parse_last_event_id(last_event_id)
        deadline = time.time() + config.SSE_STREAM_TIMEOUT_SECONDS
        terminal = {"run_complete", "run_failed", "run_cancelled"}
        yield "event: hello\ndata: {}\n\n"
        # Keepalives are comment frames: they prove liveness to the client and to
        # any intermediate proxy without consuming a sequence number, so they can
        # never be mistaken for a replayable run event.
        last_activity = time.time()
        while time.time() < deadline:
            events = store.list_run_events(run_id, after_seq=last_seq, limit=100)
            for evt in events:
                last_seq = evt["seq"]
                yield f"id: {evt['seq']}\nevent: {evt['event_type']}\ndata: {evt['payload']}\n\n"
                if evt["event_type"] in terminal:
                    return
            now = time.time()
            if events:
                last_activity = now
            elif now - last_activity >= config.SSE_KEEPALIVE_SECONDS:
                yield ": keepalive\n\n"
                last_activity = now
            await asyncio.sleep(config.SSE_POLL_INTERVAL_SECONDS)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _parse_last_event_id(value: str | None) -> int:
    if not value:
        return 0
    try:
        return max(0, int(value))
    except ValueError:
        return 0


@router.delete("/runs/{run_id}", response_model=dict)
def cancel_pipeline_run(run_id: str, store: ContentStore = Depends(get_store)) -> dict:
    """Request cancellation of an in-flight pipeline run.

    Sets `status="cancelled"` on the run row and appends a `run_cancelled` event,
    which terminates SSE streams immediately. The background task observes the
    flipped status at step boundaries (see DynamicPipeline.run) and breaks out of
    its loop — already-running sub-agents are allowed to finish, but no new step
    is started. Returns 404 if the run does not exist; calling DELETE on an
    already-terminal run is a no-op (returns the current status).
    """
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} was not found")
    if run["status"] in {"completed", "failed", "cancelled"}:
        return {"run_id": run_id, "status": run["status"], "cancelled": False}
    transitioned = store.transition_run_and_append_event(
        run_id,
        expected_statuses={"running"},
        new_status="cancelled",
        event_type="run_cancelled",
        payload={"run_id": run_id},
    )
    if transitioned is None:
        current = store.get_run(run_id)
        return {
            "run_id": run_id,
            "status": current["status"] if current else "unknown",
            "cancelled": False,
        }
    return {"run_id": run_id, "status": "cancelled", "cancelled": True}


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


@router.post(
    "/actions",
    response_model=ProposedActionResponse,
    status_code=status.HTTP_201_CREATED,
)
def propose_action(
    request: ProposedActionCreate,
    store: ContentStore = Depends(get_store),
) -> dict:
    """Record a write proposal without executing it.

    A proposal is not permission. It becomes executable only after a separate
    confirm call issues the one-time capability, and only for these exact
    arguments.
    """
    if request.tool_name not in SIDE_EFFECT_TOOLS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tool {request.tool_name} is not a registered write action",
        )
    if not store.get_agent_thread(request.thread_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thread {request.thread_id} was not found",
        )
    return store.create_proposed_action(
        thread_id=request.thread_id,
        tool_name=request.tool_name,
        args=request.args,
        impact_summary=request.impact_summary
        or f"Execute write tool {request.tool_name}",
        ttl_seconds=config.ACTION_CAPABILITY_TTL_SECONDS,
        requester=config.AUTH_USERNAME if config.AUTH_ENABLED else None,
    )


@router.get("/threads/{thread_id}/actions", response_model=list[ProposedActionResponse])
def list_thread_actions(
    thread_id: str,
    store: ContentStore = Depends(get_store),
    limit: int = Query(20, ge=1, le=100),
) -> list[dict]:
    if not store.get_agent_thread(thread_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thread {thread_id} was not found",
        )
    store.expire_proposed_actions(thread_id=thread_id)
    return store.list_proposed_actions(thread_id, limit=limit)


@router.post("/actions/{action_id}/confirm", response_model=ProposedActionResponse)
def confirm_action(
    action_id: str,
    store: ContentStore = Depends(get_store),
) -> dict:
    """Issue the one-time capability for a pending proposal.

    Concurrent confirmations of the same proposal serialize in the store, so only
    the first receives 200; the rest see 409 and no second capability exists.
    """
    confirmed = store.confirm_proposed_action(action_id)
    if confirmed:
        return confirmed
    existing = store.get_proposed_action(action_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action {action_id} was not found",
        )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Action {action_id} is {existing['status']} and cannot be confirmed",
    )


@router.post("/actions/{action_id}/cancel", response_model=ProposedActionResponse)
def cancel_action(
    action_id: str,
    store: ContentStore = Depends(get_store),
) -> dict:
    cancelled = store.cancel_proposed_action(action_id)
    if cancelled:
        return cancelled
    existing = store.get_proposed_action(action_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action {action_id} was not found",
        )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Action {action_id} is {existing['status']} and cannot be cancelled",
    )


@router.get("/threads", response_model=list[AgentThreadResponse])
def list_threads(
    store: ContentStore = Depends(get_store),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    include_archived: bool = Query(False),
    q: str | None = Query(None, max_length=200),
) -> list[dict]:
    return store.list_agent_threads(
        limit=limit,
        offset=offset,
        include_archived=include_archived,
        q=q,
    )


@router.get("/threads/search", response_model=list[AgentSearchHit])
def search_threads(
    store: ContentStore = Depends(get_store),
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(20, ge=1, le=100),
    thread_id: str | None = Query(None, max_length=80),
) -> list[dict]:
    hits = store.search_agent_messages(q, limit=limit, thread_id=thread_id)
    return [
        {
            "message_id": hit["id"],
            "thread_id": hit["thread_id"],
            "role": hit["role"],
            "content": hit["content"],
            "provider": hit.get("provider"),
            "model": hit.get("model"),
            "created_at": hit.get("created_at"),
        }
        for hit in hits
    ]


@router.get("/threads/{thread_id}/messages", response_model=list[AgentMessageResponse])
def list_thread_messages(
    thread_id: str,
    store: ContentStore = Depends(get_store),
    limit: int = Query(200, ge=1, le=500),
    before_id: int | None = Query(None, ge=1),
) -> list[dict]:
    if not store.get_agent_thread(thread_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Thread {thread_id} was not found")
    return store.list_agent_messages(thread_id, limit=limit, before_id=before_id)


@router.patch("/threads/{thread_id}", response_model=AgentThreadResponse)
def update_thread(
    thread_id: str,
    request: AgentThreadUpdateRequest,
    store: ContentStore = Depends(get_store),
) -> dict:
    updated = store.update_agent_thread(
        thread_id,
        title=request.title,
        pinned=request.pinned,
        archived=request.archived,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Thread {thread_id} was not found")
    return updated


@router.delete("/threads/{thread_id}", response_model=dict)
def delete_thread(
    thread_id: str,
    store: ContentStore = Depends(get_store),
) -> dict:
    if not store.get_agent_thread(thread_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Thread {thread_id} was not found")
    # Deleted transcripts are untrusted and there is no longer a user-visible
    # confirmation surface after deletion. Never send them to an auto-applying
    # curator or mutate persistent memory from this route.
    if not store.delete_agent_thread(thread_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Thread {thread_id} was not found")
    return {"deleted": True}


@router.get("/stream")
async def legacy_stream(message: str, thread_id: str = "default"):
    async def events():
        yield "event: message\ndata: Streaming transport is ready. Use POST /api/agent/runs for full pipeline streaming.\n\n"
        yield f"event: done\ndata: {thread_id}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
