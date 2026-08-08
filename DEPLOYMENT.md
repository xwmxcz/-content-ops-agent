# Production Concurrency Notes

This project now supports a production-style topology for higher concurrency:

- FastAPI handles validation, job creation, and lightweight reads.
- PostgreSQL stores content, agent history, calendar data, and job state.
- Redis + RQ run long LLM jobs outside the HTTP request path.
- Frontend flows submit jobs and poll `/api/jobs/{job_id}`.

## Local Services

```bash
docker compose up -d postgres redis
```

Use these environment values for a local production-like run:

```bash
DATABASE_URL=postgresql+psycopg://content_ops:content_ops@localhost:5432/content_ops
JOB_QUEUE_MODE=rq
REDIS_URL=redis://localhost:6379/0
JOB_QUEUE_NAME=content_ops
MAX_PROVIDER_INFLIGHT_JOBS=8
```

## API and Worker

Development fallback, no Redis required:

```bash
JOB_QUEUE_MODE=background python server.py
```

Production-style API process (matches what the `api` container runs):

```bash
gunicorn -c gunicorn.conf.py src.api.main:app
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

Brings up frontend (`:8088`), api (`:8000`, gunicorn + UvicornWorker), worker,
postgres, and redis. Every service uses `restart: unless-stopped`, and the
application containers run as a non-root `app` user.

Readiness vs liveness: `GET /api/health/ready` returns 200 only when the database
(and Redis, in `rq` mode) are reachable, 503 otherwise — use it for orchestrator
readiness gates. `GET /api/health` stays a dependency-free liveness check and is
what the compose healthcheck polls.

## Security and Tuning

- **Passwords**: `POSTGRES_PASSWORD` and `REDIS_PASSWORD` default to `content_ops`
  for a zero-config local bring-up. Set them in `.env` for any shared or
  internet-facing deployment; compose wires them into `DATABASE_URL` and
  `REDIS_URL` automatically. When running the half-local flow above with custom
  passwords, use the same values in your local connection strings.
- **Exposed ports**: Postgres (`5432`) and Redis (`6379`) bind to `127.0.0.1`
  only, so they are reachable from the host for debugging but not over the
  network. Drop the `ports` mappings entirely and use
  `docker compose exec postgres psql -U content_ops` if you want them fully internal.
- **API workers**: tune `WEB_CONCURRENCY` (default 3), subject to the
  connection-count rule above.
- **Volume ownership**: the app runs as non-root. An `app_data` volume created by
  an older root-owned image will not be writable — recreate it with
  `docker compose down -v` so the `app` user can write `/app/data`.
