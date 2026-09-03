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
  - Schema validation and bounded repair live in `plan_schema`: a Pydantic draft
    model plus staged repair passes, capped by PLANNER_MAX_REPAIR_ATTEMPTS.
  - A revision that would rename, drop, or re-wire an already-COMPLETED step is
    rejected whole rather than repaired — see `assert_completed_steps_preserved`.
  - On any planner failure (bad JSON / empty / invariant violation) → fall back to
    the canonical 5-step researcher/strategy/writer/fact_checker/editor plan
"""
from __future__ import annotations

import asyncio
import json
import logging
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
from src.api.services.plan_schema import (
    MAX_REVISIONS,
    MAX_STEPS,
    PlanParseOutcome,
    assert_completed_steps_preserved,
    coerce_plan_payload,
    parse_planner_output,
    strip_fence,
)
from src.api.services.sub_agents import (
    PRICE_PER_1K,
    SUB_AGENTS,
    SubAgentRunner,
    SubAgentSpec,
    estimate_cost,
)
from src.llm.litellm_client import LiteLLMClient, LLMConfigurationError
from src.storage import ContentStore
from src.utils import config
from src.utils import metrics
from src.utils.structured_logging import log_event


logger = logging.getLogger(__name__)
WORKSPACE_RESEARCH_TOOLS = ("search_history", "view_content", "list_recent_contents")
WEB_RESEARCH_TOOLS = ("web_search",)

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
        self._validate_research_sources(request)
        provider = resolve_provider(request.provider)
        litellm_model = config.get_litellm_model(provider, request.model)
        run_id = run_id or f"run_{uuid.uuid4().hex[:12]}"
        thread_id = request.thread_id or run_id
        research_tools = self._allowed_research_tools(request)

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
            outcome = await self._make_plan(request, provider, request.model)
        except LLMConfigurationError:
            # Misconfigured credentials are the operator's problem, not a planner
            # shape problem. Falling back here would start a full run against a
            # provider that cannot answer, so surface it instead.
            raise
        except Exception as exc:
            log_event(
                logger,
                "planner_fallback",
                level=logging.WARNING,
                run_id=run_id,
                provider=provider,
                model=litellm_model,
                reason="exception",
                error_class=exc.__class__.__name__,
            )
            metrics.planner_plans_parsed_total.labels(
                source="text_json", mode="fallback"
            ).inc()
            plan = self._default_plan(request)
        else:
            self._record_plan_outcome(
                outcome,
                run_id=run_id,
                provider=provider,
                model=litellm_model,
            )
            if outcome.steps:
                plan = outcome.steps
            else:
                plan = self._default_plan(request)
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
            user_prompt = self._build_step_prompt(step, plan, outputs, request, research_tools)
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
                    allowed_tools=research_tools if step.agent_id in ("researcher", "fact_checker") else None,
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

        # Reconcile once more after the final sub-agent returns. Cancellation may
        # arrive while that call is in flight; do not start the final content
        # save when the terminal cancel transition has already won.
        if not cancelled:
            current = self.store.get_run(run_id)
            cancelled = bool(current and current.get("status") == "cancelled")

        if cancelled:
            self.store.update_run(
                run_id,
                plan=[s.model_dump() for s in plan],
                revision_count=revisions,
                total_prompt_tokens=total_prompt,
                total_completion_tokens=total_completion,
                total_cost=total_cost,
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

        content_fields = None
        if request.save_final and final_text.strip():
            content_fields = {
                "title": self._derive_title(final_text, request.topic),
                "content": final_text,
                "content_type": request.content_type.value,
                "style": request.style.value,
                "keywords": json.dumps(request.keywords or [], ensure_ascii=False),
                "tags": json.dumps(request.keywords or [], ensure_ascii=False),
                "status": "agent_final",
                "llm_provider": provider,
                "model_name": litellm_model,
                "token_usage": total_prompt + total_completion,
                "cost_estimate": total_cost,
            }

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
            saved_content_id=None,
            provider=provider,
            model=litellm_model,
            total_prompt_tokens=total_prompt,
            total_completion_tokens=total_completion,
            total_cost=total_cost,
            revision_count=revisions,
            status="completed",
        )
        transitioned = self.store.complete_run_with_content(
            run_id,
            payload=response.model_dump(),
            content_fields=content_fields,
            plan=[s.model_dump() for s in plan],
            revision_count=revisions,
            total_prompt_tokens=total_prompt,
            total_completion_tokens=total_completion,
            total_cost=total_cost,
        )
        if transitioned is None:
            # A cancel/fail transition may win while final content is being
            # prepared. Never report a synthetic completed response when the
            # atomic completion transaction did not commit.
            current = self.store.get_run(run_id)
            current_status = current.get("status") if current else None
            if current_status in {"failed", "cancelled"}:
                response.status = current_status
                response.error = current.get("error")
            else:
                response.status = "failed"
                response.error = "Run completion did not commit"
        else:
            response.saved_content_id = transitioned.get("saved_content_id")
        log_event(
            logger,
            "pipeline_run_finished",
            run_id=run_id,
            thread_id=thread_id,
            provider=provider,
            model=litellm_model,
            status=response.status,
            prompt_tokens=total_prompt,
            completion_tokens=total_completion,
            cost=round(total_cost, 8),
            revision_count=revisions,
        )
        return response

    # -- planner ------------------------------------------------------------

    async def _make_plan(
        self,
        request: PipelineRunRequest,
        provider: str,
        model: str | None,
    ) -> PlanParseOutcome:
        keywords = ", ".join(request.keywords or []) or "none"
        available_tools = list(self._allowed_research_tools(request))
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
        raw, source = await self._call_planner(
            provider=provider,
            model=model,
            system_prompt=PLANNER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        return parse_planner_output(raw, source=source)

    async def _call_planner(
        self,
        *,
        provider: str,
        model: str | None,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[str, str]:
        """Call the planner, preferring provider-native JSON mode.

        Returns the raw text and which path produced it, so the parse outcome can
        be attributed to structured output vs. plain text.

        A provider that advertises JSON mode but rejects the parameter (common on
        self-hosted OpenAI-compatible gateways) must not fail the run: the retry
        without ``response_format`` is what keeps those deployments working, and the
        downgrade is counted so a persistently unsupported provider is visible
        rather than silently paying the extra round trip on every run.
        """
        response_format = config.planner_response_format(provider)
        if response_format:
            try:
                raw = await self.llm.generate_from_prompts(
                    provider=provider,
                    model=model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.3,
                    max_tokens=1024,
                    response_format=response_format,
                )
                return raw, "structured_output"
            except LLMConfigurationError:
                # Missing/invalid credentials fail the same way without JSON mode.
                raise
            except TypeError:
                # An injected client predating response_format support. Retrying
                # without it keeps custom clients and test doubles working.
                pass
            except Exception as exc:
                log_event(
                    logger,
                    "planner_structured_output_unsupported",
                    level=logging.WARNING,
                    provider=provider,
                    error_class=exc.__class__.__name__,
                )
                metrics.planner_structured_output_unsupported_total.labels(
                    provider=provider
                ).inc()

        raw = await self.llm.generate_from_prompts(
            provider=provider,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=1024,
        )
        return raw, "text_json"

    @staticmethod
    def _validate_research_sources(request: PipelineRunRequest) -> None:
        if request.use_web_search or request.use_history_search:
            return
        raise ValueError("At least one research source must be enabled for the dynamic pipeline.")

    @staticmethod
    def _allowed_research_tools(request: PipelineRunRequest) -> tuple[str, ...]:
        tools: list[str] = []
        if request.use_history_search:
            tools.extend(WORKSPACE_RESEARCH_TOOLS)
        if request.use_web_search:
            tools.extend(WEB_RESEARCH_TOOLS)
        return tuple(tools)

    def _record_plan_outcome(
        self,
        outcome: PlanParseOutcome,
        *,
        run_id: str,
        provider: str,
        model: str,
    ) -> None:
        """Emit logs and metrics for one planner parse attempt.

        Every attempt is counted, including the clean ones: a repair rate is only
        interpretable against the total, and `mode="strict"` is the baseline that
        makes a rise in `repaired`/`fallback` legible.
        """
        metrics.planner_plans_parsed_total.labels(
            source=outcome.source, mode=outcome.mode
        ).inc()
        for pass_name in outcome.applied_passes:
            metrics.planner_repair_passes_total.labels(pass_name=pass_name).inc()
        for invariant in outcome.violations:
            metrics.planner_invariant_violations_total.labels(invariant=invariant).inc()

        if outcome.mode == "fallback":
            log_event(
                logger,
                "planner_fallback",
                level=logging.WARNING,
                run_id=run_id,
                provider=provider,
                model=model,
                reason="invalid_plan",
                **outcome.as_log_fields(),
            )
            return

        log_event(
            logger,
            "planner_plan_accepted",
            level=logging.WARNING if outcome.mode == "repaired" else logging.INFO,
            run_id=run_id,
            provider=provider,
            model=model,
            **outcome.as_log_fields(),
        )
        if not outcome.has_research_step:
            # Not an error: the planner prompt allows skipping research for topics
            # with no claims to verify. Recorded because a research-oriented track
            # producing research-free plans in bulk means the prompt has drifted.
            log_event(
                logger,
                "planner_plan_without_research",
                level=logging.WARNING,
                run_id=run_id,
                provider=provider,
                model=model,
                step_count=len(outcome.steps),
            )

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
        # Deliberately not using _call_planner here: "no revision needed" is encoded as
        # JSON `null`, which provider JSON-object mode forbids as a top-level value.
        # Requesting json_object would push the planner into inventing a revision
        # rather than declining one, so the revision path stays on plain text.
        raw = await self.llm.generate_from_prompts(
            provider=provider,
            model=model,
            system_prompt=REVISION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=1024,
        )
        cleaned = strip_fence(raw)
        if not cleaned or cleaned.lower() == "null":
            return None
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            return None
        if payload is None:
            return None
        revised = coerce_plan_payload(payload)
        if not revised:
            return None

        # Safety gate, not a shape check. A revision that renames or drops a step
        # whose output is already recorded would relabel that output, so downstream
        # steps reading inputs_from would consume text from an agent they did not
        # ask for. Reject the whole revision and keep running the known-good plan.
        violations = assert_completed_steps_preserved(plan, revised)
        if violations:
            log_event(
                logger,
                "planner_revision_rejected",
                level=logging.WARNING,
                reason="completed_step_mutated",
                violations=list(violations),
            )
            for violation in violations:
                metrics.planner_revisions_rejected_total.labels(
                    reason=violation.split(":", 1)[0]
                ).inc()
            return None

        # Carry completed results forward. Safe now that identity is confirmed
        # unchanged: index N in the revision is the same step that produced this output.
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
                new_step.tool_events = old.tool_events
        return revised

    @staticmethod
    def _coerce_plan(payload: list[Any]) -> list[PipelinePlanStep]:
        """Lenient salvage of a raw step list. Delegates to `plan_schema`.

        Retained as a method because it is the documented seam for coercion and is
        exercised directly by the plan-coercion tests.
        """
        return coerce_plan_payload(payload)

    def _default_plan(self, request: PipelineRunRequest) -> list[PipelinePlanStep]:
        # Dynamic pipeline is positioned as the RESEARCH-oriented track. The default
        # fallback plan should reflect that: the user picked dynamic precisely because
        # they expect researcher / fact_checker to be involved.
        research_instruction = self._default_research_instruction(request)
        fact_check_instruction = self._default_fact_check_instruction(request)
        return [
            PipelinePlanStep(index=1, agent_id="researcher",
                             description="Gather context from the enabled research sources",
                             instruction=research_instruction,
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
                             instruction=fact_check_instruction,
                             inputs_from=[3]),
            PipelinePlanStep(index=5, agent_id="editor",
                             description="Polish the draft and incorporate fact-check findings",
                             instruction="Polish for clarity and platform fit. If the fact_checker flagged unverified claims, soften or remove them.",
                             inputs_from=[3, 4]),
        ]

    # -- step prompt builder ----------------------------------------------

    def _build_step_prompt(
        self,
        step: PipelinePlanStep,
        plan: list[PipelinePlanStep],
        outputs: dict[int, str],
        request: PipelineRunRequest,
        research_tools: tuple[str, ...],
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
            instruction += self._research_step_suffix(research_tools)
        return f"{ctx}\n\nYour task: {instruction}\n"

    @staticmethod
    def _default_research_instruction(request: PipelineRunRequest) -> str:
        if request.use_history_search and request.use_web_search:
            return (
                "Research the topic. Use search_history first, then web_search if it adds external context. "
                "Summarize findings as 5-8 bullet points."
            )
        if request.use_history_search:
            return (
                "Research the topic using only the internal content library tools "
                "(search_history, view_content, list_recent_contents). Summarize findings as 5-8 bullet points."
            )
        return (
            "Research the topic using only web_search. Summarize findings as 5-8 bullet points."
        )

    @staticmethod
    def _default_fact_check_instruction(request: PipelineRunRequest) -> str:
        if request.use_history_search and request.use_web_search:
            return "Identify concrete claims (numbers, dates, names). Verify each via search_history or web_search. Flag anything unverified."
        if request.use_history_search:
            return "Identify concrete claims (numbers, dates, names). Verify each via the internal content library tools only. Flag anything unverified."
        return "Identify concrete claims (numbers, dates, names). Verify each via web_search only. Flag anything unverified."

    @staticmethod
    def _research_step_suffix(research_tools: tuple[str, ...]) -> str:
        tools_label = ", ".join(research_tools) or "(none)"
        if "web_search" in research_tools and any(tool in research_tools for tool in WORKSPACE_RESEARCH_TOOLS):
            return (
                f"\nAvailable research tools in this run: {tools_label}."
                "\nWhen using web_search, include the topic's specific qualifiers in every query "
                "(location, product/object, platform, audience, scenario, year). If a query is too "
                "generic or returns irrelevant results, retry with the original topic words included."
            )
        if "web_search" in research_tools:
            return (
                f"\nAvailable research tools in this run: {tools_label}."
                "\nDo not call search_history, view_content, or list_recent_contents in this run; "
                "the internal content library is disabled."
                "\nWhen using web_search, include the topic's specific qualifiers in every query "
                "(location, product/object, platform, audience, scenario, year)."
            )
        return (
            f"\nAvailable research tools in this run: {tools_label}."
            "\nDo not call web_search in this run; public web search is disabled. "
            "Rely only on the internal content library tools that are available."
        )

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
