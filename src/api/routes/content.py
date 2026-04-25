from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.dependencies import get_litellm_client, get_store
from src.api.schemas.content import (
    ContentResponse,
    ContentSummary,
    GenerateRequest,
    GenerateResponse,
    RefineRequest,
    SeoRequest,
    TextResult,
    TitleRequest,
)
from src.api.services import content_service
from src.llm.litellm_client import LiteLLMClient
from src.storage import ContentStore


router = APIRouter()


@router.get("", response_model=list[ContentSummary])
def list_contents(
    status_filter: str | None = Query(default=None, alias="status"),
    content_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    store: ContentStore = Depends(get_store),
) -> list[dict]:
    return store.list_contents(status=status_filter, content_type=content_type, limit=limit, offset=offset)


@router.get("/{content_id}", response_model=ContentResponse)
def get_content(content_id: int, store: ContentStore = Depends(get_store)) -> dict:
    content = store.get_content(content_id)
    if not content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content not found")
    return content


@router.post("/generate", response_model=GenerateResponse, status_code=status.HTTP_201_CREATED)
async def generate_content(
    request: GenerateRequest,
    store: ContentStore = Depends(get_store),
    llm: LiteLLMClient = Depends(get_litellm_client),
) -> dict:
    try:
        content_id, generated, provider, model = await content_service.generate_content(request, llm, store)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
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


@router.post("/refine", response_model=GenerateResponse, status_code=status.HTTP_201_CREATED)
async def refine_content(
    request: RefineRequest,
    store: ContentStore = Depends(get_store),
    llm: LiteLLMClient = Depends(get_litellm_client),
) -> dict:
    try:
        content_id, refined, provider, model = await content_service.refine_content(request, llm, store)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    stored = store.get_content(content_id) or {}
    return {
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


@router.post("/titles", response_model=TextResult)
async def generate_titles(
    request: TitleRequest,
    store: ContentStore = Depends(get_store),
    llm: LiteLLMClient = Depends(get_litellm_client),
) -> TextResult:
    try:
        return TextResult(result=await content_service.generate_titles(request, llm, store))
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/seo", response_model=TextResult)
async def analyze_seo(
    request: SeoRequest,
    store: ContentStore = Depends(get_store),
    llm: LiteLLMClient = Depends(get_litellm_client),
) -> TextResult:
    try:
        return TextResult(result=await content_service.analyze_seo(request, llm, store))
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
