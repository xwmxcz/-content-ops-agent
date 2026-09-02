"""Durable one-time write capability contracts (P1-01).

Every test asserts the real database side-effect count, not only the returned
status: a denial that still writes a row is the failure these guard against.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import threading

import pytest
from sqlalchemy import inspect, text

from src.api.schemas.agent import ChatIntent
from src.api.services.tool_policy import ToolPolicyDenied, authorize_tool_call
from src.utils.canonical import args_hash


MEMORY_ARGS = {"target": "user", "text": "durable capability"}


def _thread(store, thread_id="thread_actions"):
    store.upsert_agent_thread(thread_id, title="actions", provider="claude", model="test")
    return thread_id


def _propose(store, thread_id, *, tool_name="memory_add", args=None, ttl_seconds=900):
    return store.create_proposed_action(
        thread_id=thread_id,
        tool_name=tool_name,
        args=args if args is not None else MEMORY_ARGS,
        impact_summary="Append a durable user memory entry",
        ttl_seconds=ttl_seconds,
    )


def _confirmed_intent(action_id, *, tool_name="memory_add", args=None):
    intent = ChatIntent(
        name="action_confirm",
        confidence=0.99,
        allowed_tools=[tool_name],
        slots={},
    )
    intent.bind_server_approval(tool_name, args if args is not None else MEMORY_ARGS, action_id)
    return intent


def _count_actions(store, status):
    with store.engine.connect() as connection:
        return connection.execute(
            text("SELECT count(*) FROM proposed_actions WHERE status = :status"),
            {"status": status},
        ).scalar_one()


def test_proposed_action_schema_has_capability_indexes(store):
    indexes = {
        tuple(index.get("column_names") or [])
        for index in inspect(store.engine).get_indexes("proposed_actions")
    }
    assert {("thread_id", "created_at"), ("status", "expires_at")} <= indexes


def test_proposal_persists_canonical_args_hash_and_expiry(store):
    thread_id = _thread(store)
    action = _propose(store, thread_id)

    assert action["status"] == "proposed"
    assert action["args_hash"] == args_hash(MEMORY_ARGS)
    assert action["impact_summary"]
    assert action["consumed_at"] is None
    # Key order must not change the stored hash, or a re-serialized confirmation
    # would fail to match its own proposal.
    assert args_hash({"text": "durable capability", "target": "user"}) == action["args_hash"]
    stored = store.get_proposed_action(action["id"])
    assert stored["thread_id"] == thread_id
    assert stored["args"] == MEMORY_ARGS
    assert datetime.fromisoformat(stored["expires_at"]) > datetime.fromisoformat(stored["created_at"])


def test_confirmed_capability_is_consumable_exactly_once(store):
    thread_id = _thread(store)
    action = _propose(store, thread_id)
    assert store.confirm_proposed_action(action["id"])["status"] == "confirmed"

    first = store.consume_proposed_action(action["id"], tool_name="memory_add", args=MEMORY_ARGS)
    replay = store.consume_proposed_action(action["id"], tool_name="memory_add", args=MEMORY_ARGS)

    assert first is not None and first["status"] == "consumed"
    assert replay is None
    assert _count_actions(store, "consumed") == 1
    assert store.get_proposed_action(action["id"])["consumed_at"] is not None


def test_unconfirmed_proposal_cannot_be_consumed(store):
    thread_id = _thread(store)
    action = _propose(store, thread_id)

    assert store.consume_proposed_action(action["id"], tool_name="memory_add", args=MEMORY_ARGS) is None
    assert store.get_proposed_action(action["id"])["status"] == "proposed"
    assert _count_actions(store, "consumed") == 0


def test_expired_proposal_fails_closed_and_is_not_confirmable(store):
    thread_id = _thread(store)
    action = _propose(store, thread_id, ttl_seconds=1)
    with store.engine.begin() as connection:
        connection.execute(
            text("UPDATE proposed_actions SET expires_at = :past WHERE id = :id"),
            {"past": datetime.now() - timedelta(seconds=5), "id": action["id"]},
        )

    assert store.confirm_proposed_action(action["id"]) is None
    assert store.get_proposed_action(action["id"])["status"] == "expired"
    # An expired proposal must not be silently treated as confirmed.
    assert store.consume_proposed_action(action["id"], tool_name="memory_add", args=MEMORY_ARGS) is None
    assert store.latest_pending_proposed_action(thread_id) is None
    assert _count_actions(store, "consumed") == 0


def test_capability_expiring_after_confirmation_cannot_be_consumed(store):
    thread_id = _thread(store)
    action = _propose(store, thread_id)
    store.confirm_proposed_action(action["id"])
    with store.engine.begin() as connection:
        connection.execute(
            text("UPDATE proposed_actions SET expires_at = :past WHERE id = :id"),
            {"past": datetime.now() - timedelta(seconds=5), "id": action["id"]},
        )

    assert store.consume_proposed_action(action["id"], tool_name="memory_add", args=MEMORY_ARGS) is None
    assert store.get_proposed_action(action["id"])["status"] == "expired"
    assert _count_actions(store, "consumed") == 0


@pytest.mark.parametrize(
    "tampered_args",
    [
        {"target": "user", "text": "TAMPERED"},
        {"target": "agent", "text": "durable capability"},
        {"target": "user", "text": "durable capability", "extra": 1},
    ],
)
def test_tampered_arguments_cannot_consume_a_valid_capability(store, tampered_args):
    thread_id = _thread(store)
    action = _propose(store, thread_id)
    store.confirm_proposed_action(action["id"])

    assert store.consume_proposed_action(action["id"], tool_name="memory_add", args=tampered_args) is None
    # The capability must remain usable for the argument set the user approved.
    assert store.get_proposed_action(action["id"])["status"] == "confirmed"
    assert store.consume_proposed_action(action["id"], tool_name="memory_add", args=MEMORY_ARGS) is not None
    assert _count_actions(store, "consumed") == 1


def test_rescoped_tool_cannot_consume_another_tools_capability(store):
    thread_id = _thread(store)
    action = _propose(store, thread_id)
    store.confirm_proposed_action(action["id"])

    assert store.consume_proposed_action(
        action["id"], tool_name="memory_remove", args=MEMORY_ARGS
    ) is None
    assert store.get_proposed_action(action["id"])["status"] == "confirmed"
    assert _count_actions(store, "consumed") == 0


def test_cancelled_capability_cannot_be_consumed(store):
    thread_id = _thread(store)
    action = _propose(store, thread_id)
    store.confirm_proposed_action(action["id"])
    assert store.cancel_proposed_action(action["id"])["status"] == "cancelled"

    assert store.consume_proposed_action(action["id"], tool_name="memory_add", args=MEMORY_ARGS) is None
    assert _count_actions(store, "consumed") == 0


def test_consumed_capability_cannot_be_cancelled_afterwards(store):
    thread_id = _thread(store)
    action = _propose(store, thread_id)
    store.confirm_proposed_action(action["id"])
    store.consume_proposed_action(action["id"], tool_name="memory_add", args=MEMORY_ARGS)

    assert store.cancel_proposed_action(action["id"]) is None
    assert store.get_proposed_action(action["id"])["status"] == "consumed"


def test_concurrent_double_confirm_issues_one_capability(store):
    """A double-clicked confirmation must not produce two usable capabilities."""
    thread_id = _thread(store)
    action = _propose(store, thread_id)
    barrier = threading.Barrier(2)

    def confirm():
        barrier.wait()
        return store.confirm_proposed_action(action["id"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(confirm), pool.submit(confirm)]
        outcomes = [item.result() for item in results]

    assert sum(outcome is not None for outcome in outcomes) == 1
    assert store.get_proposed_action(action["id"])["status"] == "confirmed"
    # Exactly one consumption remains possible regardless of the confirm race.
    assert store.consume_proposed_action(action["id"], tool_name="memory_add", args=MEMORY_ARGS) is not None
    assert store.consume_proposed_action(action["id"], tool_name="memory_add", args=MEMORY_ARGS) is None
    assert _count_actions(store, "consumed") == 1


def test_concurrent_double_consume_yields_exactly_one_side_effect(store):
    """Two racing executions of the same confirmed action: one wins."""
    thread_id = _thread(store)
    action = _propose(store, thread_id)
    store.confirm_proposed_action(action["id"])
    barrier = threading.Barrier(4)

    def consume():
        barrier.wait()
        return store.consume_proposed_action(
            action["id"], tool_name="memory_add", args=MEMORY_ARGS
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = [item.result() for item in [pool.submit(consume) for _ in range(4)]]

    assert sum(outcome is not None for outcome in outcomes) == 1
    assert _count_actions(store, "consumed") == 1


def test_policy_gate_denies_replay_against_the_real_store(store):
    """End-to-end: the executor's gate consumes the durable row exactly once."""
    thread_id = _thread(store)
    action = _propose(store, thread_id)
    store.confirm_proposed_action(action["id"])
    intent = _confirmed_intent(action["id"])

    def consume(action_id, tool_name, args):
        return store.consume_proposed_action(action_id, tool_name=tool_name, args=args)

    authorize_tool_call("memory_add", MEMORY_ARGS, intent, consume_capability=consume)
    with pytest.raises(ToolPolicyDenied, match="already used, expired, or cancelled"):
        authorize_tool_call("memory_add", MEMORY_ARGS, intent, consume_capability=consume)
    assert _count_actions(store, "consumed") == 1


def test_legacy_proposal_without_durable_row_cannot_write(store):
    """Pre-existing threads have no capability, so they must fail closed."""
    thread_id = _thread(store, "thread_legacy")
    intent = ChatIntent(
        name="action_confirm",
        confidence=0.99,
        allowed_tools=["memory_add"],
        slots={"approved_tool_name": "memory_add", "approved_args": MEMORY_ARGS},
    )
    # Exact argument evidence, but no durable action id: this is the legacy shape.
    intent.bind_server_approval("memory_add", MEMORY_ARGS, None)

    def consume(action_id, tool_name, args):
        return store.consume_proposed_action(action_id, tool_name=tool_name, args=args)

    with pytest.raises(ToolPolicyDenied, match="no durable confirmed capability"):
        authorize_tool_call("memory_add", MEMORY_ARGS, intent, consume_capability=consume)
    assert _count_actions(store, "consumed") == 0


def test_latest_pending_proposal_is_thread_scoped(store):
    mine = _thread(store, "thread_mine")
    other = _thread(store, "thread_other")
    _propose(store, other, args={"target": "user", "text": "other thread"})
    action = _propose(store, mine)

    pending = store.latest_pending_proposed_action(mine)
    assert pending["id"] == action["id"]
    assert pending["thread_id"] == mine
    assert store.latest_pending_proposed_action(mine, tool_name="memory_remove") is None


def test_expire_proposed_actions_sweeps_only_overdue_rows(store):
    thread_id = _thread(store)
    stale = _propose(store, thread_id)
    fresh = _propose(store, thread_id, args={"target": "user", "text": "fresh"})
    with store.engine.begin() as connection:
        connection.execute(
            text("UPDATE proposed_actions SET expires_at = :past WHERE id = :id"),
            {"past": datetime.now() - timedelta(seconds=5), "id": stale["id"]},
        )

    assert store.expire_proposed_actions(thread_id=thread_id) == 1
    assert store.get_proposed_action(stale["id"])["status"] == "expired"
    assert store.get_proposed_action(fresh["id"])["status"] == "proposed"


@pytest.mark.parametrize("status", ["proposed", "confirmed", "consumed"])
def test_thread_delete_clears_capabilities_in_every_state(store, status):
    """``proposed_actions.thread_id`` is a NO ACTION foreign key.

    Without an explicit delete, any thread that ever proposed a write becomes
    permanently undeletable with a ForeignKeyViolation, so this asserts the
    thread is gone and no orphan capability row survives.
    """
    thread_id = _thread(store, "thread_delete_caps")
    action = _propose(store, thread_id)
    if status in {"confirmed", "consumed"}:
        store.confirm_proposed_action(action["id"])
    if status == "consumed":
        store.consume_proposed_action(
            action["id"], tool_name="memory_add", args=MEMORY_ARGS
        )
    assert store.get_proposed_action(action["id"])["status"] == status

    assert store.delete_agent_thread(thread_id) is True
    assert store.get_proposed_action(action["id"]) is None
    assert _count_actions(store, status) == 0
