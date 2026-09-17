from typing import Literal

from pydantic import BaseModel, Field

from src.models import ContentStyle, ContentType


class GenerateRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    content_type: ContentType
    style: ContentStyle = ContentStyle.CASUAL
    keywords: list[str] | None = None
    length: Literal["short", "medium", "long"] = "medium"
    provider: str | None = None
    model: str | None = None
    temperature: float = Field(0.7, ge=0.0, le=1.0)
    max_tokens: int = Field(2048, ge=128, le=8192)


class RefineRequest(BaseModel):
    content_id: int = Field(..., gt=0)
    instruction: str | None = None
    new_style: ContentStyle | None = None
    provider: str | None = None
    model: str | None = None
    temperature: float = Field(0.7, ge=0.0, le=1.0)
    max_tokens: int = Field(2048, ge=128, le=8192)


class TitleRequest(BaseModel):
    topic: str | None = None
    content_id: int | None = Field(default=None, gt=0)
    content_type: ContentType = ContentType.XIAOHONGSHU
    count: int = Field(5, ge=1, le=10)
    provider: str | None = None
    model: str | None = None


class SeoRequest(BaseModel):
    content_id: int = Field(..., gt=0)
    provider: str | None = None
    model: str | None = None


class ContentResponse(BaseModel):
    id: int
    title: str | None = None
    content: str
    content_type: str
    style: str
    tags: list[str] = Field(default_factory=list)
    status: str
    created_at: str | None = None
    updated_at: str | None = None


class ContentSummary(BaseModel):
    id: int
    title: str | None = None
    content: str
    content_type: str
    style: str
    status: str
    created_at: str | None = None


class GenerateResponse(ContentResponse):
    provider: str
    model: str


class TextResult(BaseModel):
    result: str
