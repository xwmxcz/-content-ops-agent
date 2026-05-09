from typing import Literal, Optional

from pydantic import BaseModel, Field


MediaType = Literal["image", "video"]
MediaSourceType = Literal["upload", "generated", "external_url"]


class MediaAssetResponse(BaseModel):
    id: int
    content_id: int
    media_type: MediaType
    source_type: MediaSourceType
    file_name: str
    file_path: str
    file_url: str
    mime_type: Optional[str] = None
    sort_order: int = 0
    provider: Optional[str] = None
    generation_params: dict | None = None
    created_at: Optional[str] = None


class MediaUploadResponse(MediaAssetResponse):
    pass


class MediaUploadRequest(BaseModel):
    content_id: int = Field(..., gt=0)
    media_type: MediaType
