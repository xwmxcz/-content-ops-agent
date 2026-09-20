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


# The metric columns are 32-bit integers; reject what they cannot hold up front.
_METRIC_MAX = 2_000_000_000


class ContentMetricsRequest(BaseModel):
    """One platform's current running totals for a piece of content."""

    platform: str = Field(..., min_length=1, max_length=50, pattern=r"^\s*[\w-]+\s*$")
    views: int = Field(0, ge=0, le=_METRIC_MAX)
    likes: int = Field(0, ge=0, le=_METRIC_MAX)
    comments: int = Field(0, ge=0, le=_METRIC_MAX)
    shares: int = Field(0, ge=0, le=_METRIC_MAX)


class ContentMetricsResponse(BaseModel):
    id: int
    content_id: int
    platform: str | None = None
    views: int
    likes: int
    comments: int
    shares: int
    engagement_rate: float
    recorded_at: str | None = None


class MetricsImportRow(ContentMetricsRequest):
    content_id: int = Field(..., gt=0)


class MetricsImportRequest(BaseModel):
    rows: list[MetricsImportRow] = Field(..., min_length=1, max_length=500)


class MetricsImportResponse(BaseModel):
    recorded: int
    # Rows naming content that is not in the caller's workspace are skipped, not
    # fatal: one stale id in a spreadsheet should not reject the other 499 rows.
    missing_content_ids: list[int] = Field(default_factory=list)
