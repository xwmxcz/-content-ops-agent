"""Business idempotency keys for write operations (P1-02).

A key identifies one *request*, never the payload. Two genuinely different user
requests can carry byte-identical arguments — regenerating the same topic,
re-refining with the default instruction, reposting the same content on the same
day — so keying on argument content would collapse legitimate repeats. The key
therefore comes from request identity:

- chat lane: the ``proposed_actions.id`` consumed by the policy gate, which is
  already unique per authorization;
- HTTP lane: a client-supplied ``Idempotency-Key`` header. When the client sends
  no key it has promised nothing about reuse, so behavior stays unchanged.

``args_hash`` is stored alongside as a tamper cross-check, mirroring
``consume_proposed_action``: the same key arriving with different arguments is a
client error and fails closed rather than returning the first result.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar


# Scope namespaces the key so one key value reused across resource families does
# not cross-deduplicate. This is what satisfies "不同资源范围不误去重".
SCOPE_CONTENT_CREATE = "content.create"
SCOPE_CONTENT_REFINE = "content.refine"
SCOPE_CALENDAR_COMMIT = "calendar.commit"
SCOPE_PUBLICATION_CREATE = "publication.create"
SCOPE_PUBLICATION_EXECUTE = "publication.execute"
SCOPE_MEMORY_MUTATION = "memory.mutate"

IDEMPOTENCY_SCOPES = (
    SCOPE_CONTENT_CREATE,
    SCOPE_CONTENT_REFINE,
    SCOPE_CALENDAR_COMMIT,
    SCOPE_PUBLICATION_CREATE,
    SCOPE_PUBLICATION_EXECUTE,
    SCOPE_MEMORY_MUTATION,
)

# Statuses of a ledger row. ``failed`` is retryable; ``completed`` replays.
IDEMPOTENCY_STATUSES = ("in_progress", "completed", "failed")


class DuplicateRequestInFlight(RuntimeError):
    """Another request already holds this key and has not finished.

    Raised instead of writing, so concurrent duplicates produce exactly one side
    effect rather than two.
    """


class IdempotencyKeyConflict(RuntimeError):
    """The key was reused with different arguments.

    Returning the first result would silently discard the second request's
    intent, so this fails closed.
    """


_REQUEST_KEY: ContextVar[str | None] = ContextVar("idempotency_request_key", default=None)


def current_request_key() -> str | None:
    """The request identity in scope, or ``None`` when the caller supplied none."""
    return _REQUEST_KEY.get()


@contextmanager
def request_key(key: str | None):
    """Bind one request identity for the duration of a single write call."""
    token = _REQUEST_KEY.set(key)
    try:
        yield key
    finally:
        _REQUEST_KEY.reset(token)


def publication_request_id(publication_id: int) -> str:
    """Stable external request id for one publication attempt.

    Derived from the durable ``platform_publications.id`` rather than generated
    per call, so a job retry, a worker restart, or a re-enqueue all present the
    same token to the platform. A ``uuid4()`` per attempt would look unique to
    the provider on every retry, which is exactly the double-publish this
    prevents.
    """
    return f"pub-{int(publication_id)}"


def entry_key(key: str, index: int) -> str:
    """Sub-key for one entry of a fan-out write.

    ``commit_publishing_schedule`` writes N calendar rows under one
    authorization, and a plan may legitimately contain two identical entries. A
    single per-request key would collapse those into fewer than N rows, so each
    entry is keyed by its position within the approved plan.
    """
    return f"{key}:{index}"


def idempotent_write(
    store,
    *,
    scope: str,
    key: str | None,
    args: dict,
    write,
    external_request_id: str | None = None,
):
    """Run ``write`` at most once per ``(scope, key)``, replaying prior results.

    With no key the caller has promised nothing about retries, so the write runs
    unguarded and behavior is unchanged. With a key, the ledger row is claimed
    before the write and completed after: a crash in between leaves the row
    ``in_progress``, which fails closed for concurrent duplicates and is released
    by :meth:`ContentStore.fail_idempotency_key` on a raised exception so the user
    can retry.

    The claim commits in its own transaction before the write, exactly like
    capability consumption in P1-01, so the guarantee is "replayable for retries
    that reuse the key" rather than true exactly-once across a crash.
    """
    if not key:
        return write()

    claim = store.claim_idempotency_key(
        scope=scope,
        key=key,
        args=args,
        external_request_id=external_request_id,
    )
    if claim["outcome"] == "replay":
        return claim["result"]

    record_id = claim["record_id"]
    try:
        result = write()
    except Exception:
        store.fail_idempotency_key(record_id)
        raise
    store.complete_idempotency_key(record_id, result=result)
    return result


async def idempotent_write_async(
    store,
    *,
    scope: str,
    key: str | None,
    args: dict,
    write,
    external_request_id: str | None = None,
):
    """Async counterpart of :func:`idempotent_write`.

    The claim is taken *before* awaiting ``write``, so a replayed retry skips the
    provider call as well as the database write. That matters for cost: re-running
    a generation would bill a second time even if the row were deduplicated.
    """
    if not key:
        return await write()

    claim = store.claim_idempotency_key(
        scope=scope,
        key=key,
        args=args,
        external_request_id=external_request_id,
    )
    if claim["outcome"] == "replay":
        return claim["result"]

    record_id = claim["record_id"]
    try:
        result = await write()
    except Exception:
        store.fail_idempotency_key(record_id)
        raise
    store.complete_idempotency_key(record_id, result=result)
    return result
