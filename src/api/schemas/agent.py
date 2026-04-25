from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from src.models import ContentStyle, ContentType


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    thread_id: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: float = Field(0.7, ge=0.0, le=1.0)
    max_tokens: int = Field(2048, ge=128, le=8192)


class ChatToolEvent(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    output: str = ""
    status: Literal["completed", "failed"] = "completed"
    error: Optional[str] = None


class ChatResponse(BaseModel):
    message_id: int
    thread_id: str
    response: str
    provider: str
    model: str
    tool_events: list[ChatToolEvent] = Field(default_factory=list)


class AgentThreadResponse(BaseModel):
    id: str
    title: Optional[str] = None
    last_provider: Optional[str] = None
    last_model: Optional[str] = None
    message_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AgentMessageResponse(BaseModel):
    id: int
    thread_id: str
    role: Literal["user", "assistant"]
    content: str
    provider: Optional[str] = None
    model: Optional[str] = None
    tool_events: list[ChatToolEvent] = Field(default_factory=list)
    status: str
    created_at: Optional[str] = None


class AgentRunRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    content_type: ContentType
    style: ContentStyle = ContentStyle.CASUAL
    keywords: Optional[list[str]] = None
    length: str = "medium"
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: float = Field(0.7, ge=0.0, le=1.0)
    max_tokens: int = Field(2048, ge=128, le=8192)
    save_final: bool = True
    thread_id: Optional[str] = None


class AgentStep(BaseModel):
    id: str
    name: str
    role: str
    status: Literal["pending", "running", "completed", "failed"]
    input_summary: str
    output: str = ""
    duration_ms: int = 0
    error: Optional[str] = None


class AgentFinalContent(BaseModel):
    title: Optional[str] = None
    content: str
    content_type: str
    style: str
    tags: list[str] = []
    status: str = "agent_final"


class AgentRunResponse(BaseModel):
    run_id: str
    thread_id: str
    steps: list[AgentStep]
    final_content: AgentFinalContent
    saved_content_id: Optional[int] = None
    provider: str
    model: str
