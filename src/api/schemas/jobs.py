from typing import Any, Literal

from pydantic import BaseModel, Field

from src.api.schemas.agent import AgentRunRequest
from src.api.schemas.content import GenerateRequest, RefineRequest, SeoRequest, TitleRequest


JobStatus = Literal["queued", "running", "completed", "failed"]
JobType = Literal["content_generation", "agent_run", "refine", "titles", "seo"]


class JobResponse(BaseModel):
    id: str
    job_type: JobType
    status: JobStatus
    progress: int = Field(0, ge=0, le=100)
    result: dict[str, Any] | None = None
    error: str | None = None
    provider: str | None = None
    model: str | None = None
    attempts: int = 0
    created_at: str | None = None
    updated_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class ContentGenerationJobRequest(GenerateRequest):
    pass


class AgentRunJobRequest(AgentRunRequest):
    pass


class RefineJobRequest(RefineRequest):
    pass


class TitlesJobRequest(TitleRequest):
    pass


class SeoJobRequest(SeoRequest):
    pass
