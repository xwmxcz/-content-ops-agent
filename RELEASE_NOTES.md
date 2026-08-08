# Release Notes

## Highlights

- **Dynamic Studio pipeline** — plan-then-execute content workflow where a planner LLM emits a 3–6 step plan drawn from researcher, strategist, writer, editor, reviewer, and fact-checker sub-agents, with every transition streamed over SSE. Falls back to the canonical 4-step pipeline on any planner failure.
- **Persistent Chat Agent** — LangChain tool-calling assistant with thread history, content/planning/memory tools, and session search. Write tools require confirmation before side-effecting actions.
- **Hermes-style long-term memory** — four-layer file memory (`MEMORY.md` / `USER.md` with hard char budgets, frozen per-session snapshots, a memory curator for deleted threads, and a context compressor for long threads). Replaces the earlier vector-backed store.
- **Multi-provider LLM routing** — Claude, SiliconFlow, DeepSeek, Moonshot, and NewAPI via a single LiteLLM path, with provider-prefix rewriting and OpenAI-compatible base URLs.
- **Multi-provider web research** — Serper, Tavily, Brave, SearXNG, DuckDuckGo, and Bing fallback, exposed to research sub-agents as read-only tools.
- **Two job-queue modes** — in-process FastAPI `BackgroundTasks` or Redis + RQ workers on top of PostgreSQL, switched entirely by env vars.
- **Single-admin auth gate** — optional login gate (`AUTH_ENABLED`) protecting the API and frontend.
- **One-command Docker stack** — frontend, API, worker, PostgreSQL, and Redis via Compose.

## Frontend

- Vue 3 + Element Plus + Pinia workspace covering Studio, Refine, Chat, Content Library, Calendar (60-day queue), Stats, and a Memory editor with live char budgets.
- Studio/Refine submit jobs and poll `GET /api/jobs/{job_id}`; the dynamic pipeline surfaces step progress over SSE.

## Documentation

- `README.md` and `README.zh-CN.md` describe the current architecture, agent surfaces, memory system, and both startup flows.
- `DEPLOYMENT.md` covers Docker and host-based deployment notes.
- `.env.example`, `.env.postgres-rq`, `.env.docker.example`, and `frontend/.env.example` document all runtime configuration.

## Verification

- `python -m pytest tests -q` — 133 passing on a clean checkout.
- `python -m compileall src tests examples`
- `cd frontend && npm run build`

## Notes

- Use `JOB_QUEUE_MODE=background` (the default) for local development and demo runs; no Redis or `python worker.py` needed.
- Use `.env.postgres-rq` plus `docker compose up -d postgres redis` for higher-concurrency runs.
- The Xiaohongshu publishing path is a local MCP-backed demonstration and should be hardened before production use.

## Project Boundary

This is a demo-ready prototype, not a hardened multi-tenant SaaS. Team accounts, RBAC, billing, tenant isolation, and managed cloud deployment are intentionally out of scope.
