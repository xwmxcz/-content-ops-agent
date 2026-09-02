import shutil
from pathlib import Path as FilePath

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, status

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
from src.llm.litellm_client import LLMConfigurationError, LLMGenerationError, LiteLLMClient
from src.storage import ContentStore
from src.utils import config
from src.utils.idempotency import (
    DuplicateRequestInFlight,
    IdempotencyKeyConflict,
    request_key,
)


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
def get_content(content_id: int = Path(..., gt=0), store: ContentStore = Depends(get_store)) -> dict:
    content = store.get_content(content_id)
    if not content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content not found")
    return content


@router.post("/{content_id}/archive", response_model=dict)
def archive_content(content_id: int = Path(..., gt=0), store: ContentStore = Depends(get_store)) -> dict:
    if not store.archive_content(content_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content not found")
    return {"archived": True}


@router.delete("/{content_id}", response_model=dict)
def delete_content(content_id: int = Path(..., gt=0), store: ContentStore = Depends(get_store)) -> dict:
    deleted = store.delete_content(content_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content not found")
    _delete_local_media_files(content_id, deleted.get("media_assets", []))
    return {"deleted": True}


@router.post("/generate", response_model=GenerateResponse, status_code=status.HTTP_201_CREATED)
async def generate_content(
    request: GenerateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    store: ContentStore = Depends(get_store),
    llm: LiteLLMClient = Depends(get_litellm_client),
) -> dict:
    try:
        with request_key(idempotency_key):
            content_id, generated, provider, model = await content_service.generate_content(request, llm, store)
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LLMGenerationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except DuplicateRequestInFlight as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IdempotencyKeyConflict as exc:
        # Literal 422: `HTTP_422_UNPROCESSABLE_ENTITY` is deprecated on Starlette
        # 1.6 while `HTTP_422_UNPROCESSABLE_CONTENT` is absent on the older
        # versions that `fastapi>=0.115` still allows.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    store: ContentStore = Depends(get_store),
    llm: LiteLLMClient = Depends(get_litellm_client),
) -> dict:
    try:
        with request_key(idempotency_key):
            content_id, refined, provider, model = await content_service.refine_content(request, llm, store)
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LLMGenerationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DuplicateRequestInFlight as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IdempotencyKeyConflict as exc:
        # See the note on /generate: the 422 constant spelling is version-split.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LLMGenerationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
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
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LLMGenerationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _delete_local_media_files(content_id: int, media_assets: list[dict]) -> None:
    media_root = FilePath(config.MEDIA_STORAGE_ROOT).resolve()
    content_dir = (media_root / str(content_id)).resolve()
    if content_dir.exists() and (content_dir == media_root or media_root in content_dir.parents):
        shutil.rmtree(content_dir, ignore_errors=True)

    for asset in media_assets:
        file_path = FilePath(asset.get("file_path", ""))
        try:
            resolved = file_path.resolve()
        except OSError:
            continue
        if resolved.exists() and media_root in resolved.parents:
            resolved.unlink(missing_ok=True)
