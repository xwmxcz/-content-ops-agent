import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from src.api.schemas.agent import ChatIntent
from src.api.services.chat_agent import AVAILABLE_TOOL_NAMES, ChatAgentService
from src.api.services.tool_policy import (
    SIDE_EFFECT_TOOLS,
    ToolPolicyDenied,
    authorize_tool_call,
    validate_tool_policy_registry,
)
from src.storage.file_memory import FileMemory, USER
from src.utils.canonical import canonical_json


class _OneToolModel:
    def __init__(self, name, args):
        self.name = name
        self.args = args

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        if not any(isinstance(message, ToolMessage) for message in messages):
            return AIMessage(
                content="",
                tool_calls=[{"id": "call_policy", "name": self.name, "args": self.args}],
            )
        return AIMessage(content="done")


def _intent(**overrides):
    server_confirmed = bool(overrides.pop("server_confirmed", False))
    action_id = overrides.pop("action_id", "act_test_capability")
    payload = {
        "name": "content_create",
        "confidence": 0.99,
        "requires_confirmation": False,
        "allowed_tools": ["create_content"],
        "slots": {},
    }
    payload.update(overrides)
    intent = ChatIntent(**payload)
    if server_confirmed:
        if intent.name == "schedule_commit":
            proposal_plan = intent.slots.get("proposal_plan")
            if isinstance(proposal_plan, list) and proposal_plan:
                intent.bind_server_approval(
                    "commit_publishing_schedule",
                    {"plan": proposal_plan},
                    action_id,
                )
        else:
            intent.bind_server_approval(
                intent.slots.get("approved_tool_name", ""),
                intent.slots.get("approved_args", {}),
                action_id,
            )
    return intent


class _CapabilityLedger:
    """In-memory stand-in for the durable one-time capability.

    Mirrors ``ContentStore.consume_proposed_action``: the first exact-matching
    claim wins and every later claim returns ``None``.
    """

    def __init__(self, action_id="act_test_capability", tool_name=None, args=None):
        self.action_id = action_id
        self.tool_name = tool_name
        self.args = args
        self.consumed = []

    def __call__(self, action_id, tool_name, args):
        if action_id != self.action_id or action_id in self.consumed:
            return None
        if self.tool_name is not None and tool_name != self.tool_name:
            return None
        if self.args is not None and canonical_json(args) != canonical_json(self.args):
            return None
        self.consumed.append(action_id)
        return {"id": action_id, "tool_name": tool_name, "status": "consumed"}


def _allow_capability(action_id, tool_name, args):
    """Consumer that always grants, for tests asserting non-capability checks."""
    return {"id": action_id, "tool_name": tool_name, "status": "consumed"}


def test_tool_policy_registry_is_exhaustive_for_chat_surface():
    validate_tool_policy_registry(AVAILABLE_TOOL_NAMES)
    assert SIDE_EFFECT_TOOLS == {
        "create_content",
        "refine_content",
        "add_to_calendar",
        "commit_publishing_schedule",
        "memory_add",
        "memory_replace",
        "memory_remove",
    }


@pytest.mark.parametrize("tool_name", sorted(SIDE_EFFECT_TOOLS))
def test_every_side_effect_fails_closed_without_persisted_exact_approval(tool_name):
    intent = _intent(requires_confirmation=False, allowed_tools=[tool_name])
    with pytest.raises(ToolPolicyDenied):
        authorize_tool_call(tool_name, {}, intent)


@pytest.mark.parametrize("tool_name", sorted(SIDE_EFFECT_TOOLS - {"commit_publishing_schedule"}))
def test_confirmed_side_effect_is_bound_to_exact_tool_and_args(tool_name):
    args = {"target": "user", "text": "approved"}
    intent = _intent(
        name="action_confirm",
        allowed_tools=[tool_name],
        server_confirmed=True,
        slots={
            "approved_tool_name": tool_name,
            "approved_args": args,
        },
    )
    authorize_tool_call(tool_name, args, intent, consume_capability=_allow_capability)
    with pytest.raises(ToolPolicyDenied, match="arguments differ"):
        authorize_tool_call(
            tool_name,
            {**args, "text": "changed"},
            intent,
            consume_capability=_allow_capability,
        )


def test_side_effect_must_match_server_intent_allow_list():
    with pytest.raises(ToolPolicyDenied, match="outside the recognized intent"):
        authorize_tool_call("memory_add", {"target": "user", "text": "x"}, _intent())


def test_exact_proposal_without_server_confirmation_marker_is_denied():
    args = {"target": "user", "text": "not-authorized"}
    intent = _intent(
        name="action_confirm",
        allowed_tools=["memory_add"],
        slots={"approved_tool_name": "memory_add", "approved_args": args},
    )
    with pytest.raises(ToolPolicyDenied, match="server-validated confirmation"):
        authorize_tool_call("memory_add", args, intent)


def test_create_content_cannot_replace_approved_topic_with_model_generated_topic():
    approved = {"topic": "APPROVED A", "content_type": "blog"}
    intent = _intent(
        name="action_confirm",
        allowed_tools=["create_content"],
        server_confirmed=True,
        slots={
            "approved_tool_name": "create_content",
            "approved_args": approved,
        },
    )
    authorize_tool_call("create_content", approved, intent, consume_capability=_allow_capability)
    with pytest.raises(ToolPolicyDenied, match="arguments differ"):
        authorize_tool_call(
            "create_content",
            {"topic": "UNAPPROVED B", "content_type": "blog"},
            intent,
            consume_capability=_allow_capability,
        )


def test_public_slots_cannot_mutate_private_approved_action():
    approved = {"topic": "APPROVED A", "content_type": "blog"}
    changed = {"topic": "UNAPPROVED B", "content_type": "blog"}
    intent = _intent(
        name="action_confirm",
        allowed_tools=["create_content"],
        server_confirmed=True,
        slots={
            "approved_tool_name": "create_content",
            "approved_args": approved,
        },
    )

    # Slots are serialized to the client/history and may be used in prompts, so
    # they must not be the executor's authorization source after recognition.
    intent.slots["approved_args"] = changed
    authorize_tool_call("create_content", approved, intent, consume_capability=_allow_capability)
    with pytest.raises(ToolPolicyDenied, match="arguments differ"):
        authorize_tool_call(
            "create_content",
            changed,
            intent,
            consume_capability=_allow_capability,
        )
    dumped = intent.model_dump()
    assert "_server_approved_args" not in dumped
    assert "_server_approved_tool_name" not in dumped
    assert "_server_approved_action_id" not in dumped


def test_memory_operation_cannot_change_from_approved_add_to_remove():
    approved = {"target": "user", "text": "keep this"}
    intent = _intent(
        name="action_confirm",
        allowed_tools=["memory_add"],
        server_confirmed=True,
        slots={
            "approved_tool_name": "memory_add",
            "approved_args": approved,
        },
    )
    with pytest.raises(ToolPolicyDenied, match="outside the recognized intent"):
        authorize_tool_call("memory_remove", {"target": "user", "old_text": "keep this"}, intent)


def test_schedule_commit_is_bound_to_exact_persisted_proposal():
    plan = [{"content_id": 1, "platform": "xiaohongshu", "scheduled_date": "2026-06-20"}]
    intent = _intent(
        name="schedule_commit",
        allowed_tools=["commit_publishing_schedule"],
        server_confirmed=True,
        slots={"proposal_plan": plan},
    )
    authorize_tool_call(
        "commit_publishing_schedule",
        {"plan": plan},
        intent,
        consume_capability=_allow_capability,
    )
    with pytest.raises(ToolPolicyDenied, match="differ"):
        authorize_tool_call(
            "commit_publishing_schedule",
            {"plan": [{**plan[0], "scheduled_date": "2026-06-21"}]},
            intent,
            consume_capability=_allow_capability,
        )


def test_schedule_commit_without_persisted_proposal_is_denied():
    intent = _intent(
        name="schedule_commit",
        allowed_tools=["commit_publishing_schedule"],
        server_confirmed=True,
        slots={},
    )
    with pytest.raises(ToolPolicyDenied, match="persisted prior proposal"):
        authorize_tool_call(
            "commit_publishing_schedule",
            {"plan": []},
            intent,
            consume_capability=_allow_capability,
        )


def test_exact_confirmation_without_durable_capability_is_denied():
    """A legacy thread whose proposal predates proposed_actions cannot write."""
    args = {"target": "user", "text": "legacy"}
    intent = _intent(
        name="action_confirm",
        allowed_tools=["memory_add"],
        server_confirmed=True,
        action_id=None,
        slots={"approved_tool_name": "memory_add", "approved_args": args},
    )
    with pytest.raises(ToolPolicyDenied, match="no durable confirmed capability"):
        authorize_tool_call("memory_add", args, intent, consume_capability=_allow_capability)


def test_write_without_capability_consumer_is_denied():
    args = {"target": "user", "text": "no consumer"}
    intent = _intent(
        name="action_confirm",
        allowed_tools=["memory_add"],
        server_confirmed=True,
        slots={"approved_tool_name": "memory_add", "approved_args": args},
    )
    with pytest.raises(ToolPolicyDenied, match="without a capability consumer"):
        authorize_tool_call("memory_add", args, intent)


def test_confirmed_capability_authorizes_exactly_one_invocation():
    """Replay inside one turn is denied even with byte-identical arguments."""
    args = {"target": "user", "text": "once"}
    intent = _intent(
        name="action_confirm",
        allowed_tools=["memory_add"],
        server_confirmed=True,
        slots={"approved_tool_name": "memory_add", "approved_args": args},
    )
    ledger = _CapabilityLedger(tool_name="memory_add", args=args)
    authorize_tool_call("memory_add", args, intent, consume_capability=ledger)
    with pytest.raises(ToolPolicyDenied, match="already used, expired, or cancelled"):
        authorize_tool_call("memory_add", args, intent, consume_capability=ledger)
    assert ledger.consumed == ["act_test_capability"]


@pytest.mark.asyncio
async def test_large_schedule_proposal_survives_executor_event_persistence():
    class _ScheduleStore:
        @staticmethod
        def get_content(content_id):
            return {
                "id": content_id,
                "title": f"content-{content_id}",
                "content_type": "xiaohongshu",
            }

        @staticmethod
        def get_calendar_conflicts(start, end):
            return []

    args = {
        "content_ids": list(range(1, 101)),
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "cadence": "daily",
    }
    model = _OneToolModel("propose_publishing_schedule", args)
    service = ChatAgentService(
        store=_ScheduleStore(),
        model_factory=lambda *unused: model,
        context_engine=None,
    )
    _, events, _ = await service._run_agent(
        history=[],
        message="propose a schedule",
        provider="claude",
        model="test",
        temperature=0.7,
        max_tokens=256,
        intent=_intent(
            name="schedule_propose",
            allowed_tools=["propose_publishing_schedule"],
        ),
    )
    payload = json.loads(events[0].output)
    assert len(events[0].output) > 1200
    assert len(payload["plan"]) == 100
    assert payload["plan"][-1]["content_id"] == 100


@pytest.mark.asyncio
async def test_executor_does_not_invoke_denied_write_tool(tmp_path):
    memory = FileMemory(tmp_path / "memory")
    model = _OneToolModel("memory_add", {"target": "user", "text": "blocked"})
    service = ChatAgentService(
        store=object(),
        model_factory=lambda *args: model,
        file_memory=memory,
        context_engine=None,
    )
    _, events, _ = await service._run_agent(
        history=[],
        message="remember this",
        provider="claude",
        model="test",
        temperature=0.7,
        max_tokens=256,
        thread_id="policy-denied",
        intent=_intent(
            name="memory_update",
            allowed_tools=["memory_add"],
            requires_confirmation=True,
        ),
    )
    assert memory.load(USER) == ""
    assert events[0].status == "proposed"
    assert events[0].error is None
    assert events[0].args == {"target": "user", "text": "blocked"}


@pytest.mark.asyncio
async def test_executor_invokes_only_exact_persisted_confirmation(tmp_path):
    memory = FileMemory(tmp_path / "memory")
    model = _OneToolModel("memory_add", {"target": "user", "text": "allowed"})

    class _CapabilityStore:
        """Minimal store exposing only the capability seam the executor uses."""

        def __init__(self):
            self.claims = []
            self.idempotency_claims = []

        def consume_proposed_action(self, action_id, *, tool_name, args, consuming_message_id=None):
            if action_id in self.claims:
                return None
            self.claims.append(action_id)
            return {"id": action_id, "tool_name": tool_name, "status": "consumed"}

        def claim_idempotency_key(self, *, scope, key, args, external_request_id=None):
            """Stub idempotency claim that always returns fresh."""
            record_id = f"{scope}:{key}"
            self.idempotency_claims.append(record_id)
            return {"outcome": "fresh", "record_id": record_id}

        def complete_idempotency_key(self, record_id, *, result):
            """Stub completion."""
            pass

        def fail_idempotency_key(self, record_id):
            """Stub failure."""
            pass

    store = _CapabilityStore()
    service = ChatAgentService(
        store=store,
        model_factory=lambda *args: model,
        file_memory=memory,
        context_engine=None,
    )
    _, events, _ = await service._run_agent(
        history=[],
        message="yes",
        provider="claude",
        model="test",
        temperature=0.7,
        max_tokens=256,
        thread_id="policy-allowed",
        intent=_intent(
            name="action_confirm",
            allowed_tools=["memory_add"],
            requires_confirmation=False,
            server_confirmed=True,
            slots={
                "approved_tool_name": "memory_add",
                "approved_args": {"target": "user", "text": "allowed"},
            },
        ),
    )
    assert "allowed" in memory.load(USER)
    assert events[0].status == "completed"
    # The write went through the durable capability rather than argument
    # equality alone, and claimed it exactly once.
    assert store.claims == ["act_test_capability"]
