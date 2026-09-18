from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

PublicationStatus = Literal["draft", "queued", "running", "scheduled", "completed", "failed"]
PublishType = Literal["image_post", "video_post"]


class XiaohongshuPublishRequest(BaseModel):
    content_id: int = Field(..., gt=0)
    publish_type: PublishType
    title: str | None = None
    content: str | None = None
    media_ids: list[int] | None = None
    scheduled_at: datetime | None = None
    tags: list[str] | None = None
    visibility: Literal["public", "self-only", "friends-only"] = "public"
    is_original: bool = False


class PublicationResponse(BaseModel):
    id: int
    content_id: int
    platform: str
    publish_type: PublishType
    status: PublicationStatus
    title: str | None = None
    body: str
    scheduled_at: str | None = None
    published_at: str | None = None
    external_post_id: str | None = None
    error_message: str | None = None
    request_payload: dict[str, Any] | None = None
    response_payload: dict[str, Any] | None = None
    created_at: str | None = None
    updated_at: str | None = None


class PublishActionResponse(BaseModel):
    publication: PublicationResponse
    job_id: str


class XiaohongshuLoginStatusResponse(BaseModel):
    connected: bool
    status_text: str = ""
    details: dict[str, Any] | None = None
