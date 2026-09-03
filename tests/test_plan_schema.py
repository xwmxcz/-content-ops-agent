"""Tests for planner structured output, bounded repair, and plan invariants (P1-05).

Most tests here are pure-unit and need no database: the planner contract is about
turning untrusted text into a plan, which is entirely in-process. Only the
end-to-end pipeline assertions use the `store` fixture.
"""
from __future__ import annotations

import json
import logging
import random

import pytest

from src.api.schemas.agent import PipelinePlanStep
from src.api.services.dynamic_pipeline import DynamicPipeline
from src.api.services.plan_schema import (
    INVARIANT_BACKWARD_EDGES,
    INVARIANT_CONTIGUOUS_INDICES,
    INVARIANT_FINAL_AGENT,
    INVARIANT_PAYLOAD_SHAPE,
    INVARIANT_SCHEMA,
    INVARIANT_STEP_COUNT,
    MAX_STEPS,
    REPAIR_PASS_NAMES,
    PlannerPlanDraft,
    assert_completed_steps_preserved,
    check_plan_invariants,
    coerce_plan_payload,
    has_research_step,
    parse_planner_output,
    plan_response_schema,
    strip_fence,
)
from src.llm.litellm_client import LLMConfigurationError
from src.utils import config
from src.utils.config import Config


# ---------- helpers -----------------------------------------------------------


def _step(index: int, agent_id: str, inputs_from=None, **overrides) -> PipelinePlanStep:
    payload = {
        "index": index,
        "agent_id": agent_id,
        "description": f"{agent_id} step",
        "instruction": "",
        "inputs_from": list(inputs_from or []),
    }
    payload.update(overrides)
    return PipelinePlanStep(**payload)


def _raw(*steps: dict) -> str:
    return json.dumps(list(steps))


def _entry(index: int, agent_id: str, inputs_from=None, **extra) -> dict:
    payload = {
        "index": index,
        "agent_id": agent_id,
        "description": f"{agent_id} desc",
        "instruction": "",
        "inputs_from": list(inputs_from or []),
    }
    payload.update(extra)
    return payload


class _PlannerLLM:
    """Records calls and replays queued responses."""

    def __init__(self, *responses: str, accepts_response_format: bool = True):
        self.calls: list[dict] = []
        self.responses = list(responses)
        self.accepts_response_format = accepts_response_format

    async def generate_from_prompts(self, **kwargs):
        if kwargs.get("response_format") and not self.accepts_response_format:
            raise RuntimeError("response_format is not supported by this gateway")
        self.calls.append(kwargs)
        return self.responses.pop(0) if self.responses else "null"


def _pipeline(llm) -> DynamicPipeline:
    # store/runner are unused by the planner-only seams under test.
    return DynamicPipeline(store=None, llm=llm, runner=object())


# ---------- strict schema validation ------------------------------------------


def test_well_formed_plan_parses_strictly_without_repair():
    outcome = parse_planner_output(
        _raw(_entry(1, "researcher"), _entry(2, "writer", [1]))
    )

    assert outcome.mode == "strict"
    assert outcome.repair_attempts == 0
    assert outcome.applied_passes == ()
    assert outcome.violations == ()
    assert [s.agent_id for s in outcome.steps] == ["researcher", "writer"]


def test_parsed_steps_always_start_pending_with_no_output():
    outcome = parse_planner_output(_raw(_entry(1, "writer")))

    assert [s.status for s in outcome.steps] == ["pending"]
    assert [s.output for s in outcome.steps] == [""]


def test_planner_cannot_inject_a_precompleted_step():
    """`extra="forbid"` is a safety boundary, not tidiness.

    A planner that returns `status: completed` with prefabricated `output` would
    otherwise have a step treated as already-run, skipping the real agent and
    feeding model-authored text downstream as if an agent had produced it.
    """
    raw = _raw(_entry(1, "writer", status="completed", output="injected text"))

    outcome = parse_planner_output(raw)

    assert outcome.mode != "strict"  # rejected by the draft model, then salvaged
    assert [(s.status, s.output) for s in outcome.steps] == [("pending", "")]


def test_sibling_keys_beside_the_steps_array_are_ignored():
    """Models in JSON mode often add a reasoning field next to the plan.

    Only `steps`/`plan` is read and everything else is discarded, so a sibling key
    smuggles nothing and must not cost a repair pass. The injection boundary that
    matters is per-step, covered by the precompleted-step test above.
    """
    payload = json.dumps(
        {"steps": [_entry(1, "writer")], "reasoning": "I thought about it"}
    )

    outcome = parse_planner_output(payload)

    assert outcome.mode == "strict"
    assert [s.agent_id for s in outcome.steps] == ["writer"]


def test_draft_model_rejects_blank_description():
    with pytest.raises(Exception):
        PlannerPlanDraft(steps=[{"index": 1, "agent_id": "writer", "description": ""}])


# ---------- structured output / envelope --------------------------------------

def test_structured_output_envelope_is_unwrapped_strictly():
    """Providers in JSON-object mode cannot emit a top-level array.

    The same plan therefore arrives wrapped as `{"steps": [...]}`, and that must
    still count as a clean parse rather than paying a repair pass.
    """
    payload = json.dumps({"steps": [_entry(1, "researcher"), _entry(2, "editor", [1])]})

    outcome = parse_planner_output(payload, source="structured_output")

    assert outcome.mode == "strict"
    assert outcome.source == "structured_output"
    assert [s.agent_id for s in outcome.steps] == ["researcher", "editor"]


def test_plan_alias_envelope_is_also_accepted():
    payload = json.dumps({"plan": [_entry(1, "writer")]})

    assert parse_planner_output(payload).mode == "strict"


def test_response_schema_is_serialisable_and_names_the_plan():
    schema = plan_response_schema()

    assert schema["name"] == "pipeline_plan"
    json.dumps(schema)  # must survive being put on the wire


# ---------- repair passes -----------------------------------------------------

def test_prose_wrapped_json_is_recovered_by_extraction():
    raw = "Sure! Here is the plan you asked for:\n" + _raw(
        _entry(1, "researcher"), _entry(2, "writer", [1])
    )

    outcome = parse_planner_output(raw)

    assert outcome.mode == "repaired"
    assert outcome.applied_passes == ("extract_json",)
    assert outcome.repair_attempts == 1


def test_markdown_fence_is_stripped_without_counting_as_repair():
    raw = "```json\n" + _raw(_entry(1, "writer")) + "\n```"

    outcome = parse_planner_output(raw)

    assert outcome.mode == "strict"
    assert outcome.repair_attempts == 0


def test_extraction_handles_braces_inside_descriptions():
    """Brace counting must be string-aware.

    A depth counter that ignores quoting would mis-balance on a `}` inside prose
    and truncate the array mid-step.
    """
    raw = "Here you go: " + _raw(
        _entry(1, "writer", description="Use the {placeholder} token")
    )

    outcome = parse_planner_output(raw)

    assert outcome.steps
    assert "{placeholder}" in outcome.steps[0].description


def test_string_indices_and_invented_agents_are_coerced_away():
    raw = _raw(
        _entry(1, "strategy"),
        _entry(2, "not_a_real_agent", [1]),
        {"index": "3", "agent_id": "writer", "description": "W", "inputs_from": [1, 2]},
    )

    outcome = parse_planner_output(raw)

    assert outcome.mode == "repaired"
    assert "coerce_steps" in outcome.applied_passes
    assert [s.agent_id for s in outcome.steps] == ["strategy", "writer"]
    assert [s.index for s in outcome.steps] == [1, 2]


def test_duplicate_indices_are_deduped_and_renumbered():
    raw = _raw(_entry(1, "strategy"), _entry(1, "researcher"), _entry(2, "writer", [1]))

    outcome = parse_planner_output(raw)

    assert [s.index for s in outcome.steps] == list(range(1, len(outcome.steps) + 1))
    assert check_plan_invariants(outcome.steps) == ()


def test_plan_ending_on_reviewer_gains_a_writer_so_the_run_ships_something():
    raw = _raw(_entry(1, "writer"), _entry(2, "reviewer", [1]))

    outcome = parse_planner_output(raw)

    assert outcome.mode == "repaired"
    assert "enforce_structure" in outcome.applied_passes
    assert outcome.steps[-1].agent_id in ("writer", "editor")


def test_full_plan_ending_on_reviewer_is_trimmed_when_there_is_no_room():
    """At MAX_STEPS there is no room to append, so trailing commentary is dropped.

    Appending anyway would breach the step ceiling that bounds run cost.
    """
    entries = [_entry(i, "writer" if i == 1 else "reviewer", [1]) for i in range(1, MAX_STEPS + 1)]

    outcome = parse_planner_output(json.dumps(entries))

    assert outcome.steps
    assert len(outcome.steps) <= MAX_STEPS
    assert outcome.steps[-1].agent_id in ("writer", "editor")


def test_forward_edges_are_dropped_by_coercion():
    raw = _raw(_entry(1, "writer", inputs_from=[2]), _entry(2, "editor", [1]))

    outcome = parse_planner_output(raw)

    assert outcome.steps
    assert check_plan_invariants(outcome.steps) == ()
    assert outcome.steps[0].inputs_from == []


def test_oversized_plan_is_capped_at_max_steps():
    entries = [_entry(i, "writer") for i in range(1, MAX_STEPS + 5)]

    outcome = parse_planner_output(json.dumps(entries))

    assert len(outcome.steps) <= MAX_STEPS


# ---------- repair boundary ---------------------------------------------------

def test_unusable_output_falls_back_without_exhausting_passes():
    outcome = parse_planner_output("I'll just wing it, no JSON for you")

    assert outcome.mode == "fallback"
    assert outcome.steps == []
    assert outcome.violations == (INVARIANT_PAYLOAD_SHAPE,)


def test_zero_repair_budget_disables_all_repair():
    raw = _raw(_entry(1, "writer"), _entry(2, "reviewer", [1]))

    outcome = parse_planner_output(raw, max_repair_attempts=0)

    assert outcome.mode == "fallback"
    assert outcome.repair_attempts == 0
    assert outcome.applied_passes == ()


def test_repair_attempts_never_exceed_the_configured_budget():
    """The bound is what stops a persistently malformed planner from spinning."""
    nasty_inputs = [
        "",
        "null",
        "not json at all",
        "{}",
        "[]",
        json.dumps({"steps": []}),
        json.dumps([{"agent_id": "writer"}]),
        json.dumps([_entry(1, "reviewer")]),
        "prose then [" + json.dumps(_entry(1, "bogus")) + "]",
    ]

    for raw in nasty_inputs:
        outcome = parse_planner_output(raw, max_repair_attempts=2)
        assert outcome.repair_attempts <= 2, raw
        assert len(outcome.applied_passes) <= 2, raw


def test_default_budget_matches_the_implemented_pass_count():
    assert config.PLANNER_MAX_REPAIR_ATTEMPTS == len(REPAIR_PASS_NAMES)


def test_empty_payload_is_not_rescued_into_a_lone_writer():
    """Synthesising a plan from nothing loses research and strategy.

    The caller's canonical default plan is strictly better than a one-step guess,
    so an empty array must reach fallback rather than being "repaired".
    """
    outcome = parse_planner_output("[]")

    assert outcome.mode == "fallback"
    assert outcome.steps == []


# ---------- invariants --------------------------------------------------------

def test_valid_plan_satisfies_every_invariant():
    steps = [_step(1, "researcher"), _step(2, "writer", [1]), _step(3, "editor", [2])]

    assert check_plan_invariants(steps) == ()


def test_empty_plan_violates_step_count():
    assert check_plan_invariants([]) == (INVARIANT_STEP_COUNT,)


def test_non_contiguous_indices_are_reported():
    steps = [_step(1, "researcher"), _step(3, "writer", [1])]

    assert INVARIANT_CONTIGUOUS_INDICES in check_plan_invariants(steps)


def test_forward_edge_violates_backward_edges_invariant():
    steps = [_step(1, "writer", [2]), _step(2, "editor", [1])]

    assert INVARIANT_BACKWARD_EDGES in check_plan_invariants(steps)


def test_self_referencing_edge_violates_backward_edges_invariant():
    steps = [_step(1, "writer", [1])]

    assert INVARIANT_BACKWARD_EDGES in check_plan_invariants(steps)


def test_plan_not_ending_in_writer_or_editor_is_reported():
    steps = [_step(1, "writer"), _step(2, "reviewer", [1])]

    assert INVARIANT_FINAL_AGENT in check_plan_invariants(steps)


def test_oversized_plan_violates_step_count():
    steps = [_step(i, "writer") for i in range(1, MAX_STEPS + 2)]

    assert INVARIANT_STEP_COUNT in check_plan_invariants(steps)


def test_backward_edges_invariant_makes_cycles_unrepresentable():
    """Indices fixed at 1..N plus strictly-backward edges is the DAG guarantee.

    Any edge that could close a cycle points forward, so it is already a
    violation; no separate cycle search is needed.
    """
    cyclic = [_step(1, "writer", [2]), _step(2, "editor", [1])]

    assert INVARIANT_BACKWARD_EDGES in check_plan_invariants(cyclic)


def test_research_presence_is_recorded_not_enforced():
    """A research-free plan is legitimate for topics with no claims.

    The prompt delegates that judgement to the planner, so the parser reports the
    fact and still accepts the plan.
    """
    outcome = parse_planner_output(_raw(_entry(1, "strategy"), _entry(2, "writer", [1])))

    assert outcome.mode == "strict"
    assert outcome.has_research_step is False
    assert has_research_step(outcome.steps) is False


def test_research_presence_detects_fact_checker_too():
    steps = [_step(1, "writer"), _step(2, "fact_checker", [1]), _step(3, "editor", [2])]

    assert has_research_step(steps) is True


# ---------- completed-step immutability (safety) ------------------------------

def test_revision_preserving_completed_steps_is_accepted():
    current = [_step(1, "writer", status="completed", output="draft"), _step(2, "reviewer", [1])]
    revised = [_step(1, "writer"), _step(2, "editor", [1])]

    assert assert_completed_steps_preserved(current, revised) == ()


def test_revision_removing_a_completed_step_is_rejected():
    current = [_step(1, "writer", status="completed", output="draft"), _step(2, "reviewer", [1])]
    revised = [_step(1, "editor")]

    violations = assert_completed_steps_preserved(current, revised)

    assert any(v.startswith("completed_step_agent_changed") for v in violations)


def test_revision_renaming_a_completed_agent_is_rejected():
    """Relabelling completed work is the corruption this guard exists for.

    Index 2's recorded output came from the writer; calling it the editor makes
    every downstream `inputs_from: [2]` consumer read mislabelled text.
    """
    current = [
        _step(1, "researcher", status="completed", output="findings"),
        _step(2, "writer", [1], status="completed", output="draft"),
    ]
    revised = [_step(1, "researcher"), _step(2, "editor", [1])]

    violations = assert_completed_steps_preserved(current, revised)

    assert violations == ("completed_step_agent_changed:2",)


def test_revision_rewiring_a_completed_step_is_rejected():
    current = [
        _step(1, "researcher", status="completed", output="findings"),
        _step(2, "writer", [1], status="completed", output="draft"),
    ]
    revised = [_step(1, "researcher"), _step(2, "writer", [])]

    assert assert_completed_steps_preserved(current, revised) == (
        "completed_step_inputs_changed:2",
    )


def test_dropping_a_completed_step_entirely_is_rejected():
    current = [
        _step(1, "researcher", status="completed", output="findings"),
        _step(2, "writer", [1], status="completed", output="draft"),
    ]
    revised = [_step(1, "researcher")]

    assert assert_completed_steps_preserved(current, revised) == (
        "completed_step_removed:2",
    )


def test_pending_steps_may_be_reordered_and_replaced_freely():
    current = [
        _step(1, "writer", status="completed", output="draft"),
        _step(2, "reviewer", [1]),
        _step(3, "editor", [2]),
    ]
    revised = [_step(1, "writer"), _step(2, "fact_checker", [1]), _step(3, "editor", [1, 2])]

    assert assert_completed_steps_preserved(current, revised) == ()


async def test_pipeline_rejects_a_revision_that_relabels_completed_work(caplog):
    current = [
        _step(1, "researcher", status="completed", output="findings"),
        _step(2, "writer", [1], status="completed", output="draft"),
    ]
    hostile = _raw(_entry(1, "researcher"), _entry(2, "editor", [1]))
    pipeline = _pipeline(_PlannerLLM(hostile))

    from src.api.schemas.agent import PipelineRunRequest
    from src.models import ContentStyle, ContentType

    request = PipelineRunRequest(
        topic="t", content_type=ContentType.BLOG, style=ContentStyle.PROFESSIONAL
    )

    with caplog.at_level(logging.WARNING):
        revised = await pipeline._maybe_revise_plan(
            current, {1: "findings", 2: "draft"}, request, "siliconflow", None
        )

    assert revised is None, "a revision that relabels completed work must be discarded"
    assert any(getattr(r, "event", "") == "planner_revision_rejected" for r in caplog.records)


async def test_pipeline_carries_completed_outputs_into_an_accepted_revision():
    current = [
        _step(1, "writer", status="completed", output="draft", prompt_tokens=7),
        _step(2, "reviewer", [1]),
    ]
    accepted = _raw(_entry(1, "writer"), _entry(2, "reviewer", [1]), _entry(3, "editor", [1, 2]))
    pipeline = _pipeline(_PlannerLLM(accepted))

    from src.api.schemas.agent import PipelineRunRequest
    from src.models import ContentStyle, ContentType

    request = PipelineRunRequest(
        topic="t", content_type=ContentType.BLOG, style=ContentStyle.PROFESSIONAL
    )

    revised = await pipeline._maybe_revise_plan(
        current, {1: "draft"}, request, "siliconflow", None
    )

    assert revised is not None
    assert revised[0].status == "completed"
    assert revised[0].output == "draft"
    assert revised[0].prompt_tokens == 7
    assert revised[-1].agent_id == "editor"


async def test_revision_declining_with_null_leaves_the_plan_untouched():
    pipeline = _pipeline(_PlannerLLM("null"))

    from src.api.schemas.agent import PipelineRunRequest
    from src.models import ContentStyle, ContentType

    request = PipelineRunRequest(
        topic="t", content_type=ContentType.BLOG, style=ContentStyle.PROFESSIONAL
    )

    assert await pipeline._maybe_revise_plan(
        [_step(1, "writer")], {}, request, "siliconflow", None
    ) is None


async def test_revision_path_never_requests_json_object_mode():
    """`null` means "no revision needed" and JSON-object mode forbids it.

    Asking for json_object here would push the planner into inventing a revision
    rather than declining one.
    """
    llm = _PlannerLLM("null")
    pipeline = _pipeline(llm)

    from src.api.schemas.agent import PipelineRunRequest
    from src.models import ContentStyle, ContentType

    request = PipelineRunRequest(
        topic="t", content_type=ContentType.BLOG, style=ContentStyle.PROFESSIONAL
    )
    await pipeline._maybe_revise_plan([_step(1, "writer")], {}, request, "siliconflow", None)

    assert llm.calls
    assert all(call.get("response_format") is None for call in llm.calls)


# ---------- provider conformance ---------------------------------------------

@pytest.mark.parametrize(
    "provider,expected",
    [
        ("siliconflow", {"type": "json_object"}),
        ("deepseek", {"type": "json_object"}),
        ("moonshot", {"type": "json_object"}),
        ("newapi", {"type": "json_object"}),
        ("claude", None),
    ],
)
def test_response_format_is_offered_only_where_the_provider_accepts_it(provider, expected):
    assert config.planner_response_format(provider) == expected


def test_response_format_can_be_disabled_globally(monkeypatch):
    # Patches the class, not the `config` instance: the helper is a classmethod and
    # reads `cls.`, so an instance attribute would be shadowed and ignored.
    monkeypatch.setattr(Config, "PLANNER_STRUCTURED_OUTPUT_ENABLED", False)

    assert config.planner_response_format("siliconflow") is None


async def test_capable_provider_uses_structured_output_in_one_call():
    llm = _PlannerLLM(_raw(_entry(1, "writer")))
    pipeline = _pipeline(llm)

    raw, source = await pipeline._call_planner(
        provider="siliconflow", model=None, system_prompt="s", user_prompt="u"
    )

    assert source == "structured_output"
    assert len(llm.calls) == 1
    assert llm.calls[0]["response_format"] == {"type": "json_object"}


async def test_claude_stays_on_the_text_path_without_response_format():
    llm = _PlannerLLM(_raw(_entry(1, "writer")))
    pipeline = _pipeline(llm)

    raw, source = await pipeline._call_planner(
        provider="claude", model=None, system_prompt="s", user_prompt="u"
    )

    assert source == "text_json"
    assert llm.calls[0].get("response_format") is None


async def test_provider_rejecting_response_format_is_retried_as_plain_text(caplog):
    """A gateway can advertise JSON mode and still reject the parameter.

    Failing the run there would break those deployments, so the downgrade is
    retried and counted rather than raised.
    """
    llm = _PlannerLLM(_raw(_entry(1, "writer")), accepts_response_format=False)
    pipeline = _pipeline(llm)

    with caplog.at_level(logging.WARNING):
        raw, source = await pipeline._call_planner(
            provider="siliconflow", model=None, system_prompt="s", user_prompt="u"
        )

    assert source == "text_json"
    assert raw
    assert any(
        getattr(r, "event", "") == "planner_structured_output_unsupported"
        for r in caplog.records
    )


async def test_client_without_response_format_support_still_works():
    """An injected client predating the parameter must not break."""

    class LegacyClient:
        def __init__(self):
            self.calls = []

        async def generate_from_prompts(
            self, provider, model, system_prompt, user_prompt, temperature=0.7, max_tokens=2048
        ):
            self.calls.append(provider)
            return _raw(_entry(1, "writer"))

    llm = LegacyClient()
    raw, source = await _pipeline(llm)._call_planner(
        provider="siliconflow", model=None, system_prompt="s", user_prompt="u"
    )

    assert source == "text_json"
    assert len(llm.calls) == 1


async def test_missing_credentials_are_not_swallowed_by_the_text_retry():
    """A configuration error fails the same way without JSON mode.

    Retrying would double the latency before surfacing the same failure.
    """

    class Unconfigured:
        async def generate_from_prompts(self, **kwargs):
            raise LLMConfigurationError("Missing API key for provider: siliconflow")

    with pytest.raises(LLMConfigurationError):
        await _pipeline(Unconfigured())._call_planner(
            provider="siliconflow", model=None, system_prompt="s", user_prompt="u"
        )


# ---------- observability -----------------------------------------------------

def test_outcome_log_fields_carry_no_planner_text():
    """Log fields must stay free of prompts and model prose."""
    outcome = parse_planner_output(
        "Here is the plan: " + _raw(_entry(1, "researcher"), _entry(2, "writer", [1]))
    )
    fields = outcome.as_log_fields()

    assert fields["plan_mode"] == "repaired"
    assert fields["step_count"] == 2
    assert fields["has_research_step"] is True
    serialised = json.dumps(fields)
    assert "Here is the plan" not in serialised


def test_repaired_plan_is_logged_as_accepted_with_pass_names(caplog):
    pipeline = _pipeline(_PlannerLLM())
    outcome = parse_planner_output("prose " + _raw(_entry(1, "researcher"), _entry(2, "writer", [1])))

    with caplog.at_level(logging.INFO):
        pipeline._record_plan_outcome(outcome, run_id="run_1", provider="deepseek", model="m")

    record = next(r for r in caplog.records if getattr(r, "event", "") == "planner_plan_accepted")
    assert record.plan_mode == "repaired"
    assert "extract_json" in record.applied_passes


def test_fallback_outcome_is_logged_with_violations(caplog):
    pipeline = _pipeline(_PlannerLLM())
    outcome = parse_planner_output("total garbage")

    with caplog.at_level(logging.WARNING):
        pipeline._record_plan_outcome(outcome, run_id="run_2", provider="deepseek", model="m")

    record = next(r for r in caplog.records if getattr(r, "event", "") == "planner_fallback")
    assert record.reason == "invalid_plan"
    assert INVARIANT_PAYLOAD_SHAPE in record.violations


def test_research_free_plan_is_flagged_for_prompt_drift(caplog):
    pipeline = _pipeline(_PlannerLLM())
    outcome = parse_planner_output(_raw(_entry(1, "strategy"), _entry(2, "writer", [1])))

    with caplog.at_level(logging.WARNING):
        pipeline._record_plan_outcome(outcome, run_id="run_3", provider="deepseek", model="m")

    assert any(
        getattr(r, "event", "") == "planner_plan_without_research" for r in caplog.records
    )


def test_plan_with_research_is_not_flagged(caplog):
    pipeline = _pipeline(_PlannerLLM())
    outcome = parse_planner_output(_raw(_entry(1, "researcher"), _entry(2, "writer", [1])))

    with caplog.at_level(logging.WARNING):
        pipeline._record_plan_outcome(outcome, run_id="run_4", provider="deepseek", model="m")

    assert not any(
        getattr(r, "event", "") == "planner_plan_without_research" for r in caplog.records
    )


# ---------- property / fuzz ---------------------------------------------------

def _fuzz_payloads(seed: int, count: int) -> list[str]:
    rng = random.Random(seed)
    agents = ["researcher", "writer", "editor", "reviewer", "strategy", "fact_checker", "bogus", ""]
    payloads: list[str] = []
    for _ in range(count):
        entries = []
        for _ in range(rng.randint(0, MAX_STEPS + 3)):
            entry: dict = {}
            if rng.random() < 0.85:
                entry["index"] = rng.choice([rng.randint(-2, MAX_STEPS + 3), str(rng.randint(1, 5)), None])
            if rng.random() < 0.9:
                entry["agent_id"] = rng.choice(agents)
            if rng.random() < 0.8:
                entry["description"] = rng.choice(["desc", "", "  ", "with {brace}"])
            if rng.random() < 0.5:
                entry["inputs_from"] = rng.choice(
                    [[], [1], [rng.randint(-1, 9)], ["2"], [True], [None], "notalist"]
                )
            entries.append(entry)
        raw = json.dumps(entries)
        style = rng.random()
        if style < 0.2:
            raw = f"```json\n{raw}\n```"
        elif style < 0.4:
            raw = f"Here is the plan:\n{raw}\nHope that helps!"
        elif style < 0.5:
            raw = json.dumps({"steps": entries})
        elif style < 0.55:
            raw = raw[: max(1, len(raw) // 2)]  # truncated JSON
        payloads.append(raw)
    return payloads


def test_fuzzed_planner_output_never_raises_and_never_yields_an_invalid_plan():
    """The core property: any text in, an actionable outcome out.

    A returned plan must satisfy every invariant, and anything unusable must be a
    fallback with no steps. Both branches keep the run safe; a partially valid
    plan reaching the executor would not.
    """
    for raw in _fuzz_payloads(seed=1337, count=400):
        outcome = parse_planner_output(raw)

        assert outcome.mode in ("strict", "repaired", "fallback")
        assert outcome.repair_attempts <= config.PLANNER_MAX_REPAIR_ATTEMPTS
        if outcome.steps:
            assert check_plan_invariants(outcome.steps) == (), raw
            assert len(outcome.steps) <= MAX_STEPS
            assert [s.index for s in outcome.steps] == list(range(1, len(outcome.steps) + 1))
            assert all(s.status == "pending" for s in outcome.steps)
            assert outcome.steps[-1].agent_id in ("writer", "editor")
        else:
            assert outcome.mode == "fallback"


def test_fuzzed_coercion_never_raises():
    for raw in _fuzz_payloads(seed=99, count=200):
        try:
            payload = json.loads(strip_fence(raw))
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(payload, list):
            continue
        steps = coerce_plan_payload(payload)
        if steps:
            assert all(s.index >= 1 for s in steps)


def test_valid_plans_round_trip_through_parsing_unchanged():
    """Property: a plan the parser accepts strictly survives re-serialisation."""
    plans = [
        [_entry(1, "writer")],
        [_entry(1, "researcher"), _entry(2, "writer", [1])],
        [_entry(1, "researcher"), _entry(2, "strategy", [1]), _entry(3, "editor", [1, 2])],
    ]
    for entries in plans:
        first = parse_planner_output(json.dumps(entries))
        assert first.mode == "strict"

        again = parse_planner_output(
            json.dumps(
                [
                    {
                        "index": s.index,
                        "agent_id": s.agent_id,
                        "description": s.description,
                        "instruction": s.instruction,
                        "inputs_from": s.inputs_from,
                    }
                    for s in first.steps
                ]
            )
        )
        assert again.mode == "strict"
        assert [s.model_dump() for s in again.steps] == [s.model_dump() for s in first.steps]


# ---------- end-to-end --------------------------------------------------------

async def test_run_uses_a_structured_output_plan_end_to_end(store):
    from tests.test_dynamic_pipeline import FakeRunner, _request

    plan = json.dumps({"steps": [_entry(1, "strategy"), _entry(2, "writer", [1])]})
    llm = _PlannerLLM(plan, "null")
    runner = FakeRunner(store=store, scripted={"strategy": "S", "writer": "W"})
    pipeline = DynamicPipeline(store=store, llm=llm, runner=runner)

    response = await pipeline.run(_request())

    assert [s.agent_id for s in response.plan] == ["strategy", "writer"]
    assert response.final_content.content == "W"
    assert llm.calls[0]["response_format"] == {"type": "json_object"}


async def test_run_falls_back_to_the_default_plan_when_output_is_unusable(store):
    from tests.test_dynamic_pipeline import FakeRunner, _request

    llm = _PlannerLLM("no json here", "null")
    runner = FakeRunner(
        store=store,
        scripted={"researcher": "R", "strategy": "S", "writer": "W", "fact_checker": "F", "editor": "E"},
    )
    pipeline = DynamicPipeline(store=store, llm=llm, runner=runner)

    response = await pipeline.run(_request())

    assert [s.agent_id for s in response.plan] == [
        "researcher", "strategy", "writer", "fact_checker", "editor",
    ]
    assert all(s.status == "completed" for s in response.plan)


async def test_run_surfaces_configuration_errors_instead_of_falling_back(store):
    """A run against an unusable provider must not silently execute a default plan."""
    from tests.test_dynamic_pipeline import FakeRunner, _request

    class Unconfigured:
        async def generate_from_prompts(self, **kwargs):
            raise LLMConfigurationError("Missing API key for provider: siliconflow")

    pipeline = DynamicPipeline(
        store=store, llm=Unconfigured(), runner=FakeRunner(store=store)
    )

    with pytest.raises(LLMConfigurationError):
        await pipeline.run(_request())
