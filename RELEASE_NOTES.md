# Release Notes

## Highlights

- Added job-backed workflows for content generation, agent runs, refinement, title generation, and SEO analysis.
- Added two runtime modes: local SQLite with FastAPI background tasks, and PostgreSQL + Redis with RQ workers.
- Added `worker.py`, `docker-compose.yml`, `DEPLOYMENT.md`, and ready-to-use `.env.sqlite` / `.env.postgres-rq` templates.
- Updated the frontend Studio, Refine, and Chat pages to use the new job APIs.
- Fixed model selection state sync so the Studio header and page-level summaries reflect the selected provider/model correctly.
- Expanded persistence to track job state in the database.

## Documentation

- Refreshed `README.md` and `README.zh-CN.md` to match the current architecture and startup flows.
- Added screenshot assets for the Studio, Refine, and Chat workspaces.
- Added frontend proxy configuration reference via `frontend/.env.example`.

## Verification

- `conda run -n only python -m pytest tests -q`
- `conda run -n only python -m compileall src tests examples`
- `cd frontend && npm run build`

## Notes

- Use `.env.sqlite` for local development and demo runs.
- Use `.env.postgres-rq` plus `docker compose up -d postgres redis` for higher-concurrency runs.
- In SQLite mode, do not start `python worker.py`.
