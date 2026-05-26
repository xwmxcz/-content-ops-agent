from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path as ApiPath, UploadFile, status
from fastapi.responses import FileResponse

from src.api.dependencies import get_publish_service, get_store
from src.api.schemas.media import MediaAssetResponse, MediaUploadResponse
from src.api.services.publish_service import PublicationValidationError, PublishService
from src.storage import ContentStore
from src.utils import config


router = APIRouter()


@router.get("/content/{content_id}/media", response_model=list[MediaAssetResponse])
def list_media_assets(
    content_id: int = ApiPath(..., gt=0),
    store: ContentStore = Depends(get_store),
) -> list[dict]:
    if not store.get_content(content_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content not found")
    return [_with_file_url(item) for item in store.list_media_assets(content_id)]


@router.post("/media/upload", response_model=MediaUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_media(
    content_id: int = Form(...),
    media_type: str = Form(...),
    file: UploadFile = File(...),
    store: ContentStore = Depends(get_store),
    publish_service: PublishService = Depends(get_publish_service),
) -> dict:
    content = store.get_content(content_id)
    if not content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content not found")

    try:
        publish_service.validate_upload(media_type, file.filename or "upload", file.content_type)
    except PublicationValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    existing_assets = store.list_media_assets(content_id, media_type=media_type)
    if media_type == "image" and len(existing_assets) >= config.MEDIA_MAX_IMAGE_COUNT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {config.MEDIA_MAX_IMAGE_COUNT} images are allowed per content item",
        )
    if media_type == "video" and existing_assets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only one video is allowed per content item in v1",
        )

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")
    if media_type == "video":
        max_size = config.MEDIA_MAX_VIDEO_SIZE_MB * 1024 * 1024
        if len(payload) > max_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Video file exceeds {config.MEDIA_MAX_VIDEO_SIZE_MB} MB",
            )

    storage_root = Path(config.MEDIA_STORAGE_ROOT).resolve()
    target_dir = storage_root / str(content_id) / media_type
    target_dir.mkdir(parents=True, exist_ok=True)

    original_name = Path(file.filename or f"{media_type}.bin")
    target_path = target_dir / f"{uuid4().hex}{original_name.suffix.lower()}"
    target_path.write_bytes(payload)

    asset = store.save_media_asset(
        content_id=content_id,
        media_type=media_type,
        source_type="upload",
        file_name=original_name.name,
        file_path=str(target_path),
        mime_type=file.content_type,
    )
    return _with_file_url(asset)


@router.delete("/media/{media_id}", response_model=dict)
def delete_media_asset(
    media_id: int = ApiPath(..., gt=0),
    store: ContentStore = Depends(get_store),
) -> dict:
    asset = store.delete_media_asset(media_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media asset not found")

    file_path = _media_file_path(asset)
    if file_path and file_path.exists():
        file_path.unlink()
    return {"deleted": True}


@router.get("/media/{media_id}/file")
def get_media_file(
    media_id: int = ApiPath(..., gt=0),
    store: ContentStore = Depends(get_store),
):
    asset = store.get_media_asset(media_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media asset not found")

    file_path = _media_file_path(asset)
    if not file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media file not found")
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media file not found")
    return FileResponse(path=file_path, media_type=asset.get("mime_type"), filename=asset.get("file_name"))


def _media_file_path(asset: dict) -> Path | None:
    try:
        media_root = Path(config.MEDIA_STORAGE_ROOT).resolve()
        file_path = Path(asset["file_path"]).resolve()
    except (KeyError, OSError):
        return None
    if file_path == media_root or media_root not in file_path.parents:
        return None
    return file_path


def _with_file_url(asset: dict) -> dict:
    payload = dict(asset)
    payload["file_url"] = f"/api/media/{asset['id']}/file"
    return payload
