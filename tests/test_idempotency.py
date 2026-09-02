"""Business idempotency key contracts (P1-02 part A).

Every test asserts the real database side-effect count, not just the returned
value: a retry that returns the right payload while writing a second row is the
failure these guard against.
"""
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest
from sqlalchemy import text

from src.api.schemas.content import GenerateRequest, RefineRequest
from src.api.services import content_service
from src.models import ContentStyle, ContentType
from src.utils.idempotency import (
    SCOPE_CALENDAR_COMMIT,
    SCOPE_CONTENT_CREATE,
    SCOPE_CONTENT_REFINE,
    DuplicateRequestInFlight,
    IdempotencyKeyConflict,
    entry_key,
    idempotent_write,
    request_key,
)


ARGS = {"topic": "AI workflows", "style": "casual"}


class FakeLLM:
    """Counts provider calls so a replay can be shown to skip generation."""

    def __init__(self):
        self.calls = 0

    async def generate_from_prompts(self, **kwargs):
        self.calls += 1
        return f"【标题】\n标题 {self.calls}\n\n【正文】\n正文 {self.calls}\n\n【标签】\nAI"


def _count(store, table="idempotency_records", where=""):
    clause = f" WHERE {where}" if where else ""
    with store.engine.connect() as connection:
        return connection.execute(text(f"SELECT count(*) FROM {table}{clause}")).scalar_one()


def _seed_content(store, title="original"):
    from src.models import GeneratedContent

    return store.save_content(
        GeneratedContent(content=f"{title} body", title=title, tags=[], content_type=ContentType.XIAOHONGSHU),
        style="casual",
    )


def test_claim_then_complete_makes_a_retry_replay_the_original_result(store):
    first = store.claim_idempotency_key(scope=SCOPE_CONTENT_CREATE, key="k-1", args=ARGS)
    assert first["outcome"] == "claimed"
    store.complete_idempotency_key(first["record_id"], result={"content_id": 41})

    second = store.claim_idempotency_key(scope=SCOPE_CONTENT_CREATE, key="k-1", args=ARGS)
    assert second["outcome"] == "replay"
    assert second["result"] == {"content_id": 41}
    # The retry must not add a second ledger row.
    assert _count(store) == 1


def test_second_claim_while_in_flight_is_refused(store):
    store.claim_idempotency_key(scope=SCOPE_CONTENT_CREATE, key="k-flight", args=ARGS)
    with pytest.raises(DuplicateRequestInFlight):
        store.claim_idempotency_key(scope=SCOPE_CONTENT_CREATE, key="k-flight", args=ARGS)
    assert _count(store) == 1


def test_same_key_with_different_args_fails_closed(store):
    store.claim_idempotency_key(scope=SCOPE_CONTENT_CREATE, key="k-tamper", args=ARGS)
    store.complete_idempotency_key(
        store.get_idempotency_record(scope=SCOPE_CONTENT_CREATE, key="k-tamper")["id"],
        result={"content_id": 7},
    )
    with pytest.raises(IdempotencyKeyConflict):
        store.claim_idempotency_key(
            scope=SCOPE_CONTENT_CREATE,
            key="k-tamper",
            args={"topic": "something else", "style": "casual"},
        )


def test_failed_attempt_is_retryable_and_reuses_one_row(store):
    claim = store.claim_idempotency_key(scope=SCOPE_CONTENT_CREATE, key="k-fail", args=ARGS)
    assert store.fail_idempotency_key(claim["record_id"]) is True

    retry = store.claim_idempotency_key(scope=SCOPE_CONTENT_CREATE, key="k-fail", args=ARGS)
    assert retry["outcome"] == "claimed"
    # A permanently burned key would make the request unretryable; the unique
    # constraint also forbids inserting a second row for it.
    assert _count(store) == 1


def test_same_key_in_different_scopes_is_not_deduplicated(store):
    a = store.claim_idempotency_key(scope=SCOPE_CONTENT_CREATE, key="shared", args=ARGS)
    b = store.claim_idempotency_key(scope=SCOPE_CALENDAR_COMMIT, key="shared", args=ARGS)
    c = store.claim_idempotency_key(scope=SCOPE_CONTENT_REFINE, key="shared", args=ARGS)
    assert {a["outcome"], b["outcome"], c["outcome"]} == {"claimed"}
    assert _count(store) == 3


def test_concurrent_claims_of_one_key_yield_exactly_one_winner(store):
    barrier = threading.Barrier(4)
    outcomes: list[object] = []

    def claim():
        barrier.wait()
        try:
            return store.claim_idempotency_key(scope=SCOPE_CONTENT_CREATE, key="race", args=ARGS)
        except DuplicateRequestInFlight:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = [item.result() for item in [pool.submit(claim) for _ in range(4)]]

    winners = [item for item in outcomes if item and item["outcome"] == "claimed"]
    assert len(winners) == 1
    assert _count(store) == 1


def test_idempotent_write_runs_the_write_once_for_one_key(store):
    calls = []

    def write():
        calls.append(1)
        return {"event_id": len(calls)}

    first = idempotent_write(
        store, scope=SCOPE_CALENDAR_COMMIT, key="w-1", args=ARGS, write=write
    )
    second = idempotent_write(
        store, scope=SCOPE_CALENDAR_COMMIT, key="w-1", args=ARGS, write=write
    )
    assert first == second == {"event_id": 1}
    assert len(calls) == 1


def test_idempotent_write_without_a_key_leaves_behavior_unchanged(store):
    calls = []

    def write():
        calls.append(1)
        return len(calls)

    assert idempotent_write(store, scope=SCOPE_CALENDAR_COMMIT, key=None, args=ARGS, write=write) == 1
    assert idempotent_write(store, scope=SCOPE_CALENDAR_COMMIT, key=None, args=ARGS, write=write) == 2
    # No key means the client promised nothing about retries: no ledger row.
    assert _count(store) == 0


def test_idempotent_write_releases_the_key_when_the_write_raises(store):
    def boom():
        raise RuntimeError("provider exploded")

    with pytest.raises(RuntimeError):
        idempotent_write(store, scope=SCOPE_CALENDAR_COMMIT, key="w-err", args=ARGS, write=boom)

    record = store.get_idempotency_record(scope=SCOPE_CALENDAR_COMMIT, key="w-err")
    assert record["status"] == "failed"

    # The user must be able to retry after a transient failure.
    assert idempotent_write(
        store, scope=SCOPE_CALENDAR_COMMIT, key="w-err", args=ARGS, write=lambda: "ok"
    ) == "ok"


def test_calendar_writes_are_deduplicated_per_key_not_per_business_columns(store):
    content_id = _seed_content(store)
    from datetime import date

    def write():
        return store.save_calendar_event(content_id, "xiaohongshu", date(2026, 9, 10))

    args = {"content_id": content_id, "platform": "xiaohongshu", "scheduled_date": "2026-09-10"}
    first = idempotent_write(store, scope=SCOPE_CALENDAR_COMMIT, key="cal-1", args=args, write=write)
    replay = idempotent_write(store, scope=SCOPE_CALENDAR_COMMIT, key="cal-1", args=args, write=write)
    assert first == replay
    assert _count(store, "calendar_events") == 1

    # A different key for the identical slot is an intentional second scheduling
    # (morning + evening repost), so it must still write.
    idempotent_write(store, scope=SCOPE_CALENDAR_COMMIT, key="cal-2", args=args, write=write)
    assert _count(store, "calendar_events") == 2


def test_entry_keys_keep_duplicate_plan_items_from_collapsing(store):
    content_id = _seed_content(store)
    from datetime import date

    plan = [
        {"content_id": content_id, "platform": "xiaohongshu", "scheduled_date": "2026-09-11"},
        {"content_id": content_id, "platform": "xiaohongshu", "scheduled_date": "2026-09-11"},
    ]
    for index, item in enumerate(plan):
        idempotent_write(
            store,
            scope=SCOPE_CALENDAR_COMMIT,
            key=entry_key("action-abc", index),
            args=item,
            write=lambda: store.save_calendar_event(content_id, "xiaohongshu", date(2026, 9, 11)),
        )
    # Two identical approved entries must produce two rows, not one.
    assert _count(store, "calendar_events") == 2

    # Replaying the whole batch writes nothing further.
    for index, item in enumerate(plan):
        idempotent_write(
            store,
            scope=SCOPE_CALENDAR_COMMIT,
            key=entry_key("action-abc", index),
            args=item,
            write=lambda: store.save_calendar_event(content_id, "xiaohongshu", date(2026, 9, 11)),
        )
    assert _count(store, "calendar_events") == 2


def test_concurrent_calendar_writes_with_one_key_produce_exactly_one_row(store):
    content_id = _seed_content(store)
    from datetime import date

    barrier = threading.Barrier(4)
    args = {"content_id": content_id, "platform": "weibo", "scheduled_date": "2026-09-12"}

    def commit():
        barrier.wait()
        try:
            return idempotent_write(
                store,
                scope=SCOPE_CALENDAR_COMMIT,
                key="cal-race",
                args=args,
                write=lambda: store.save_calendar_event(content_id, "weibo", date(2026, 9, 12)),
            )
        except DuplicateRequestInFlight:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        [item.result() for item in [pool.submit(commit) for _ in range(4)]]

    assert _count(store, "calendar_events") == 1


@pytest.mark.asyncio
async def test_content_create_retry_replays_without_a_second_row_or_llm_call(store):
    llm = FakeLLM()
    request = GenerateRequest(
        topic="AI workflows",
        content_type=ContentType.XIAOHONGSHU,
        style=ContentStyle.CASUAL,
    )
    with request_key("create-1"):
        first_id, first, _, _ = await content_service.generate_content(request, llm, store)
        second_id, second, _, _ = await content_service.generate_content(request, llm, store)

    assert first_id == second_id
    assert first.content == second.content
    assert _count(store, "contents") == 1
    # Replay must skip the provider too, otherwise the retry is billed again.
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_content_create_without_a_key_still_regenerates(store):
    llm = FakeLLM()
    request = GenerateRequest(
        topic="AI workflows",
        content_type=ContentType.XIAOHONGSHU,
        style=ContentStyle.CASUAL,
    )
    await content_service.generate_content(request, llm, store)
    await content_service.generate_content(request, llm, store)
    # Asking for another draft of the same topic is legitimate and must not dedupe.
    assert _count(store, "contents") == 2
    assert llm.calls == 2


@pytest.mark.asyncio
async def test_content_refine_retry_replays_both_of_its_writes(store):
    parent_id = _seed_content(store, title="parent")
    llm = FakeLLM()
    request = RefineRequest(content_id=parent_id, instruction="Tighten the hook")

    with request_key("refine-1"):
        first_id, _, _, _ = await content_service.refine_content(request, llm, store)
        second_id, _, _, _ = await content_service.refine_content(request, llm, store)

    assert first_id == second_id
    # One parent + exactly one refined child.
    assert _count(store, "contents") == 2
    assert llm.calls == 1
    # The status update is part of the same logical operation, so the replayed
    # row must still be the completed "refined" one.
    assert store.get_content(first_id)["status"] == "refined"


@pytest.mark.asyncio
async def test_refine_and_create_may_share_a_key_without_cross_deduplication(store):
    parent_id = _seed_content(store, title="parent")
    llm = FakeLLM()

    with request_key("shared-key"):
        created_id, _, _, _ = await content_service.generate_content(
            GenerateRequest(
                topic="AI workflows",
                content_type=ContentType.XIAOHONGSHU,
                style=ContentStyle.CASUAL,
            ),
            llm,
            store,
        )
        refined_id, _, _, _ = await content_service.refine_content(
            RefineRequest(content_id=parent_id, instruction="Tighten the hook"),
            llm,
            store,
        )

    assert created_id != refined_id
    assert _count(store, "idempotency_records", "idempotency_key = 'shared-key'") == 2
