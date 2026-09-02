"""Server-side authorization policy for Chat Agent tools.

Prompts and model-produced intent are not authorization boundaries.  The executor
calls this module immediately before every tool invocation and refuses all
side-effecting tools unless the server-recognized intent authorizes that exact
operation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from src.api.schemas.agent import ChatIntent
from src.utils.canonical import canonical_json


ToolEffect = Literal["read_only", "side_effect"]
ToolRisk = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class ToolPolicy:
    effect: ToolEffect
    risk: ToolRisk
    resource: str


# Keep this registry explicit and exhaustive. Adding a Chat tool without adding
# a policy must fail tests rather than silently inheriting write permission.
TOOL_POLICIES: dict[str, ToolPolicy] = {
    "create_content": ToolPolicy("side_effect", "medium", "content"),
    "refine_content": ToolPolicy("side_effect", "medium", "content"),
    "generate_title_options": ToolPolicy("read_only", "low", "llm"),
    "optimize_seo": ToolPolicy("read_only", "low", "content"),
    "view_content": ToolPolicy("read_only", "low", "content"),
    "list_recent_contents": ToolPolicy("read_only", "low", "content"),
    "add_to_calendar": ToolPolicy("side_effect", "high", "calendar"),
    "view_calendar": ToolPolicy("read_only", "low", "calendar"),
    "get_content_stats": ToolPolicy("read_only", "low", "analytics"),
    "check_xiaohongshu_login": ToolPolicy("read_only", "low", "publication"),
    "search_history": ToolPolicy("read_only", "low", "content"),
    "web_search": ToolPolicy("read_only", "medium", "external_search"),
    "analyze_content_performance": ToolPolicy("read_only", "low", "analytics"),
    "find_optimization_candidates": ToolPolicy("read_only", "low", "content"),
    "propose_topics": ToolPolicy("read_only", "low", "content"),
    "propose_publishing_schedule": ToolPolicy("read_only", "low", "calendar"),
    "commit_publishing_schedule": ToolPolicy("side_effect", "high", "calendar"),
    "memory_add": ToolPolicy("side_effect", "high", "memory"),
    "memory_replace": ToolPolicy("side_effect", "high", "memory"),
    "memory_remove": ToolPolicy("side_effect", "high", "memory"),
    "session_search": ToolPolicy("read_only", "low", "memory"),
}

SIDE_EFFECT_TOOLS = frozenset(
    name for name, policy in TOOL_POLICIES.items() if policy.effect == "side_effect"
)

class ToolPolicyDenied(PermissionError):
    """Raised when a model requests a tool call without server authorization."""


class ToolApprovalRequired(ToolPolicyDenied):
    """The exact model-proposed write must be confirmed in a later turn."""

    def __init__(self, tool_name: str, args: dict[str, Any]):
        super().__init__(f"Write tool `{tool_name}` requires confirmation of its exact arguments")
        self.tool_name = tool_name
        self.tool_args = args


# Consumes the durable capability for one invocation. Returns the consumed
# action record, or None when the capability was already used, expired, cancelled,
# or does not match this exact call.
CapabilityConsumer = Callable[[str, str, dict[str, Any]], Any]


def authorize_tool_call(
    name: str,
    args: dict[str, Any],
    intent: ChatIntent | None,
    *,
    consume_capability: CapabilityConsumer | None = None,
) -> None:
    """Authorize one model-requested tool call or fail closed.

    Read tools are allowed once they have already passed the intent allow-list
    used when binding tools. Side effects additionally require a recognized
    intent, explicit server-side confirmation state, an exact allow-list match,
    and a durable one-time capability that this call consumes. Schedule commits
    are bound to the plan persisted in the preceding proposal turn so the model
    cannot alter dates after confirmation.
    """
    policy = TOOL_POLICIES.get(name)
    if policy is None:
        raise ToolPolicyDenied(f"Tool `{name}` has no registered server policy")
    if policy.effect == "read_only":
        return

    if intent is None:
        raise ToolPolicyDenied(f"Write tool `{name}` requires a recognized intent")
    if name not in intent.allowed_tools:
        raise ToolPolicyDenied(f"Write tool `{name}` is outside the recognized intent")

    if name == "commit_publishing_schedule":
        if (
            intent._server_approved_tool_name != name
            or not isinstance(intent._server_approved_args, dict)
        ):
            raise ToolPolicyDenied("Schedule commit requires a persisted prior proposal")
        if not intent._server_confirmation_validated:
            raise ToolPolicyDenied("Schedule commit lacks server-validated confirmation")
        if _canonical(args) != _canonical(intent._server_approved_args):
            raise ToolPolicyDenied("Schedule commit arguments differ from the confirmed proposal")
        _consume_or_deny(name, args, intent, consume_capability)
        return

    if intent.name != "action_confirm":
        raise ToolApprovalRequired(name, args)
    if not intent._server_confirmation_validated:
        raise ToolPolicyDenied(f"Write tool `{name}` lacks server-validated confirmation")
    if (
        intent._server_approved_tool_name != name
        or not isinstance(intent._server_approved_args, dict)
    ):
        raise ToolPolicyDenied(f"Write tool `{name}` lacks an exact persisted proposal")
    if _canonical(args) != _canonical(intent._server_approved_args):
        raise ToolPolicyDenied(f"Write tool `{name}` arguments differ from the confirmed proposal")
    _consume_or_deny(name, args, intent, consume_capability)


def _consume_or_deny(
    name: str,
    args: dict[str, Any],
    intent: ChatIntent,
    consume_capability: CapabilityConsumer | None,
) -> None:
    """Claim the durable capability, or deny the write.

    Argument equality alone cannot bound how many times an approved call runs:
    the executor loop reuses one intent, and concurrent requests read the same
    pre-confirmation history. Consumption is what makes the approved write happen
    at most once. A caller that supplies no consumer gets no write.
    """
    if consume_capability is None:
        raise ToolPolicyDenied(
            f"Write tool `{name}` cannot execute without a capability consumer"
        )
    action_id = intent._server_approved_action_id
    if not action_id:
        raise ToolPolicyDenied(
            f"Write tool `{name}` has no durable confirmed capability; "
            "the action must be proposed and confirmed again"
        )
    if consume_capability(action_id, name, args) is None:
        raise ToolPolicyDenied(
            f"Write tool `{name}` capability was already used, expired, or cancelled"
        )


def validate_tool_policy_registry(tool_names: list[str]) -> None:
    missing = sorted(set(tool_names) - set(TOOL_POLICIES))
    stale = sorted(set(TOOL_POLICIES) - set(tool_names))
    if missing or stale:
        raise RuntimeError(f"Tool policy registry mismatch: missing={missing}, stale={stale}")


def _canonical(value: Any) -> str:
    return canonical_json(value)
