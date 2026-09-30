"""In-memory execution state rebuilt from the existing PostgreSQL checkpoints."""

from dataclasses import dataclass, field

from src.api.schemas.agent import PipelinePlanStep, PipelineRunRequest


@dataclass
class PipelineExecution:
    request: PipelineRunRequest
    run_id: str
    thread_id: str
    provider: str
    litellm_model: str
    research_tools: tuple[str, ...]
    plan: list[PipelinePlanStep] = field(default_factory=list)
    outputs: dict[int, str] = field(default_factory=dict)
    revisions: int = 0
    index: int = 0
    total_prompt: int = 0
    total_completion: int = 0
    total_cost: float = 0.0
    cancelled: bool = False
    step_succeeded: bool = True
