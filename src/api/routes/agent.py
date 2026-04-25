from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from src.api.dependencies import get_chat_agent_service, get_litellm_client, get_store
from src.api.schemas.agent import (
    AgentMessageResponse,
    AgentRunRequest,
    AgentRunResponse,
    AgentThreadResponse,
    ChatRequest,
    ChatResponse,
)
from src.api.services.chat_agent import ChatAgentExecutionError, ChatAgentService
from src.api.services.agent_pipeline import PipelineExecutionError, run_agent_pipeline
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
async def stream(message: str, thread_id: str = "default"):
    async def events():
        yield "event: message\ndata: Streaming transport is ready. Use POST /api/agent/chat for full replies in v1.\n\n"
        yield f"event: done\ndata: {thread_id}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
