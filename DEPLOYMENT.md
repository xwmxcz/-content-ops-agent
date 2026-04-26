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

Production-style API process:

```bash
gunicorn -k uvicorn.workers.UvicornWorker src.api.main:app --workers 4 --bind 0.0.0.0:8000
```

Worker process:

```bash
python worker.py
```

Scale API workers for lightweight request concurrency. Scale worker processes for LLM throughput, bounded by provider limits and `MAX_PROVIDER_INFLIGHT_JOBS`.

On Windows, `worker.py` automatically uses RQ `SimpleWorker` because the default fork-based worker requires Unix `os.fork()`.
