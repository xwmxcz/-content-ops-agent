"""Planner plan schema, bounded repair, and invariants (P1-05).

The planner is an LLM, so its output is untrusted text. Three things go wrong,
in increasing severity:

1. **Wrapping noise** — a markdown fence, a prose preamble, or a
   ``{"steps": [...]}`` envelope instead of a bare array. Cosmetic, and
   recoverable by extracting the JSON block.
2. **Shape drift** — a step is missing ``description``, ``index`` arrives as
   ``"2"``, an ``agent_id`` is invented, or two steps claim the same index.
   Recoverable by coercion plus dropping what cannot be salvaged.
3. **Invariant violation** — the final step is a reviewer (so the run produces
   no shippable draft), or ``inputs_from`` points forward at output that does
   not exist yet. Coercion alone does not fix these; they need a structural
   repair or the plan must be discarded.

Repair is therefore **staged, not retried**. Each pass is strictly more invasive
than the last, and the number of passes actually applied is capped by
``config.PLANNER_MAX_REPAIR_ATTEMPTS`` so a persistently malformed response
cannot spin. Re-prompting the model was rejected: a planner that emitted
unparseable output once will usually do it again, and every extra round trip is
paid latency on the critical path. The canonical default plan is valid by
construction, so falling back is always cheaper than another attempt.

``assert_completed_steps_preserved`` is the one check here guarding a *safety*
property rather than a shape property. A revision that renames the agent at an
index whose step already completed would attach one agent's output to another
agent's identity, and every later step reading ``inputs_from`` would silently
consume mislabelled text. Such a revision is **rejected outright, never
repaired** — the run continues on the plan that is already known-good.

The research requirement is *recorded*, not enforced. The planner prompt makes
researcher steps conditional ("unless the topic is genuinely a personal essay
with zero claims"), so a research-free plan can be legitimate. Forcing a
researcher step here would override a decision the prompt delegates to the
planner, so this module reports whether research is present and leaves the
judgement to the caller.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.api.schemas.agent import PipelinePlanStep, SubAgentId
from src.utils import config


# Hard structural bounds. MAX_STEPS also caps how much work one run can schedule,
# so it is a cost ceiling as much as a schema bound.
MAX_STEPS = 8
MAX_REVISIONS = 2

# A run only ships something if the last step produces prose. reviewer/researcher
# /fact_checker all emit commentary about a draft rather than a draft.
FINAL_STEP_AGENTS: tuple[str, ...] = ("writer", "editor")
RESEARCH_AGENTS: tuple[str, ...] = ("researcher", "fact_checker")

VALID_AGENT_IDS: frozenset[str] = frozenset(get_args(SubAgentId))

PLANNER_SCHEMA_NAME = "pipeline_plan"

ParseSource = Literal["structured_output", "text_json"]
ParseMode = Literal["strict", "repaired", "fallback"]

# Invariant identifiers. These are metric label values and log fields, so they are
# named constants rather than inline strings — a typo in a label silently creates a
# second time series instead of failing.
INVARIANT_PAYLOAD_SHAPE = "payload_shape"
INVARIANT_SCHEMA = "schema_validation"
INVARIANT_STEP_COUNT = "step_count_within_bounds"
INVARIANT_CONTIGUOUS_INDICES = "contiguous_indices"
INVARIANT_KNOWN_AGENTS = "known_agent_ids"
INVARIANT_BACKWARD_EDGES = "backward_edges_only"
INVARIANT_FINAL_AGENT = "final_step_is_writer_or_editor"

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.DOTALL)


class PlannerStepDraft(BaseModel):
    """One planner-emitted step: shape and types only.

    Deliberately excludes every runtime field on ``PipelinePlanStep`` (``status``,
    ``output``, token counts, ``tool_events``). ``extra="forbid"`` is what makes
    that exclusion meaningful: a planner that tries to hand us ``"status":
    "completed"`` or ``"output": "..."`` is rejected rather than silently trusted,
    so model text can never inject an already-finished step into a fresh plan.

    Semantic rules (contiguity, edge direction, final agent) live in
    ``check_plan_invariants`` instead of here, so that every violation is reported
    through one uniform channel.
    """

    model_config = ConfigDict(extra="forbid")

    index: int = Field(..., ge=1)
    agent_id: SubAgentId
    description: str = Field(..., min_length=1)
    instruction: str = ""
    inputs_from: list[int] = Field(default_factory=list)


class PlannerPlanDraft(BaseModel):
    """A whole planner-emitted plan, before semantic invariants are applied."""

    model_config = ConfigDict(extra="forbid")

    steps: list[PlannerStepDraft] = Field(..., min_length=1)


@dataclass(frozen=True)
class PlanParseOutcome:
    """What happened while turning planner text into a plan.

    ``steps`` is empty exactly when ``mode == "fallback"``; the caller is then
    responsible for substituting the default plan. ``violations`` carries the
    invariant identifiers still unsatisfied at the point the attempt was
    abandoned, which is the field worth alerting on.
    """

    steps: list[PipelinePlanStep]
    source: ParseSource
    mode: ParseMode
    repair_attempts: int
    violations: tuple[str, ...] = ()
    applied_passes: tuple[str, ...] = ()
    has_research_step: bool = False

    def as_log_fields(self) -> dict[str, Any]:
        return {
            "plan_source": self.source,
            "plan_mode": self.mode,
            "repair_attempts": self.repair_attempts,
            "applied_passes": list(self.applied_passes),
            "violations": list(self.violations),
            "step_count": len(self.steps),
            "has_research_step": self.has_research_step,
        }


def plan_response_schema() -> dict[str, Any]:
    """JSON Schema envelope for providers that accept a named response schema.

    Kept separate from the wire-level ``response_format`` chosen in
    ``config.planner_response_format`` because not every gateway that advertises
    JSON mode also accepts a schema; this is the payload for the ones that do.
    """
    return {
        "name": PLANNER_SCHEMA_NAME,
        "schema": PlannerPlanDraft.model_json_schema(),
        "strict": False,
    }


def check_plan_invariants(steps: list[PipelinePlanStep]) -> tuple[str, ...]:
    """Return the invariant identifiers ``steps`` violates; empty means valid.

    Order is deliberate: cheap structural facts first, so a plan that is empty or
    oversized is reported without walking every edge.
    """
    if not steps:
        return (INVARIANT_STEP_COUNT,)

    violations: list[str] = []

    if len(steps) > MAX_STEPS:
        violations.append(INVARIANT_STEP_COUNT)

    if [step.index for step in steps] != list(range(1, len(steps) + 1)):
        violations.append(INVARIANT_CONTIGUOUS_INDICES)

    if any(step.agent_id not in VALID_AGENT_IDS for step in steps):
        violations.append(INVARIANT_KNOWN_AGENTS)

    # Edges must point strictly backwards. That single rule is what makes the plan
    # a DAG: with indices fixed at 1..N and every edge going to a lower index, a
    # cycle is unrepresentable, so no separate cycle search is needed.
    for step in steps:
        if any(
            not isinstance(ref, int) or isinstance(ref, bool) or ref < 1 or ref >= step.index
            for ref in step.inputs_from
        ):
            violations.append(INVARIANT_BACKWARD_EDGES)
            break

    if steps[-1].agent_id not in FINAL_STEP_AGENTS:
        violations.append(INVARIANT_FINAL_AGENT)

    return tuple(dict.fromkeys(violations))


def has_research_step(steps: list[PipelinePlanStep]) -> bool:
    return any(step.agent_id in RESEARCH_AGENTS for step in steps)


def assert_completed_steps_preserved(
    current_plan: list[PipelinePlanStep],
    revised_steps: list[PipelinePlanStep],
) -> tuple[str, ...]:
    """Return violations if ``revised_steps`` disturbs an already-completed step.

    A completed step's identity is ``(index, agent_id, inputs_from)``. The output
    text is already recorded and cannot change, but the *label* on it can: if a
    revision turns index 2 from ``writer`` into ``editor``, the writer's draft
    keeps flowing downstream wearing the editor's name, and every consumer of
    ``inputs_from: [2]`` is silently misled about what it is reading.

    Non-empty result means the revision must be discarded whole. Partial
    acceptance is not offered on purpose: re-numbering half a plan around a
    rejected step is how index/edge corruption gets introduced.
    """
    violations: list[str] = []
    revised_by_index = {step.index: step for step in revised_steps}

    for step in current_plan:
        if step.status != "completed":
            continue
        candidate = revised_by_index.get(step.index)
        if candidate is None:
            violations.append(f"completed_step_removed:{step.index}")
            continue
        if candidate.agent_id != step.agent_id:
            violations.append(f"completed_step_agent_changed:{step.index}")
        if list(candidate.inputs_from) != list(step.inputs_from):
            violations.append(f"completed_step_inputs_changed:{step.index}")

    return tuple(violations)


def strip_fence(text: str) -> str:
    return _FENCE_RE.sub("", (text or "").strip()).strip()


def coerce_plan_payload(payload: list[Any]) -> list[PipelinePlanStep]:
    """Best-effort salvage of a raw step list into a valid plan.

    Public because it is the lenient counterpart to strict validation and is used
    directly by the revision path, where a partially malformed plan is still worth
    salvaging. Applies the coercion and structural repair passes in order and
    returns whatever survives — possibly an empty list.
    """
    coerced = _repair_coerce_steps("", payload)
    if coerced is None:
        return []
    structured = _repair_enforce_structure("", coerced)
    if structured is not None:
        coerced = structured
    steps, _ = _build_steps(coerced)
    return steps


def parse_planner_output(
    raw: str,
    *,
    source: ParseSource = "text_json",
    max_repair_attempts: int | None = None,
) -> PlanParseOutcome:
    """Turn planner text into a plan, repairing within a fixed pass budget.

    Never raises: the planner sits on the run's critical path, so every failure
    mode has to resolve to an outcome the caller can act on. An unusable response
    returns ``mode="fallback"`` with empty ``steps``.
    """
    cap = config.PLANNER_MAX_REPAIR_ATTEMPTS if max_repair_attempts is None else max_repair_attempts
    cap = max(0, cap)

    payload: Any = None
    try:
        payload = json.loads(strip_fence(raw))
    except (json.JSONDecodeError, TypeError):
        payload = None

    violations: tuple[str, ...] = (INVARIANT_PAYLOAD_SHAPE,)
    if payload is not None:
        steps, violations = _validate_payload(payload)
        if steps and not violations:
            return PlanParseOutcome(
                steps=steps,
                source=source,
                mode="strict",
                repair_attempts=0,
                has_research_step=has_research_step(steps),
            )

    attempts = 0
    applied: list[str] = []
    for pass_name, repair in _REPAIR_PASSES:
        if attempts >= cap:
            break
        try:
            repaired = repair(raw, payload)
        except Exception:
            # A repair pass exists to rescue malformed input; letting it raise would
            # turn a recoverable planner glitch into a failed run.
            repaired = None
        if repaired is None:
            continue
        attempts += 1
        applied.append(pass_name)
        payload = repaired
        steps, violations = _validate_payload(payload)
        if steps and not violations:
            return PlanParseOutcome(
                steps=steps,
                source=source,
                mode="repaired",
                repair_attempts=attempts,
                applied_passes=tuple(applied),
                has_research_step=has_research_step(steps),
            )

    return PlanParseOutcome(
        steps=[],
        source=source,
        mode="fallback",
        repair_attempts=attempts,
        violations=violations,
        applied_passes=tuple(applied),
    )


# -- internals ---------------------------------------------------------------


def _unwrap_envelope(payload: Any) -> Any:
    """Accept both a bare array and an object wrapper.

    Providers in JSON-object mode cannot return a top-level array, so the same
    plan legitimately arrives as ``{"steps": [...]}`` there and as ``[...]`` on
    the text path. ``"plan"`` is accepted too because the prompt uses that word.
    """
    if isinstance(payload, dict):
        for key in ("steps", "plan"):
            nested = payload.get(key)
            if isinstance(nested, list):
                return nested
    return payload


def _validate_payload(payload: Any) -> tuple[list[PipelinePlanStep], tuple[str, ...]]:
    steps_payload = _unwrap_envelope(payload)
    if not isinstance(steps_payload, list):
        return [], (INVARIANT_PAYLOAD_SHAPE,)
    try:
        draft = PlannerPlanDraft(steps=steps_payload)
    except ValidationError:
        return [], (INVARIANT_SCHEMA,)
    steps = _drafts_to_runtime(draft.steps)
    return steps, check_plan_invariants(steps)


def _drafts_to_runtime(drafts: list[PlannerStepDraft]) -> list[PipelinePlanStep]:
    # Sorted by index so a correctly numbered but out-of-order plan still counts as
    # strict; contiguity is then checked on the sorted sequence.
    ordered = sorted(drafts, key=lambda draft: draft.index)
    return [
        PipelinePlanStep(
            index=draft.index,
            agent_id=draft.agent_id,
            description=draft.description,
            instruction=draft.instruction,
            inputs_from=sorted(set(draft.inputs_from)),
            status="pending",
        )
        for draft in ordered
    ]


def _build_steps(payload: list[dict[str, Any]]) -> tuple[list[PipelinePlanStep], tuple[str, ...]]:
    steps: list[PipelinePlanStep] = []
    for entry in payload:
        try:
            steps.append(
                PipelinePlanStep(
                    index=entry["index"],
                    agent_id=entry["agent_id"],
                    description=entry["description"],
                    instruction=entry.get("instruction", ""),
                    inputs_from=list(entry.get("inputs_from") or []),
                    status="pending",
                )
            )
        except Exception:
            continue
    return steps, check_plan_invariants(steps)


def _extract_json_block(text: str) -> str | None:
    """Return the first balanced JSON array/object in ``text``.

    Brace counting rather than a regex: a non-greedy pattern stops at the first
    inner ``}``, which truncates every nested step object. String-aware so a brace
    inside a description does not shift the depth count.
    """
    if not text:
        return None
    start = min(
        (pos for pos in (text.find("["), text.find("{")) if pos != -1),
        default=-1,
    )
    if start == -1:
        return None

    opener = text[start]
    closer = "]" if opener == "[" else "}"
    depth = 0
    in_string = False
    escaped = False

    for offset, char in enumerate(text[start:], start=start):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return text[start : offset + 1]
    return None


def _repair_extract_json(raw: str, payload: Any) -> Any | None:
    """Pass 1 — pull a JSON block out of prose. No-op once JSON already parsed."""
    if payload is not None:
        return None
    block = _extract_json_block(strip_fence(raw))
    if block is None:
        return None
    try:
        return json.loads(block)
    except json.JSONDecodeError:
        return None


def _repair_coerce_steps(raw: str, payload: Any) -> list[dict[str, Any]] | None:
    """Pass 2 — cast types, drop unsalvageable steps, renumber, remap edges.

    Renumbering happens after dropping, and edges are remapped through the
    old→new index map, so a surviving step keeps pointing at the same *step* it
    originally depended on rather than at whatever now occupies that number.
    """
    steps_payload = _unwrap_envelope(payload)
    if not isinstance(steps_payload, list):
        return None

    coerced: list[dict[str, Any]] = []
    seen_indices: set[int] = set()

    for entry in steps_payload[:MAX_STEPS]:
        if not isinstance(entry, dict):
            continue
        agent_id = entry.get("agent_id")
        if agent_id not in VALID_AGENT_IDS:
            continue
        try:
            index = int(entry.get("index") or len(coerced) + 1)
        except (TypeError, ValueError):
            continue
        if index in seen_indices:
            continue
        refs = [
            int(ref)
            for ref in (entry.get("inputs_from") or [])
            if (isinstance(ref, int) and not isinstance(ref, bool))
            or (isinstance(ref, str) and ref.isdigit())
        ]
        description = str(entry.get("description") or "").strip() or f"{agent_id} step"
        instruction = str(entry.get("instruction") or "").strip()
        coerced.append(
            {
                "index": index,
                "agent_id": agent_id,
                "description": description,
                "instruction": instruction,
                "inputs_from": [ref for ref in refs if ref < index],
            }
        )
        seen_indices.add(index)

    if not coerced:
        return None

    coerced.sort(key=lambda entry: entry["index"])
    old_to_new = {entry["index"]: new for new, entry in enumerate(coerced, start=1)}
    for entry in coerced:
        new_index = old_to_new[entry["index"]]
        entry["inputs_from"] = sorted(
            {
                old_to_new[ref]
                for ref in entry["inputs_from"]
                if ref in old_to_new and old_to_new[ref] < new_index
            }
        )
        entry["index"] = new_index
    return coerced


def _repair_enforce_structure(raw: str, payload: Any) -> list[dict[str, Any]] | None:
    """Pass 3 — append a writer when the plan would not produce a draft.

    Returns ``None`` for an empty payload rather than fabricating a lone writer
    step: a plan synthesised from nothing has no research and no strategy, and the
    caller's default plan is a strictly better answer than a one-step guess.
    """
    steps_payload = _unwrap_envelope(payload)
    if not isinstance(steps_payload, list) or not steps_payload:
        return None
    if not all(isinstance(entry, dict) for entry in steps_payload):
        return None
    if steps_payload[-1].get("agent_id") in FINAL_STEP_AGENTS:
        return None
    if len(steps_payload) >= MAX_STEPS:
        # No room to append; drop trailing non-final steps instead so the plan still
        # ends on a draft rather than silently exceeding the step ceiling.
        trimmed = list(steps_payload)
        while trimmed and trimmed[-1].get("agent_id") not in FINAL_STEP_AGENTS:
            trimmed.pop()
        return trimmed or None

    appended = list(steps_payload)
    last_index = appended[-1].get("index") or len(appended)
    appended.append(
        {
            "index": int(last_index) + 1,
            "agent_id": "writer",
            "description": "Compose the final draft using prior outputs.",
            "instruction": "Write the final draft based on the strategy and any reviewer notes above.",
            "inputs_from": [
                int(entry["index"]) for entry in steps_payload if isinstance(entry.get("index"), int)
            ],
        }
    )
    return appended


# Order matters: extraction only helps when nothing parsed, coercion only helps
# once a list exists, and structural repair only helps once steps are numbered.
# len(_REPAIR_PASSES) is the natural value for PLANNER_MAX_REPAIR_ATTEMPTS.
_REPAIR_PASSES: tuple[tuple[str, Any], ...] = (
    ("extract_json", _repair_extract_json),
    ("coerce_steps", _repair_coerce_steps),
    ("enforce_structure", _repair_enforce_structure),
)

REPAIR_PASS_NAMES: tuple[str, ...] = tuple(name for name, _ in _REPAIR_PASSES)
