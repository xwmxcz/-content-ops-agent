from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from src.api.dependencies import get_litellm_client
from src.api.schemas.agent import ChatRequest, ChatResponse
from src.api.services.content_service import resolve_provider
from src.llm.litellm_client import LiteLLMClient


router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    llm: LiteLLMClient = Depends(get_litellm_client),
) -> ChatResponse:
    provider = resolve_provider(None)
    try:
        response = await llm.generate(
            provider=provider,
            model=None,
            messages=[
                {
                    "role": "system",
                    "content": "You are Content Ops Agent, an assistant for content creation and operations.",
                },
                {"role": "user", "content": request.message},
            ],
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ChatResponse(thread_id=request.thread_id or "default", response=response)


@router.get("/stream")
async def stream(message: str, thread_id: str = "default"):
    async def events():
        yield "event: message\ndata: Streaming transport is ready. Use POST /api/agent/chat for full replies in v1.\n\n"
        yield f"event: done\ndata: {thread_id}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
