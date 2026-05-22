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


class PlanStep(BaseModel):
    index: int
    description: str
    tool_hint: Optional[str] = None
    status: Literal["pending", "running", "completed", "failed", "skipped"] = "pending"


class ChatToolEvent(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    output: str = ""
    status: Literal["completed", "failed"] = "completed"
    error: Optional[str] = None
    plan_step_index: Optional[int] = None
    attempt: int = 1
    duration_ms: int = 0


class ChatResponse(BaseModel):
    message_id: int
    thread_id: str
    response: str
    provider: str
    model: str
    tool_events: list[ChatToolEvent] = Field(default_factory=list)
    plan: list[PlanStep] = Field(default_factory=list)


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
    plan: list[PlanStep] = Field(default_factory=list)
    status: str
    created_at: Optional[str] = None


class AgentRunRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    content_type: ContentType
    style: ContentStyle = ContentStyle.CASUAL
    keywords: Optional[list[str]] = None
    length: Literal["short", "medium", "long"] = "medium"
    mode: Literal["agent", "workflow"] = "agent"
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
    tool_events: list[ChatToolEvent] = Field(default_factory=list)
    duration_ms: int = 0
    error: Optional[str] = None


class AgentFinalContent(BaseModel):
    title: Optional[str] = None
    content: str
    content_type: str
    style: str
    tags: list[str] = Field(default_factory=list)
    status: str = "agent_final"


class AgentRunResponse(BaseModel):
    run_id: str
    thread_id: str
    steps: list[AgentStep]
    final_content: AgentFinalContent
    saved_content_id: Optional[int] = None
    provider: str
    model: str


SubAgentId = Literal["strategy", "writer", "editor", "reviewer", "researcher", "fact_checker"]


class SubAgentToolEvent(BaseModel):
    """One tool invocation made by a sub-agent during its step."""
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    status: Literal["started", "completed", "failed"] = "completed"
    preview: str = ""
    error: Optional[str] = None
    duration_ms: int = 0


class PipelinePlanStep(BaseModel):
    index: int
    agent_id: SubAgentId
    description: str
    instruction: str = ""
    inputs_from: list[int] = Field(default_factory=list)
    status: Literal["pending", "running", "completed", "failed", "skipped"] = "pending"
    output: str = ""
    duration_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_estimate: float = 0.0
    revised_at: Optional[int] = None
    tool_events: list[SubAgentToolEvent] = Field(default_factory=list)


class PipelineRunRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    content_type: ContentType
    style: ContentStyle = ContentStyle.CASUAL
    keywords: Optional[list[str]] = None
    length: Literal["short", "medium", "long"] = "medium"
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: float = Field(0.7, ge=0.0, le=1.0)
    max_tokens: int = Field(2048, ge=128, le=8192)
    save_final: bool = True
    thread_id: Optional[str] = None
    use_web_search: bool = True
    use_history_search: bool = True
    research_focus: Optional[str] = None  # optional hint, e.g. "compare alternatives", "verify claims"


class PipelineRunResponse(BaseModel):
    run_id: str
    thread_id: str
    plan: list[PipelinePlanStep]
    final_content: AgentFinalContent
    saved_content_id: Optional[int] = None
    provider: str
    model: str
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cost: float = 0.0
    revision_count: int = 0
    status: Literal["running", "completed", "failed", "cancelled"] = "completed"
    error: Optional[str] = None


class PipelineRunHandle(BaseModel):
    """Returned immediately from POST /api/agent/runs so the client can subscribe to SSE."""
    run_id: str
    thread_id: str
    provider: str
    model: str
