# Workflow Checkpoint

- Recorded at: `2026-09-02T23:00:00+08:00`
- Workflow: `report_driven_iterative_hardening_continuation`
- Repository HEAD/current base: `6dee18b`
- Status: **P1-01, P1-02, P1-03 complete and verified green; Phase 1 core infrastructure finished**
- Completed phase: `Recover and Remediate Phase 0` (repository-local scope)
- Current phase: `Phase 1 Reliability and Recovery` — **COMPLETE**
- Completed tasks:
  - `P1-01` — Persistent capability (implemented, reviewed, remediated, verified)
  - `P1-02` — Business idempotency (implemented, independently reviewed, verified)
  - `P1-03` — Automatic retry (implemented, verified)
- Working tree snapshot: 67 changed/untracked status entries; tracked diff summary is `47 files changed, 3565 insertions(+), 493 deletions(-)` (untracked file contents are not included in that stat). Nothing staged, nothing committed.
- Main implementation record: `docs/IMPROVEMENT_LOG.md`

## ⚠️ Read this before resuming

The suite is **green**: `300 passed` on the disposable PostgreSQL. Phase 1 core infrastructure is complete:

- **P1-01** (Persistent capability) — ✅ Complete, independently reviewed, remediated
- **P1-02** (Business idempotency) — ✅ Complete, independently reviewed (passed with 0 HIGH findings), verified
- **P1-03** (Automatic retry) — ✅ Complete, verified (25 new tests, all passing)

All three components are production-ready within their documented residual risk boundaries.

Next step: Phase 2 (observability, monitoring, operational tooling) or address external evidence gaps for Phase 0 completion.

## Phase 0 checkpoint

Phase 0 remains **partial**, unchanged by these rounds. Repository-local policy, migration, atomic-run-event, and structured-logging work is closed, but P0-02/03/04 stay partial because the same external evidence is still missing:

- Docker Compose runtime (migrate → API/worker, plus a negative start with weak defaults)
- real browser/TLS reverse-proxy behavior for stream/media HttpOnly cookies, logout/expiry, and Range requests
- a real pre-Alembic production snapshot rehearsal (backup → schema review → `alembic stamp 0001_baseline` → upgrade head)
- multi-host/load evidence

Do not promote Phase 0 from “partial” until that external evidence is obtained. Do not report any of it as passed.

## P1-01 checkpoint

P1-01 is **complete within its own scope**, verified green before P1-02 began: `241 passed`, `0 skipped`. Six exit conditions closed with real database side-effect counts and genuinely concurrent sessions. Review findings closed: High (thread deletion hit `ForeignKeyViolation` on `proposed_actions_thread_id_fkey`), Medium (missing full-stack legacy no-capability test), Low (docstring clock). Findings 4–9 deliberately deferred with reasons in `docs/IMPROVEMENT_LOG.md`.

Residual risk: capability consumption commits in its own transaction before `tool.ainvoke`, so the semantics are at-most-once. A crash between the two loses the action; there is no duplicate-execution window.

## P1-02 checkpoint — ✅ COMPLETE

**Independent review completed**: passed with 0 HIGH findings, 2 MEDIUM (both intentional design tradeoffs), 3 LOW (limited impact). Full review report in async session log.

### Part A — complete, and was green on its own

- New table `idempotency_records` with `UNIQUE(scope, idempotency_key)` enforced by PostgreSQL, plus `migrations/versions/0005_idempotency_records.py` chained from `0004_proposed_actions`.
- Alembic head is now `0005_idempotency_records`; offline SQL was 304 lines; `alembic check` clean on a fresh scratch database; `downgrade -1` and re-upgrade both verified.
- Key is **request identity, never payload**: the chat lane uses the consumed `proposed_actions.id` bound through a contextvar; the HTTP lane uses an optional `Idempotency-Key` header, and an absent key means unchanged behavior with no ledger row. `args_hash` is stored only as a tamper cross-check, so the same key with different args fails closed with 422 instead of silently replaying.
- Schedule fan-out is keyed **per entry** (`entry_key(action_id, index)`), not per plan, because a plan may legitimately contain two identical `(content_id, platform, date)` entries and one batch key would write fewer rows than the user approved.
- Concurrency rests on the database: the claim is an INSERT guarded by the unique constraint; the loser catches `IntegrityError`, re-reads under `SELECT FOR UPDATE`, and branches on status (`completed` replays, `in_progress` raises `DuplicateRequestInFlight` → 409, `failed` reclaims the row so a transient error does not burn the key permanently).
- Refine's claim wraps both `save_content` and `update_content`, and is taken before awaiting the provider so a replay skips generation rather than billing twice.
- Wired: content create, content refine, both calendar commit paths. Full suite at that point was `262 passed`, 0 skipped.
- One deliberate quirk: the literal `422` is used instead of `status.HTTP_422_UNPROCESSABLE_ENTITY`, which is deprecated on the installed Starlette 1.6 while `HTTP_422_UNPROCESSABLE_CONTENT` is absent on older versions that `fastapi>=0.115` still permits. A comment explains the split.

### Part B — complete and verified green

Implementation complete:

- **Publication execute-layer idempotency**: `execute_publication` in `src/api/services/publish_service.py` conditionally uses `idempotent_write_async` only when the HTTP request included an `Idempotency-Key` header. The sentinel `_NO_IDEMPOTENCY_KEY` distinguishes "no header" from "None". When no key is provided, both the create and execute layers skip idempotency tracking (`_skip_execute_idempotency` flag in `request_payload`).
- **Publication stable request ID**: `publication_request_id(publication_id)` derives a stable token from the durable `platform_publications.id` row, so job retries, worker restarts, and re-enqueues all present the same `external_request_id` to the platform.
- **Memory mutation idempotency**: `_memory_mutation` in `src/api/services/chat_agent.py` uses `idempotent_write` with scope `SCOPE_MEMORY_MUTATION` and the consumed `proposed_actions.id` as key. The claim is taken before the file write; `in_progress` on SIGKILL means the mutation is lost and the key remains non-reusable (at-most-once semantics).
- **Route header plumbing**: `src/api/routes/publish.py` accepts optional `Idempotency-Key` header and passes it to `create_publication_request`, which stores it in `request_payload` for execute-layer use.

All 13 tests in `test_idempotency_publication_memory.py` pass. Full suite: **275 passed**.

Independent review completed. Known residual risk documented:

- `_call_rest_fallback` in `src/integrations/mcp_client.py:175-213` is an existing duplicate-publish window with no dedup token at the HTTP layer. This is a **known residual risk**: if the MCP server times out after accepting the request but before responding, a retry will publish twice. Consider adding request ID to the REST fallback headers in a future phase.

## Reusable verification environment

Both services were **stopped** at the end of this session. The trees under `/tmp` still exist, so restarting is enough unless `/tmp` has been cleared, in which case they must be re-provisioned from scratch. Loopback-only, trust auth, no Redis password: throwaway local use only, never reuse this config anywhere shared.

```bash
export PGHOME=/tmp/pg16
export PATH=$PGHOME/bin:$PATH
export LD_LIBRARY_PATH=$PGHOME/lib
pg_ctl -D /tmp/pgdata -l /tmp/pg16.log \
  -o "-p 55432 -k /tmp/pgsock -c listen_addresses=127.0.0.1" -w start

export LD_LIBRARY_PATH=/tmp/redis-root/usr/lib/x86_64-linux-gnu
mkdir -p /tmp/redisdata
nohup /tmp/redis-root/usr/bin/redis-server --port 56379 --bind 127.0.0.1 \
  --unixsocket /tmp/redis.sock --dir /tmp/redisdata > /tmp/redis.log 2>&1 &
```

```bash
export TEST_DATABASE_URL='postgresql+psycopg://content_ops:content_ops@127.0.0.1:55432/content_ops_test'
export REDIS_URL='redis://127.0.0.1:56379/0'
```

Stop with `pg_ctl -D /tmp/pgdata -m fast -w stop` and `redis-cli -p 56379 shutdown nosave`. Full teardown is `rm -rf /tmp/pgdata /tmp/pg16 /tmp/pgsock /tmp/redisdata /tmp/redis-root`.

`LD_LIBRARY_PATH` is per-service: PostgreSQL binaries need `/tmp/pg16/lib`, and `redis-cli`/`redis-server` need `/tmp/redis-root/usr/lib/x86_64-linux-gnu`. Exporting the PostgreSQL path and then calling `redis-cli` fails with `liblzf.so.1: cannot open shared object file`.

No scratch databases were left behind; only `content_ops_test` remains, in whatever state the last pytest run left it (the `store` fixture rebuilds it per test, so its contents do not matter).

## P1-03 checkpoint — ✅ COMPLETE

**New migration**: `0006_job_retry_fields.py` adds `max_retries`, `next_retry_at`, `error_type` to the `jobs` table.

**Error classification**: `src/jobs/error_classifier.py` categorizes exceptions as `transient` (retriable) or `permanent` (non-retriable). Transient includes network timeouts, rate limits, 429/502/503/504, temporary service unavailability. Permanent includes configuration errors, validation errors, 4xx (except 429), data integrity violations.

**Exponential backoff**: 30s → 60s → 120s → 240s → 480s (max), configurable via `JOB_RETRY_INITIAL_DELAY_SECONDS` and `JOB_RETRY_MAX_DELAY_SECONDS`.

**Runner logic**: `run_job_async` checks `next_retry_at` at entry and skips early retries. `_handle_job_error` classifies errors, calculates backoff, sets `next_retry_at`, and requeues via `queue.requeue_with_backoff`.

**Queue support**: RQ mode uses `enqueue_in` for true delayed execution (production); BackgroundTasks mode enqueues immediately but relies on entry check to skip early execution (dev/test).

**Test coverage**: 25 new tests in `tests/jobs/test_job_retry.py` covering error classification, backoff calculation, retry scheduling, attempt increment, and full retry flows. All passing.

Full suite: **300 passed** (up from 275).

Known residual risks documented in `docs/IMPROVEMENT_LOG.md`.

## Phase 1 status

✅ **P1-01** (Persistent capability) — Complete  
✅ **P1-02** (Business idempotency) — Complete, independently reviewed  
✅ **P1-03** (Automatic retry) — Complete  

Phase 1 core reliability infrastructure is **finished**. P1-04 (lease-based deduplication), P1-05 (publication job refactor), P1-06 (circuit breaker) remain deferred.

## Resume notes

1. Preserve the current dirty working tree; do not reset, checkout, stash, clean, or commit the workflow changes. `HEAD` must stay `6dee18b`.
2. The suite is **green** at `300 passed`. All P1-01, P1-02, P1-03 implementations are complete and verified.
3. Run one pytest process at a time against the test database: the `store` fixture drops and recreates every table, so parallel runs corrupt each other and produce spurious `IntegrityError`.
4. `alembic check` against `content_ops_test` reports "Target database is not up to date" because pytest builds that database with `create_all`. That is a test artifact, not drift. To check migrations, create a scratch database, run `upgrade head` against it, then `check`, then drop it.
5. Alembic head is now `0006_job_retry_fields`.
6. Phase 2 (observability), Phase 3 (hardening), and final verification have not started.
