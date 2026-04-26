from typing import Literal, Optional

from pydantic import BaseModel, Field

from src.models import ContentStyle, ContentType


class GenerateRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    content_type: ContentType
    style: ContentStyle = ContentStyle.CASUAL
    keywords: Optional[list[str]] = None
    length: Literal["short", "medium", "long"] = "medium"
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: float = Field(0.7, ge=0.0, le=1.0)
    max_tokens: int = Field(2048, ge=128, le=8192)


class RefineRequest(BaseModel):
    content_id: int = Field(..., gt=0)
    instruction: Optional[str] = None
    new_style: Optional[ContentStyle] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: float = Field(0.7, ge=0.0, le=1.0)
    max_tokens: int = Field(2048, ge=128, le=8192)


class TitleRequest(BaseModel):
    topic: Optional[str] = None
    content_id: Optional[int] = Field(default=None, gt=0)
    content_type: ContentType = ContentType.XIAOHONGSHU
    count: int = Field(5, ge=1, le=10)
    provider: Optional[str] = None
    model: Optional[str] = None


class SeoRequest(BaseModel):
    content_id: int = Field(..., gt=0)
    provider: Optional[str] = None
    model: Optional[str] = None


class ContentResponse(BaseModel):
    id: int
    title: Optional[str] = None
    content: str
    content_type: str
    style: str
    tags: list[str] = Field(default_factory=list)
    status: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ContentSummary(BaseModel):
    id: int
    title: Optional[str] = None
    content: str
    content_type: str
    style: str
    status: str
    created_at: Optional[str] = None


class GenerateResponse(ContentResponse):
    provider: str
    model: str


class TextResult(BaseModel):
    result: str
