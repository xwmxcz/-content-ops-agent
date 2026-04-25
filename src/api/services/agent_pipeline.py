"""Multi-agent content pipeline for the API layer."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from src.api.schemas.agent import AgentFinalContent, AgentRunRequest, AgentRunResponse, AgentStep
from src.api.services.content_service import resolve_provider
from src.llm.litellm_client import LiteLLMClient
from src.models import GeneratedContent
from src.storage import ContentStore
from src.utils import config


@dataclass(frozen=True)
class AgentDefinition:
    id: str
    name: str
    role: str
    system_prompt: str


class PipelineExecutionError(Exception):
    def __init__(self, message: str, steps: list[AgentStep]):
        super().__init__(message)
        self.steps = steps


AGENTS = [
    AgentDefinition(
        id="strategy",
        name="Strategy Agent",
        role="Content strategist",
        system_prompt=(
            "You are a senior content strategist. Create a concise strategy for the requested "
            "platform. Include audience, angle, structure, hook, and conversion intent. "
            "Write in the same language as the user's topic."
        ),
    ),
    AgentDefinition(
        id="writer",
        name="Writer Agent",
        role="Draft writer",
        system_prompt=(
            "You are a platform-native content writer. Use the strategy to produce a complete "
            "draft. Keep the output ready to edit and write in the same language as the user's topic."
        ),
    ),
    AgentDefinition(
        id="editor",
        name="Editor Agent",
        role="Content editor",
        system_prompt=(
            "You are a professional content editor. Improve clarity, rhythm, structure, platform fit, "
            "and persuasiveness. Return only the final polished content."
        ),
    ),
    AgentDefinition(
        id="review",
        name="Review Agent",
        role="Quality reviewer",
        system_prompt=(
            "You are a content quality reviewer. Score the final content from 1 to 100 and list "
            "strengths, risks, and practical improvements. Be concise."
        ),
    ),
]


async def run_agent_pipeline(
    request: AgentRunRequest,
    llm: LiteLLMClient,
    store: ContentStore,
) -> AgentRunResponse:
    provider = resolve_provider(request.provider)
    model_name = config.get_litellm_model(provider, request.model)
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    thread_id = request.thread_id or run_id
    steps: list[AgentStep] = []
    outputs: dict[str, str] = {}

    for agent in AGENTS:
        step = AgentStep(
            id=agent.id,
            name=agent.name,
            role=agent.role,
            status="running",
            input_summary=_input_summary(agent.id, request, outputs),
        )
        started = time.perf_counter()
        try:
            step.output = await llm.generate_from_prompts(
                provider=provider,
                model=request.model,
                system_prompt=agent.system_prompt,
                user_prompt=_build_user_prompt(agent.id, request, outputs),
                temperature=_temperature_for_step(agent.id, request.temperature),
                max_tokens=request.max_tokens,
            )
            step.status = "completed"
            outputs[agent.id] = step.output
        except Exception as exc:  # noqa: BLE001 - converted into an API-level pipeline error.
            step.status = "failed"
            step.error = str(exc)
            step.duration_ms = _elapsed_ms(started)
            steps.append(step)
            raise PipelineExecutionError(f"{agent.name} failed: {exc}", steps) from exc
        step.duration_ms = _elapsed_ms(started)
        steps.append(step)

    final_text = outputs["editor"].strip()
    final_content = AgentFinalContent(
        title=_derive_title(final_text, request.topic),
        content=final_text,
        content_type=request.content_type.value,
        style=request.style.value,
        tags=request.keywords or [],
    )
    saved_content_id = None
    if request.save_final:
        generated = GeneratedContent(
            title=final_content.title,
            content=final_content.content,
            tags=final_content.tags,
            content_type=request.content_type,
            metadata={
                "agent_run_id": run_id,
                "review": outputs.get("review", ""),
                "keywords": request.keywords or [],
            },
        )
        saved_content_id = store.save_content(
            generated,
            llm_provider=provider,
            model_name=model_name,
            style=request.style.value,
            keywords=request.keywords,
        )
        store.update_content(saved_content_id, status="agent_final")

    return AgentRunResponse(
        run_id=run_id,
        thread_id=thread_id,
        steps=steps,
        final_content=final_content,
        saved_content_id=saved_content_id,
        provider=provider,
        model=model_name,
    )


def _base_context(request: AgentRunRequest) -> str:
    keywords = ", ".join(request.keywords or []) or "none"
    return (
        f"Topic: {request.topic}\n"
        f"Platform/content type: {request.content_type.value}\n"
        f"Style: {request.style.value}\n"
        f"Length: {request.length}\n"
        f"Keywords: {keywords}"
    )


def _build_user_prompt(step_id: str, request: AgentRunRequest, outputs: dict[str, str]) -> str:
    context = _base_context(request)
    if step_id == "strategy":
        return f"{context}\n\nCreate the content strategy."
    if step_id == "writer":
        return f"{context}\n\nStrategy:\n{outputs['strategy']}\n\nWrite the first complete draft."
    if step_id == "editor":
        return (
            f"{context}\n\nStrategy:\n{outputs['strategy']}\n\nDraft:\n{outputs['writer']}\n\n"
            "Produce the final polished content."
        )
    if step_id == "review":
        return (
            f"{context}\n\nFinal content:\n{outputs['editor']}\n\n"
            "Review the final content."
        )
    raise ValueError(f"Unknown agent step: {step_id}")


def _input_summary(step_id: str, request: AgentRunRequest, outputs: dict[str, str]) -> str:
    if step_id == "strategy":
        return f"Topic '{request.topic}' for {request.content_type.value}."
    if step_id == "writer":
        return "Uses the strategy output to create a first draft."
    if step_id == "editor":
        return "Uses the strategy and draft to create the final content."
    if step_id == "review":
        return "Reviews the final edited content."
    return "Runs an agent step."


def _temperature_for_step(step_id: str, base_temperature: float) -> float:
    if step_id == "review":
        return min(base_temperature, 0.4)
    if step_id == "writer":
        return min(max(base_temperature, 0.7), 1.0)
    return base_temperature


def _derive_title(content: str, topic: str) -> str:
    for line in content.splitlines():
        title = line.strip().strip("#：: -")
        if title:
            return title[:80]
    return topic[:80]


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
