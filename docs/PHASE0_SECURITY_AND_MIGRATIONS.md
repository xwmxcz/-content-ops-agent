# Phase 0 Security and Migration Operations

## Runtime profiles and fail-closed production

`APP_ENV` must be one of `development`, `test`, or `production`. If it is omitted, the application and Docker image default to `production`; local compatibility therefore requires an explicit profile.

- `development` / `test`: auth may be disabled. `SCHEMA_MANAGEMENT=create` is allowed only as a compatibility path for a **fresh local database**.
- `production`: startup requires `SCHEMA_MANAGEMENT=validate`, enabled auth, a 12+ character non-example admin password, a 32+ character non-example signing secret, non-example PostgreSQL/Redis passwords, `DEBUG=false`, and explicit HTTPS non-local CORS origins.

The Compose migration job validates the production profile before running DDL; API and worker validate again before accepting work. In production API/worker do not run DDL and verify PostgreSQL at Alembic head with schema-drift checks. Compose defaults intentionally contain unusable/weak placeholders, so an unconfigured production deployment fails closed. Frontend and API host ports bind to loopback. API middleware accepts `X-Forwarded-Proto: https` only when the immediate peer belongs to explicit `TRUSTED_PROXY_CIDRS`; the default is empty for direct entrypoints, while Compose sets its private bridge range. The outer TLS proxy must overwrite forwarding headers, and non-health plain HTTP receives `426`.

Generate independent credentials, for example:

```bash
openssl rand -base64 24   # AUTH_PASSWORD / database / Redis (use separate values)
openssl rand -hex 32      # AUTH_SECRET_KEY
```

Do not use values containing `CHANGE_ME`, `replace-with`, `example`, or `password`; production validation rejects example-like values.

## Browser stream authentication migration

Reusable bearer tokens are accepted only in the `Authorization` header. `?access_token=...` is rejected.

Native `EventSource`, `<img>`, and `<video>` cannot attach that header. Login therefore also sets a `HttpOnly; SameSite=Strict` resource-session cookie (`Secure` in production), scoped to `/api`. The authentication middleware accepts that cookie only for narrow read-only pipeline-stream and numeric media-file paths; it never authorizes general REST APIs or writes. The frontend sends credentials without placing bearer or ticket material in URLs.

The legacy exact-path `access_ticket` helper remains development/test compatibility only. Production returns `410` from its issuance endpoint and rejects `access_ticket` query credentials. The production Nginx edge rejects both `access_ticket` and `access_token` query parameters before proxying. Its sanitized access format uses `$uri`, not `$request`/`$request_uri`, and omits Referer, so query credentials are not copied into access logs. Stateless development tickets remain replayable on the same path until expiry when the backend is run directly outside the production Nginx image. Login rate limiting/lockout and a general browser cookie + CSRF migration are not claimed by this Phase 0 change; normal mutating REST calls continue to use the Authorization header.

## Server-side Chat tool policy

`src/api/services/tool_policy.py` is the authoritative registry. Every Chat tool is explicitly marked `read_only` or `side_effect`. Side effects currently include:

- `create_content`
- `refine_content`
- `add_to_calendar`
- `commit_publishing_schedule`
- `memory_add`, `memory_replace`, `memory_remove`

Immediately before invocation, the executor requires the tool to match the server-recognized intent. Every non-schedule write first becomes a `proposed` tool event containing the exact tool name and arguments and is persisted in the assistant message without invoking the tool. A later standalone affirmative message may authorize only that exact persisted tool/argument pair. `action_confirm` and `schedule_commit` are server-only intents: classifier-provided values are always downgraded, while the deterministic rule path requires the current raw message to match the whole-message affirmative grammar and the preceding persisted proposal. The recognizer binds a deep-copied exact tool/argument call into request-local Pydantic `PrivateAttr` evidence; classifier JSON, persisted/public slots, clients, and later slot mutation cannot change it. The executor authorizes only against this private evidence. Words such as “now” are never authorization, negative/embedded phrases such as “don't do it” or quoted web text are not confirmations, and a model cannot substitute another topic, content ID, memory operation, or argument. Schedule commits likewise require an exact canonical match to the complete proposal persisted in the preceding assistant turn; schedule proposal output is not truncated at the generic 1200-character preview limit.

Model text, memory, web/tool results, and a model's claim that confirmation occurred do not grant permission. Memory Curator output is proposal-only and thread deletion never invokes it, so transcript prompt injection cannot directly mutate `MEMORY.md`/`USER.md`.

This Phase 0 gate intentionally fails closed, but it is not the Phase 1 persistent one-time capability design. Durable action IDs, atomic capability consumption, and cross-request replay protection remain deferred.

## Alembic rollout

### Fresh database

```bash
export DATABASE_URL='postgresql+psycopg://...'
alembic upgrade head
alembic current
```

Compose runs a one-shot `migrate` service before API and worker startup.

### Existing pre-Alembic database

Do not run `upgrade head` directly: revision `0001_baseline` creates the old schema and will collide with existing tables.

1. Stop API and workers and take a tested PostgreSQL backup.
2. Compare the live table set with ORM metadata and the `0001_baseline` revision. Do not stamp a database missing baseline tables; take a schema-only dump for review.
3. Mark the verified pre-Alembic schema as the baseline:

   ```bash
   alembic stamp 0001_baseline
   ```

4. Upgrade through the atomic-event and legacy-normalization revisions:

   ```bash
   alembic upgrade head
   ```

5. Start API/worker with `APP_ENV=production` and `SCHEMA_MANAGEMENT=validate`.

`0002_atomic_run_events` deterministically renumbers each run's existing events by `(seq, id)`, initializes `agent_runs.next_event_seq`, and adds `UNIQUE(run_id, seq)`. `0003_legacy_normalize` idempotently restores columns formerly added by runtime DDL plus indexes that `create_all()` could not add to existing tables. Validation-only startup compares the head revision, complete ORM table/column names, critical indexes/constraints, and Alembic metadata differences including column type/nullability and foreign keys. Migration tests also run `alembic check`. A manually stamped but drifted database fails startup. Schedule a maintenance window: clients holding an old `Last-Event-ID` should reconnect from zero after migration.

### Migration verification

Use only a disposable PostgreSQL database: migration and integration tests drop tables.

```bash
export TEST_DATABASE_URL='postgresql+psycopg://user:password@localhost:5432/content_ops_test'
python -m pytest tests/test_migrations.py tests/test_run_event_atomicity.py -q
python -m pytest tests -q
```

The migration suite covers empty-database upgrade/downgrade, simulated pre-Alembic adoption, metadata drift via `alembic check`, startup drift rejection, concurrent event allocation, terminal-state races, and cancellation versus final-content persistence.

## Atomic run terminal semantics

`ContentStore.append_run_event()` locks the owning `agent_runs` row, verifies status is still `running`, consumes `next_event_seq`, and inserts the event in the same transaction. Once a terminal transition wins, later token/tool/step events are discarded, so the terminal event remains the durable end of the stream. `transition_run_and_append_event()` compare-and-sets the expected state and appends its state event atomically. Successful completion uses `complete_run_with_content()`, which holds the same run-row lock while inserting optional final content, setting `saved_content_id`/run totals, moving to completed, and appending `run_complete`. A cancellation that wins first therefore leaves no `agent_final` content; a completion that wins first cannot subsequently be cancelled. Enqueue and worker failures use the same terminal CAS semantics.

Per-token events currently contend on one run row. Correctness is the Phase 0 priority; token batching and notification-based SSE wakeups remain Phase 2 work.

## Structured logs

API request completion/failure, job lifecycle, pipeline completion/fallback, and policy denials emit one-line JSON logs. Correlation fields include request/job/run/thread IDs and provider/model where available. Request bodies, prompts, tool output, bearer values, resource tickets, connection URLs, and raw exception text are intentionally excluded.
