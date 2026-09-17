from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, Field, PrivateAttr, model_validator

from src.models import ContentStyle, ContentType


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    thread_id: str | None = None
    provider: str | None = None
    model: str | None = None
    temperature: float = Field(0.7, ge=0.0, le=1.0)
    max_tokens: int = Field(2048, ge=128, le=8192)


ChatIntentName = Literal[
    "content_create",
    "content_refine",
    "title_generate",
    "seo_optimize",
    "content_search",
    "topic_strategy",
    "performance_review",
    "calendar_view",
    "schedule_propose",
    "schedule_commit",
    "memory_update",
    "action_confirm",
    "smalltalk",
    "clarify",
    "unknown",
]


class ChatIntent(BaseModel):
    # Server-owned, request-local authorization evidence. PrivateAttr is never
    # accepted from model JSON, persisted in intent slots, or serialized to API
    # clients/history. The executor authorizes against the private deep copy,
    # not public ``slots``, so later slot mutation cannot change an approval.
    _server_confirmation_validated: bool = PrivateAttr(default=False)
    _server_approved_tool_name: str | None = PrivateAttr(default=None)
    _server_approved_args: dict[str, Any] | None = PrivateAttr(default=None)
    # Durable one-time capability for the approved call. Argument evidence alone
    # is request-local and replayable within a turn; the executor additionally
    # requires this id so a confirmed write is consumable exactly once.
    _server_approved_action_id: str | None = PrivateAttr(default=None)

    name: ChatIntentName
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    slots: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = False
    allowed_tools: list[str] = Field(default_factory=list)
    route_surface: Literal["chat", "studio", "publish", "none"] = "chat"
    route_reason: str | None = None
    clarification: str | None = None

    def bind_server_approval(
        self,
        tool_name: str,
        args: dict[str, Any],
        action_id: str | None = None,
    ) -> None:
        """Attach immutable-by-convention authorization evidence for this request.

        ``action_id`` references a confirmed ``proposed_actions`` row. Without it
        the executor has argument evidence but no consumable capability, so the
        write still fails closed.
        """
        self._server_approved_tool_name = tool_name
        self._server_approved_args = deepcopy(args)
        self._server_approved_action_id = action_id
        self._server_confirmation_validated = True


class PlanStep(BaseModel):
    index: int
    description: str
    tool_hint: str | None = None
    status: Literal["pending", "running", "completed", "failed", "skipped"] = "pending"


class ChatToolEvent(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    output: str = ""
    status: Literal["completed", "failed", "proposed"] = "completed"
    error: str | None = None
    plan_step_index: int | None = None
    attempt: int = 1
    duration_ms: int = 0
    # Durable proposal id a later confirmation turn must reference. Display and
    # correlation only; it is never accepted as authorization from a client.
    action_id: str | None = None


class ChatResponse(BaseModel):
    message_id: int
    thread_id: str
    response: str
    provider: str
    model: str
    intent: ChatIntent | None = None
    tool_events: list[ChatToolEvent] = Field(default_factory=list)
    plan: list[PlanStep] = Field(default_factory=list)


class AgentThreadResponse(BaseModel):
    id: str
    title: str | None = None
    last_provider: str | None = None
    last_model: str | None = None
    pinned: bool = False
    archived: bool = False
    title_pinned: bool = False
    message_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class AgentThreadUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    pinned: bool | None = None
    archived: bool | None = None

    @model_validator(mode="after")
    def _require_one_field(self) -> "AgentThreadUpdateRequest":
        if self.title is None and self.pinned is None and self.archived is None:
            raise ValueError("at least one of title / pinned / archived is required")
        return self


class AgentSearchHit(BaseModel):
    message_id: int
    thread_id: str
    role: Literal["user", "assistant"]
    content: str
    provider: str | None = None
    model: str | None = None
    created_at: str | None = None


class AgentMessageResponse(BaseModel):
    id: int
    thread_id: str
    role: Literal["user", "assistant"]
    content: str
    provider: str | None = None
    model: str | None = None
    intent: ChatIntent | None = None
    tool_events: list[ChatToolEvent] = Field(default_factory=list)
    plan: list[PlanStep] = Field(default_factory=list)
    status: str
    created_at: str | None = None


class ProposedActionCreate(BaseModel):
    thread_id: str = Field(..., min_length=1, max_length=80)
    tool_name: str = Field(..., min_length=1, max_length=80)
    args: dict[str, Any] = Field(default_factory=dict)
    impact_summary: str | None = Field(default=None, max_length=500)


class ProposedActionResponse(BaseModel):
    id: str
    thread_id: str
    requester: str | None = None
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    args_hash: str
    impact_summary: str
    status: Literal["proposed", "confirmed", "consumed", "cancelled", "expired"]
    proposing_message_id: int | None = None
    consuming_message_id: int | None = None
    created_at: str | None = None
    expires_at: str | None = None
    confirmed_at: str | None = None
    consumed_at: str | None = None
    cancelled_at: str | None = None


class AgentRunRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    content_type: ContentType
    style: ContentStyle = ContentStyle.CASUAL
    keywords: list[str] | None = None
    length: Literal["short", "medium", "long"] = "medium"
    mode: Literal["agent", "workflow"] = "agent"
    provider: str | None = None
    model: str | None = None
    temperature: float = Field(0.7, ge=0.0, le=1.0)
    max_tokens: int = Field(2048, ge=128, le=8192)
    save_final: bool = True
    thread_id: str | None = None


class AgentStep(BaseModel):
    id: str
    name: str
    role: str
    status: Literal["pending", "running", "completed", "failed"]
    input_summary: str
    output: str = ""
    tool_events: list[ChatToolEvent] = Field(default_factory=list)
    duration_ms: int = 0
    error: str | None = None


class AgentFinalContent(BaseModel):
    title: str | None = None
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
    saved_content_id: int | None = None
    provider: str
    model: str


SubAgentId = Literal["strategy", "writer", "editor", "reviewer", "researcher", "fact_checker"]


class SubAgentToolEvent(BaseModel):
    """One tool invocation made by a sub-agent during its step."""

    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    status: Literal["started", "completed", "failed"] = "completed"
    preview: str = ""
    error: str | None = None
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
    revised_at: int | None = None
    tool_events: list[SubAgentToolEvent] = Field(default_factory=list)


class PipelineRunRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    content_type: ContentType
    style: ContentStyle = ContentStyle.CASUAL
    keywords: list[str] | None = None
    length: Literal["short", "medium", "long"] = "medium"
    provider: str | None = None
    model: str | None = None
    temperature: float = Field(0.7, ge=0.0, le=1.0)
    max_tokens: int = Field(2048, ge=128, le=8192)
    save_final: bool = True
    thread_id: str | None = None
    use_web_search: bool = True
    use_history_search: bool = True
    research_focus: str | None = None  # optional hint, e.g. "compare alternatives", "verify claims"


class PipelineRunResponse(BaseModel):
    run_id: str
    thread_id: str
    plan: list[PipelinePlanStep]
    final_content: AgentFinalContent
    saved_content_id: int | None = None
    provider: str
    model: str
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cost: float = 0.0
    revision_count: int = 0
    status: Literal["running", "completed", "failed", "cancelled"] = "completed"
    error: str | None = None


class PipelineRunHandle(BaseModel):
    """Returned immediately from POST /api/agent/runs so the client can subscribe to SSE."""

    run_id: str
    thread_id: str
    provider: str
    model: str
