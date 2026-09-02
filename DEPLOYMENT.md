# Production Deployment and Concurrency

> Phase 0 security and database rollout details: [`docs/PHASE0_SECURITY_AND_MIGRATIONS.md`](docs/PHASE0_SECURITY_AND_MIGRATIONS.md).

This project supports a production-style topology for higher concurrency:

- FastAPI handles validation, job creation, and lightweight reads.
- PostgreSQL stores content, agent history, calendar data, and job state.
- Redis + RQ run long LLM jobs outside the HTTP request path.
- Frontend flows submit jobs and poll `/api/jobs/{job_id}`.

## Local Services

```bash
docker compose up -d postgres redis
```

Use an **explicit development profile** for a local run. The example passwords are rejected in production:

```bash
APP_ENV=development
SCHEMA_MANAGEMENT=create
DATABASE_URL=postgresql+psycopg://content_ops:content_ops@localhost:5432/content_ops
JOB_QUEUE_MODE=rq
REDIS_URL=redis://:content_ops@localhost:6379/0
JOB_QUEUE_NAME=content_ops
MAX_PROVIDER_INFLIGHT_JOBS=8
```

## API and Worker

Development fallback, no Redis required:

```bash
APP_ENV=development SCHEMA_MANAGEMENT=create JOB_QUEUE_MODE=background python server.py
```

Production API startup is validation-only. Run migrations first and provide all fail-closed settings from `.env.docker.example`:

```bash
alembic upgrade head
APP_ENV=production SCHEMA_MANAGEMENT=validate gunicorn -c gunicorn.conf.py src.api.main:app
```

`gunicorn.conf.py` sets the UvicornWorker class, binds `API_HOST:API_PORT`, and
reads `WEB_CONCURRENCY` (default 3) for the worker count. Because each worker
holds its own DB pool, budget connections as
`WEB_CONCURRENCY * (DB_POOL_SIZE + DB_MAX_OVERFLOW)` for the API plus another
`(DB_POOL_SIZE + DB_MAX_OVERFLOW)` for the RQ worker process — `3 * 30 + 30 = 120`
at the defaults. The compose Postgres raises `max_connections` to 200
(`POSTGRES_MAX_CONNECTIONS`) so that fits; Postgres' own default is only 100.

Worker process:

```bash
python worker.py
```

Scale API workers for lightweight request concurrency. Scale worker processes for LLM throughput, bounded by provider limits and `MAX_PROVIDER_INFLIGHT_JOBS`.

On Windows, `worker.py` automatically uses RQ `SimpleWorker` because the default fork-based worker requires Unix `os.fork()`.

## Full Stack with Docker Compose

```bash
docker compose up -d --build
```

Brings up a one-shot Alembic migration job, frontend (`:8088`), API (`127.0.0.1:8000`, gunicorn + UvicornWorker), worker, PostgreSQL, and Redis. Copy `.env.docker.example` to `.env` and replace every `CHANGE_ME` value first. The API/worker refuse unsafe defaults in the default production profile. Application containers run as a non-root `app` user.

Readiness vs liveness: `GET /api/health/ready` returns 200 only when the database
(and Redis, in `rq` mode) are reachable, 503 otherwise — use it for orchestrator
readiness gates. `GET /api/health` stays a dependency-free liveness check and is
what the compose healthcheck polls.

## Security and Tuning

- **Fail-closed settings**: omitted `APP_ENV` defaults to production for direct application/image entrypoints. Production requires enabled auth, strong independent admin/signing/PostgreSQL/Redis secrets, `DEBUG=false`, `SCHEMA_MANAGEMENT=validate`, and an exact public HTTPS CORS origin. Local compatibility requires explicit `APP_ENV=development`. Defaults exist only so `docker compose up postgres redis` remains useful locally; migrate/API/worker production startup rejects unsafe settings.
- **Migrations**: the one-shot `migrate` service validates production settings before DDL and must complete before API/worker. Existing pre-Alembic databases require backup, schema verification, `alembic stamp 0001_baseline`, then `alembic upgrade head`; never stamp an unverified schema. Startup checks revision plus ORM type/nullability/foreign-key/index/constraint drift.
- **Browser resource auth**: reusable bearer values are header-only. In production, login sets a `HttpOnly; Secure; SameSite=Strict` cookie that is accepted only for pipeline-stream and numeric media-file paths; it never authorizes general REST APIs. Exact-path `access_ticket` query credentials are development/test compatibility only and are rejected in production. The production Nginx edge rejects `access_ticket`/`access_token` query parameters before proxying and logs `$uri` without query-bearing request targets or Referer.
- **TLS proxy trust**: `X-Forwarded-Proto` is ignored unless the immediate peer is in `TRUSTED_PROXY_CIDRS`; direct entrypoints default to no trusted forwarding proxies. Compose limits trust to its private bridge. Keep this range minimal and make the outer TLS proxy overwrite client forwarding headers.
- **Exposed ports**: Postgres (`5432`) and Redis (`6379`) bind to `127.0.0.1`
  only, so they are reachable from the host for debugging but not over the
  network. Drop the `ports` mappings entirely and use
  `docker compose exec postgres psql -U content_ops` if you want them fully internal.
- **API workers**: tune `WEB_CONCURRENCY` (default 3), subject to the
  connection-count rule above.
- **Volume ownership**: the app runs as non-root. An `app_data` volume created by
  an older root-owned image will not be writable — recreate it with
  `docker compose down -v` so the `app` user can write `/app/data`.
