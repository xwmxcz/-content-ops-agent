"""Dynamic Plan-then-Execute pipeline for the Studio surface.

The flow:
  1. Planner LLM proposes a JSON plan: 3-6 steps drawing from 6 sub-agent types.
  2. Each step is executed via SubAgentRunner. Outputs are kept in `outputs[index]`.
  3. After a reviewer step or any failed step, the planner is given another chance
     to revise the remaining (pending) steps. Up to MAX_REVISIONS revisions allowed.
  4. Every state transition (plan_ready / step_start / step_token / step_complete /
     step_failed / plan_revised / run_complete / run_failed) is appended to the
     `agent_run_events` table — that table also serves as the SSE bus.

Hard guards:
  - MAX_STEPS = 8
  - MAX_REVISIONS = 2
  - Schema validation: agent_id whitelist, inputs_from < own index, dedupe step indices
  - On any planner failure (bad JSON / empty / shape error) → fall back to the
    canonical 4-step strategy/writer/editor/reviewer plan
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from typing import Any

from src.api.schemas.agent import (
    AgentFinalContent,
    PipelinePlanStep,
    PipelineRunRequest,
    PipelineRunResponse,
    SubAgentId,
    SubAgentToolEvent,
)
from src.api.services.content_service import resolve_provider
from src.api.services.sub_agents import (
    PRICE_PER_1K,
    SUB_AGENTS,
    SubAgentRunner,
    SubAgentSpec,
    estimate_cost,
)
from src.llm.litellm_client import LiteLLMClient, LLMConfigurationError
from src.models import GeneratedContent
from src.storage import ContentStore
from src.utils import config


MAX_STEPS = 8
MAX_REVISIONS = 2

PLANNER_SYSTEM_PROMPT = (
    "You are the Pipeline Planner for a RESEARCH-ORIENTED content pipeline. "
    "This pipeline is the user's choice when the topic needs evidence — comparisons, "
    "claims with numbers/dates/named entities, or recent events. The user has already "
    "decided that researcher / fact_checker steps are wanted; do not skip them unless "
    "the topic is genuinely a personal essay with zero claims.\n\n"
    "You have 6 sub-agents to choose from:\n"
    "- researcher: gathers context via tools (search_history, web_search, view_content)\n"
    "- fact_checker: verifies concrete claims via tools (search_history, web_search)\n"
    "- strategy: plans audience, angle, structure (no tools)\n"
    "- writer: produces a complete first draft (no tools)\n"
    "- editor: polishes a draft for clarity, rhythm, platform fit (no tools)\n"
    "- reviewer: scores 1-100 and lists strengths/risks (no tools)\n\n"
    "Output a JSON plan: an array of steps. Each step is:\n"
    '{"index": 1, "agent_id": "strategy", "description": "...", '
    '"instruction": "...", "inputs_from": []}\n\n'
    "Rules:\n"
    "- 4 to 7 steps total\n"
    "- ALWAYS include at least one researcher step EARLY (index 1 or 2) unless the topic\n"
    "  is purely personal/emotional with no facts to gather\n"
    "- If the topic mentions specific numbers, dates, products, or comparisons, ALSO\n"
    "  include a fact_checker step BEFORE the writer\n"
    "- The available_tools field on the request indicates which tools are enabled —\n"
    "  if web_search is disabled, lean on search_history alone\n"
    "- Final step must be writer or editor (so we have content to ship)\n"
    "- inputs_from references earlier step indices; the agent will see those outputs\n"
    "- Output JSON ONLY. No prose. No markdown fence."
)

REVISION_SYSTEM_PROMPT = (
    "A pipeline run is in progress. Decide whether the remaining plan should be revised.\n\n"
    "Return one of:\n"
    "1. JSON `null` if the latest result is acceptable and the plan should continue as-is.\n"
    "2. A JSON array containing FULL revised plan (same schema as the original plan): "
    "you may add up to 2 new steps, reorder PENDING steps, but you must NOT modify or "
    "remove COMPLETED steps. Step indices stay 1-based and contiguous.\n\n"
    "Output JSON only. No prose."
)


class PipelineExecutionError(RuntimeError):
    pass


class DynamicPipeline:
    def __init__(
        self,
        store: ContentStore,
        llm: LiteLLMClient | None = None,
        runner: SubAgentRunner | None = None,
        emit_async: bool = False,
    ):
        self.store = store
        self.llm = llm or LiteLLMClient()
        self.runner = runner or SubAgentRunner(store=store, llm=self.llm)
        # When False (test mode) we await DB writes inline so events are visible immediately.
        self.emit_async = emit_async

    async def run(self, request: PipelineRunRequest, run_id: str | None = None) -> PipelineRunResponse:
        provider = resolve_provider(request.provider)
        litellm_model = config.get_litellm_model(provider, request.model)
        run_id = run_id or f"run_{uuid.uuid4().hex[:12]}"
        thread_id = request.thread_id or run_id

        if not self.store.get_run(run_id):
            self.store.create_run(
                run_id=run_id,
                topic=request.topic,
                content_type=request.content_type.value,
                style=request.style.value,
                provider=provider,
                model=litellm_model,
                thread_id=thread_id,
            )

        try:
            plan = await self._make_plan(request, provider, request.model)
        except Exception as exc:
            import sys
            print(f"[planner] fallback to default plan: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            plan = self._default_plan()
        if not plan:
            import sys
            print("[planner] empty plan returned → fallback to default", file=sys.stderr, flush=True)
            plan = self._default_plan()
        await self._emit(run_id, "plan_ready", {"plan": [s.model_dump() for s in plan]})

        outputs: dict[int, str] = {}
        revisions = 0
        i = 0
        total_prompt = 0
        total_completion = 0
        total_cost = 0.0

        cancelled = False

        while i < len(plan) and i < MAX_STEPS:
            step = plan[i]
            if step.status != "pending":
                i += 1
                continue

            # Cancellation is requested via DELETE /api/agent/runs/{id}, which flips the
            # row status to "cancelled" and writes a run_cancelled event. We poll the row
            # at step boundaries — running sub-agents are allowed to finish, but no new
            # step starts. Avoiding inline cancellation keeps streaming/tool calls safe.
            current = self.store.get_run(run_id)
            if current and current.get("status") == "cancelled":
                cancelled = True
                break

            step.status = "running"
            await self._emit(run_id, "step_start", {
                "index": step.index, "agent_id": step.agent_id, "description": step.description,
            })

            spec = SUB_AGENTS.get(step.agent_id)
            user_prompt = self._build_step_prompt(step, plan, outputs, request)
            started = time.perf_counter()
            success = True
            step_tool_events: list[dict[str, Any]] = []
            try:
                if spec is None:
                    raise ValueError(f"Unknown agent_id: {step.agent_id}")

                async def token_sink(delta: str, _idx=step.index):
                    await self._emit(run_id, "step_token", {"index": _idx, "delta": delta})

                async def tool_sink(event_type: str, payload: dict[str, Any], _idx=step.index, _events=step_tool_events):
                    enriched = {"index": _idx, **payload}
                    if event_type == "tool_call_result":
                        _events.append({
                            "name": payload.get("name", ""),
                            "args": payload.get("args") or {},
                            "status": payload.get("status", "completed"),
                            "preview": payload.get("preview", ""),
                            "error": payload.get("error"),
                            "duration_ms": payload.get("duration_ms", 0),
                        })
                    await self._emit(run_id, event_type, enriched)

                text, p_tok, c_tok, _, _ = await self.runner.run(
                    spec=spec,
                    user_prompt=user_prompt,
                    provider=provider,
                    model=request.model or config.get_model(provider),
                    max_tokens=request.max_tokens,
                    token_sink=token_sink,
                    tool_sink=tool_sink,
                )
                duration = int((time.perf_counter() - started) * 1000)
                cost = estimate_cost(litellm_model, p_tok, c_tok)

                step.output = text
                step.status = "completed"
                step.duration_ms = duration
                step.prompt_tokens = p_tok
                step.completion_tokens = c_tok
                step.cost_estimate = cost
                step.tool_events = [SubAgentToolEvent(**e) for e in step_tool_events]
                outputs[step.index] = text
                total_prompt += p_tok
                total_completion += c_tok
                total_cost += cost

                await self._emit(run_id, "step_complete", {
                    "index": step.index,
                    "agent_id": step.agent_id,
                    "output": text,
                    "duration_ms": duration,
                    "prompt_tokens": p_tok,
                    "completion_tokens": c_tok,
                    "cost_estimate": cost,
                    "tool_events": step_tool_events,
                })
            except LLMConfigurationError:
                raise
            except Exception as exc:
                success = False
                duration = int((time.perf_counter() - started) * 1000)
                step.status = "failed"
                step.duration_ms = duration
                await self._emit(run_id, "step_failed", {
                    "index": step.index,
                    "agent_id": step.agent_id,
                    "error": str(exc) or exc.__class__.__name__,
                })

            should_revise = revisions < MAX_REVISIONS and (
                step.agent_id == "reviewer" or not success
            )
            if should_revise:
                try:
                    revised = await self._maybe_revise_plan(plan, outputs, request, provider, request.model)
                except Exception:
                    revised = None
                if revised is not None:
                    plan = revised
                    revisions += 1
                    await self._emit(run_id, "plan_revised", {
                        "plan": [s.model_dump() for s in plan],
                        "revision": revisions,
                    })
                    i = next(
                        (idx for idx, s in enumerate(plan) if s.status == "pending"),
                        len(plan),
                    )
                    continue
            i += 1

        if cancelled:
            self.store.update_run(
                run_id,
                plan=[s.model_dump() for s in plan],
                revision_count=revisions,
                total_prompt_tokens=total_prompt,
                total_completion_tokens=total_completion,
                total_cost=total_cost,
                status="cancelled",
            )
            # The DELETE endpoint already emitted run_cancelled, so we do NOT emit
            # again here — duplicate terminal events would only confuse SSE clients.
            return PipelineRunResponse(
                run_id=run_id,
                thread_id=thread_id,
                plan=plan,
                final_content=AgentFinalContent(
                    title=request.topic[:80],
                    content="",
                    content_type=request.content_type.value,
                    style=request.style.value,
                    tags=request.keywords or [],
                ),
                saved_content_id=None,
                provider=provider,
                model=litellm_model,
                total_prompt_tokens=total_prompt,
                total_completion_tokens=total_completion,
                total_cost=total_cost,
                revision_count=revisions,
                status="cancelled",
            )

        final_text = self._select_final_output(plan, outputs) or request.topic

        saved_content_id = None
        if request.save_final and final_text.strip():
            generated = GeneratedContent(
                title=self._derive_title(final_text, request.topic),
                content=final_text,
                tags=request.keywords or [],
                content_type=request.content_type,
                metadata={"pipeline_run_id": run_id},
            )
            saved_content_id = self.store.save_content(
                generated,
                llm_provider=provider,
                model_name=litellm_model,
                style=request.style.value,
                keywords=request.keywords,
                token_usage=total_prompt + total_completion,
                cost_estimate=total_cost,
            )
            self.store.update_content(saved_content_id, status="agent_final")

        self.store.update_run(
            run_id,
            plan=[s.model_dump() for s in plan],
            revision_count=revisions,
            total_prompt_tokens=total_prompt,
            total_completion_tokens=total_completion,
            total_cost=total_cost,
            saved_content_id=saved_content_id,
            status="completed",
        )

        final = AgentFinalContent(
            title=self._derive_title(final_text, request.topic),
            content=final_text,
            content_type=request.content_type.value,
            style=request.style.value,
            tags=request.keywords or [],
        )
        response = PipelineRunResponse(
            run_id=run_id,
            thread_id=thread_id,
            plan=plan,
            final_content=final,
            saved_content_id=saved_content_id,
            provider=provider,
            model=litellm_model,
            total_prompt_tokens=total_prompt,
            total_completion_tokens=total_completion,
            total_cost=total_cost,
            revision_count=revisions,
            status="completed",
        )
        await self._emit(run_id, "run_complete", response.model_dump())
        return response

    # -- planner ------------------------------------------------------------

    async def _make_plan(
        self,
        request: PipelineRunRequest,
        provider: str,
        model: str | None,
    ) -> list[PipelinePlanStep]:
        keywords = ", ".join(request.keywords or []) or "none"
        available_tools: list[str] = ["search_history", "view_content", "list_recent_contents"]
        if request.use_web_search:
            available_tools.append("web_search")
        if not request.use_history_search:
            available_tools = [t for t in available_tools if t != "search_history"]
        focus = request.research_focus.strip() if request.research_focus else "(not specified)"
        user_prompt = (
            f"Topic: {request.topic}\n"
            f"Platform/content type: {request.content_type.value}\n"
            f"Style: {request.style.value}\n"
            f"Length: {request.length}\n"
            f"Keywords: {keywords}\n"
            f"Research focus hint: {focus}\n"
            f"Available tools to researcher/fact_checker: {', '.join(available_tools) or '(none)'}\n\n"
            "Output the plan now."
        )
        raw = await self.llm.generate_from_prompts(
            provider=provider,
            model=model,
            system_prompt=PLANNER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=1024,
        )
        return self._parse_plan(raw)

    async def _maybe_revise_plan(
        self,
        plan: list[PipelinePlanStep],
        outputs: dict[int, str],
        request: PipelineRunRequest,
        provider: str,
        model: str | None,
    ) -> list[PipelinePlanStep] | None:
        summary = json.dumps(
            [
                {
                    "index": s.index,
                    "agent_id": s.agent_id,
                    "status": s.status,
                    "description": s.description,
                    "output": (s.output[:200] + "…") if len(s.output) > 200 else s.output,
                }
                for s in plan
            ],
            ensure_ascii=False,
        )
        user_prompt = (
            f"Original topic: {request.topic}\n\nCurrent plan and outputs:\n{summary}\n\n"
            "Decide whether to revise. Return null or full revised plan as JSON."
        )
        raw = await self.llm.generate_from_prompts(
            provider=provider,
            model=model,
            system_prompt=REVISION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=1024,
        )
        cleaned = self._strip_fence(raw)
        if not cleaned or cleaned.lower() == "null":
            return None
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            return None
        if payload is None:
            return None
        if not isinstance(payload, list):
            return None
        revised = self._coerce_plan(payload)
        if not revised:
            return None
        # Preserve completed step outputs by id (best-effort: copy by index match)
        completed_by_index = {s.index: s for s in plan if s.status == "completed"}
        for new_step in revised:
            if new_step.index in completed_by_index:
                old = completed_by_index[new_step.index]
                new_step.status = old.status
                new_step.output = old.output
                new_step.duration_ms = old.duration_ms
                new_step.prompt_tokens = old.prompt_tokens
                new_step.completion_tokens = old.completion_tokens
                new_step.cost_estimate = old.cost_estimate
        return revised

    def _parse_plan(self, raw: str) -> list[PipelinePlanStep]:
        cleaned = self._strip_fence(raw)
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            import sys
            print(f"[planner] JSON parse failed: {exc}; raw[:200]={cleaned[:200]!r}", file=sys.stderr, flush=True)
            return []
        if not isinstance(payload, list):
            import sys
            print(f"[planner] payload not a list, got {type(payload).__name__}: {str(payload)[:200]!r}", file=sys.stderr, flush=True)
            return []
        return self._coerce_plan(payload)

    @staticmethod
    def _strip_fence(text: str) -> str:
        text = (text or "").strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL)
        return text.strip()

    @staticmethod
    def _coerce_plan(payload: list[Any]) -> list[PipelinePlanStep]:
        steps: list[PipelinePlanStep] = []
        seen_indices: set[int] = set()
        valid_ids = set(SUB_AGENTS.keys())
        for raw_step in payload[:MAX_STEPS]:
            if not isinstance(raw_step, dict):
                continue
            agent_id = raw_step.get("agent_id")
            if agent_id not in valid_ids:
                continue
            try:
                idx = int(raw_step.get("index") or len(steps) + 1)
            except (TypeError, ValueError):
                continue
            if idx in seen_indices:
                continue
            inputs_from = [
                int(x) for x in (raw_step.get("inputs_from") or []) if isinstance(x, (int, str)) and str(x).isdigit()
            ]
            inputs_from = [x for x in inputs_from if x < idx]
            description = str(raw_step.get("description") or "").strip() or f"{agent_id} step"
            instruction = str(raw_step.get("instruction") or "").strip()
            try:
                steps.append(PipelinePlanStep(
                    index=idx,
                    agent_id=agent_id,  # type: ignore[arg-type]
                    description=description,
                    instruction=instruction,
                    inputs_from=inputs_from,
                    status="pending",
                ))
                seen_indices.add(idx)
            except Exception:
                continue
        steps.sort(key=lambda s: s.index)
        # Renumber to 1..N after dropping invalid or duplicate planner steps.
        # Keep dependency edges attached to the same surviving original steps.
        old_to_new = {step.index: new_idx for new_idx, step in enumerate(steps, start=1)}
        for step in steps:
            old_index = step.index
            new_index = old_to_new[old_index]
            step.index = new_index
            remapped_inputs = {
                old_to_new[source]
                for source in step.inputs_from
                if source in old_to_new and old_to_new[source] < new_index
            }
            step.inputs_from = sorted(remapped_inputs)
        # Trim if last step is not writer/editor
        if steps and steps[-1].agent_id not in ("writer", "editor"):
            steps = steps + [PipelinePlanStep(
                index=steps[-1].index + 1,
                agent_id="writer",
                description="Compose the final draft using prior outputs.",
                instruction="Write the final draft based on the strategy and any reviewer notes above.",
                inputs_from=[s.index for s in steps],
            )]
        return steps[:MAX_STEPS]

    @staticmethod
    def _default_plan() -> list[PipelinePlanStep]:
        # Dynamic pipeline is positioned as the RESEARCH-oriented track. The default
        # fallback plan should reflect that: the user picked dynamic precisely because
        # they expect researcher / fact_checker to be involved.
        return [
            PipelinePlanStep(index=1, agent_id="researcher",
                             description="Gather context from saved content and the public web",
                             instruction="Research the topic. Use search_history first, then web_search if it adds external context. Summarize findings as 5-8 bullet points.",
                             inputs_from=[]),
            PipelinePlanStep(index=2, agent_id="strategy",
                             description="Plan audience, angle, and structure grounded in research",
                             instruction="Use the researcher's findings to design the strategy.",
                             inputs_from=[1]),
            PipelinePlanStep(index=3, agent_id="writer",
                             description="Write the first draft",
                             instruction="Use the strategy and research findings. Cite sources where the researcher provided URLs.",
                             inputs_from=[1, 2]),
            PipelinePlanStep(index=4, agent_id="fact_checker",
                             description="Verify factual claims in the draft",
                             instruction="Identify concrete claims (numbers, dates, names). Verify each via search_history or web_search. Flag anything unverified.",
                             inputs_from=[3]),
            PipelinePlanStep(index=5, agent_id="editor",
                             description="Polish the draft and incorporate fact-check findings",
                             instruction="Polish for clarity and platform fit. If the fact_checker flagged unverified claims, soften or remove them.",
                             inputs_from=[3, 4]),
        ]

    # -- step prompt builder ----------------------------------------------

    @staticmethod
    def _build_step_prompt(
        step: PipelinePlanStep,
        plan: list[PipelinePlanStep],
        outputs: dict[int, str],
        request: PipelineRunRequest,
    ) -> str:
        keywords = ", ".join(request.keywords or []) or "none"
        ctx = (
            f"Topic: {request.topic}\n"
            f"Platform: {request.content_type.value}\n"
            f"Style: {request.style.value}\n"
            f"Length: {request.length}\n"
            f"Keywords: {keywords}\n"
        )
        prior_blocks: list[str] = []
        for ref in step.inputs_from:
            if ref in outputs:
                src = next((s for s in plan if s.index == ref), None)
                label = f"{src.agent_id}" if src else f"step {ref}"
                prior_blocks.append(f"--- output of {label} ---\n{outputs[ref]}")
        if prior_blocks:
            ctx += "\n" + "\n\n".join(prior_blocks) + "\n"
        instruction = step.instruction or step.description
        if step.agent_id in ("researcher", "fact_checker"):
            instruction += (
                "\nWhen using web_search, include the topic's specific qualifiers in every query "
                "(location, product/object, platform, audience, scenario, year). If a query is too "
                "generic or returns irrelevant results, retry with the original topic words included."
            )
        return f"{ctx}\n\nYour task: {instruction}\n"

    @staticmethod
    def _select_final_output(plan: list[PipelinePlanStep], outputs: dict[int, str]) -> str:
        # Prefer the latest completed editor output, then writer, then any.
        for agent_id in ("editor", "writer"):
            for step in reversed(plan):
                if step.agent_id == agent_id and step.status == "completed" and step.output:
                    return step.output
        for step in reversed(plan):
            if step.status == "completed" and step.output:
                return step.output
        return ""

    @staticmethod
    def _derive_title(content: str, topic: str) -> str:
        for line in content.splitlines():
            t = line.strip().strip("#*-：:【】 \t")
            if t:
                return t[:80]
        return topic[:80]

    # -- emit -------------------------------------------------------------

    async def _emit(self, run_id: str, event_type: str, payload: dict[str, Any]) -> None:
        # Always inline-write: tests expect events visible immediately after .run() returns.
        # SSE consumers always read from DB so latency is dominated by the polling interval anyway.
        self.store.append_run_event(run_id, event_type, payload)
