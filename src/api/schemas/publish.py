from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


PublicationStatus = Literal["draft", "queued", "running", "scheduled", "completed", "failed"]
PublishType = Literal["image_post", "video_post"]


class XiaohongshuPublishRequest(BaseModel):
    content_id: int = Field(..., gt=0)
    publish_type: PublishType
    title: Optional[str] = None
    content: Optional[str] = None
    media_ids: Optional[list[int]] = None
    scheduled_at: Optional[datetime] = None
    tags: Optional[list[str]] = None
    visibility: Literal["public", "self-only", "friends-only"] = "public"
    is_original: bool = False


class PublicationResponse(BaseModel):
    id: int
    content_id: int
    platform: str
    publish_type: PublishType
    status: PublicationStatus
    title: Optional[str] = None
    body: str
    scheduled_at: Optional[str] = None
    published_at: Optional[str] = None
    external_post_id: Optional[str] = None
    error_message: Optional[str] = None
    request_payload: dict[str, Any] | None = None
    response_payload: dict[str, Any] | None = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PublishActionResponse(BaseModel):
    publication: PublicationResponse
    job_id: str


class XiaohongshuLoginStatusResponse(BaseModel):
    connected: bool
    status_text: str = ""
    details: dict[str, Any] | None = None
