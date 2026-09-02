# AI Content Ops Agent

[English](README.md) | [简体中文](README.zh-CN.md)

![Python](https://img.shields.io/badge/Python-3.10%2B-2563eb)
![FastAPI](https://img.shields.io/badge/FastAPI-API-0f766e)
![Vue](https://img.shields.io/badge/Vue_3-Frontend-42b883)
![Docker](https://img.shields.io/badge/Docker-Compose-2563eb)
![Tests](https://img.shields.io/badge/tests-PostgreSQL%20integration-0f7a4f)

AI Content Ops Agent is a full-stack content operations prototype built around
LLM agents, durable content workflows, and a practical Vue workspace. It combines
FastAPI, Vue 3, LiteLLM, LangChain tool calling, SQLAlchemy storage, Docker
deployment, and a single-admin auth gate into a demo-ready product surface.

The repository is designed as an AI full-stack engineering portfolio project. It
shows product thinking, API contracts, agent orchestration, background jobs,
frontend workflows, and deployment hygiene without claiming to be a hardened
multi-tenant SaaS.

## What It Does

| Area | Capability |
| --- | --- |
| Studio | Dynamic plan-then-execute content pipeline with researcher, strategist, writer, editor, reviewer, and fact-checker sub-agents. |
| Chat Agent | Persistent tool-calling assistant with thread history, content tools, planning tools, memory tools, and session search. |
| Content Library | Saved drafts, refined variants, media assets, local publication records, and searchable history. |
| Refinement | Rewrite or improve saved content while preserving source lineage. |
| Calendar | 60-day publishing queue with day-level agenda and platform summaries. |
| Stats | Polished analytics page for type/status distribution and content structure readouts. |
| Memory | Hermes-style file memory using `MEMORY.md` and `USER.md`, plus context compression and curator support. |
| Docker | One Compose stack for frontend, API, worker, PostgreSQL, and Redis. |

## Architecture

```mermaid
graph LR
  UI[Vue 3 + Vite + Element Plus] --> API[FastAPI REST API]
  API --> Content[Content Services]
  API --> Agent[Agent Services]
  API --> Jobs[Job API]
  Content --> LLM[LiteLLM Provider Router]
  Agent --> LLM
  Agent --> Tools[LangChain Tool Calling]
  Agent --> Memory[File Memory + Context Compressor]
  Memory --> Files[(MEMORY.md / USER.md)]
  Jobs --> Queue[BackgroundTasks or RQ]
  Queue --> DB[(PostgreSQL)]
  Queue --> Redis[(Redis for RQ mode)]
```

Key implementation paths:

| Path | Purpose |
| --- | --- |
| `frontend/` | Vue 3 app, Element Plus UI, model/content clients, polling and SSE flows. |
| `src/api/` | FastAPI routes, schemas, services, dependencies, and auth middleware. |
| `src/api/services/dynamic_pipeline.py` | Studio plan-then-execute pipeline with SSE event persistence. |
| `src/api/services/chat_agent.py` | Persistent tool-calling Chat Agent and long-term memory integration. |
| `src/api/services/sub_agents.py` | Researcher, fact-checker, writer, editor, reviewer, and strategy sub-agents. |
| `src/tools/web_search.py` | Multi-provider search: Serper, Tavily, Brave, SearXNG, DuckDuckGo, and Bing fallback. |
| `src/jobs/` | Queue adapter plus shared runner for BackgroundTasks and RQ. |
| `src/storage/content_store.py` | SQLAlchemy models and CRUD for contents, jobs, runs, events, media, calendar, and messages. |
| `tests/` | Contract and behavior tests for API, jobs, agents, auth, search, memory, media, and storage. |

## Agent Surfaces

This project intentionally has two different agent surfaces:

| Surface | Endpoint | Tool Access | Use Case |
| --- | --- | --- | --- |
| Dynamic Studio Pipeline | `/api/agent/runs` | Researcher and fact-checker get read/search tools only. | Produce structured content through a controlled multi-step workflow. |
| Chat Agent | `/api/agent/chat` | Full content-ops toolset with safety rules for write tools. | Conversational operations, planning, refinement, scheduling, and memory updates. |

The separation is deliberate. Pipeline steps should not freely mutate content or
calendar state. Chat can use write tools, but the prompt requires confirmation
before side-effecting actions unless the user explicitly asked for the action.

## Quick Start With Docker

Use Docker when you want the whole stack running in one command. Docker mode is
the recommended path for trying the full product because it starts the frontend,
API, worker, PostgreSQL, and Redis together.

1. Create your local `.env` file:

```powershell
# Windows PowerShell
Copy-Item .env.docker.example .env
```

```bash
# macOS / Linux
cp .env.docker.example .env
```

2. Edit `.env` and fill at least one LLM provider key:

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_deepseek_key_here
```

Replace every `CHANGE_ME` credential in `.env.docker.example`; Docker uses the fail-closed production profile. Auth, strong independent admin/signing/PostgreSQL/Redis secrets, migration validation, and an explicit HTTPS public origin are required. Stable web-search keys remain optional.

```env
AUTH_ENABLED=true
AUTH_PASSWORD=<random 12+ characters>
AUTH_SECRET_KEY=<random 32+ characters>
POSTGRES_PASSWORD=<independent random value>
REDIS_PASSWORD=<independent random value>
CORS_ORIGINS=https://content.example.com
```

Put TLS in front of the frontend before exposing it. See [Phase 0 security and migration operations](docs/PHASE0_SECURITY_AND_MIGRATIONS.md).

3. Start the full stack:

```bash
docker compose up -d --build
```

4. Check service status:

```bash
docker compose ps
```

5. Open:

- Frontend: `http://localhost:8088`
- API: `http://localhost:8000`

Docker mode starts:

| Service | Role |
| --- | --- |
| `frontend` | Nginx serving the built Vue app and proxying `/api` to the API service. |
| `migrate` | One-shot Alembic upgrade; API/worker wait for successful completion. |
| `api` | FastAPI application; production startup validates config and schema revision. |
| `worker` | RQ worker for long-running jobs; validates schema revision without running DDL. |
| `postgres` | PostgreSQL 16 database. |
| `redis` | Redis for RQ. |

Useful commands:

```bash
docker compose ps
docker compose logs -f api
docker compose logs -f worker
docker compose down
```

After editing `.env`, recreate the affected containers so they read the new
environment values:

```bash
docker compose up -d --force-recreate api worker
```

If frontend or Nginx config changed, rebuild the frontend too:

```bash
docker compose up -d --build frontend
```

## Required Configuration

Copy one env template to `.env`, then fill in the keys you need.

| Use Case | Required Settings |
| --- | --- |
| Live LLM calls | Set at least one provider key, for example `DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`, `SILICONFLOW_API_KEY`, `MOONSHOT_API_KEY`, or `NEWAPI_API_KEY`. |
| Stable web research | Set one of `SERPER_API_KEY`, `TAVILY_API_KEY`, or `BRAVE_SEARCH_API_KEY`. Without a key, the app falls back to keyless HTML search that may be blocked. |
| Production security | Auth enabled; strong independent admin/signing/PostgreSQL/Redis secrets; `SCHEMA_MANAGEMENT=validate`; exact HTTPS `CORS_ORIGINS`. Unsafe defaults fail startup. |
| Xiaohongshu publishing demo | Keep or adjust `XHS_MCP_URL` to point at your local MCP server. |

Docker reads `.env` automatically. For host-based development, copy
`.env.postgres-rq` and adjust `JOB_QUEUE_MODE` (`background` for in-process
jobs, `rq` for a separate worker).

## Local Development

Prerequisites:

- Python 3.10+
- Node.js 18+
- Docker Desktop if you want PostgreSQL, Redis, or the full Compose stack

Install backend dependencies:

```bash
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

python -m pip install -r requirements.txt
```

Install frontend dependencies:

```bash
cd frontend
npm install
cd ..
```

### Database

PostgreSQL is required (SQLite is no longer supported). Start it with Docker:

```bash
docker compose up -d postgres
```

The default `DATABASE_URL` targets this instance. Host development must explicitly set `APP_ENV=development` and `SCHEMA_MANAGEMENT=create` via `.env.example` or the environment. Omitting `APP_ENV` now selects fail-closed production; production must use Alembic and `SCHEMA_MANAGEMENT=validate`.

### Default Mode: In-Process Jobs

The simplest host-based path. Jobs run inside the API process through FastAPI
`BackgroundTasks`, so no Redis or worker is needed. This is the default
`JOB_QUEUE_MODE=background`.

Start the backend:

```bash
python server.py
```

Start the frontend in another terminal:

```bash
cd frontend
npm run dev
```

### RQ Worker Mode

Use this when you want the API process and long-running jobs separated.

```bash
# Windows PowerShell
Copy-Item .env.postgres-rq .env

# macOS / Linux
cp .env.postgres-rq .env
```

Start infrastructure:

```bash
docker compose up -d postgres redis
```

Start the API:

```bash
python server.py
```

Start the worker in another terminal:

```bash
python worker.py
```

Start the frontend:

```bash
cd frontend
npm run dev
```

On Windows, `worker.py` automatically uses RQ `SimpleWorker` because the
default fork-based RQ worker requires Unix `os.fork()`.

## Long-Term Memory

The Chat Agent includes a four-layer memory system inspired by the Hermes
agent-curated memory pattern.

| Layer | Location | Behavior |
| ---: | --- | --- |
| 1 | `data/memory/MEMORY.md` and `data/memory/USER.md` | Small markdown files with hard char limits. `MEMORY.md` stores project and tool notes; `USER.md` stores user preferences. |
| 2 | Chat Agent prompt | Files are loaded once at the start of a thread and frozen for that session. Writes take effect in the next session. |
| 3 | `src/agent/memory_curator.py` | Deleted threads can trigger a curator pass that proposes add, replace, or remove operations. |
| 4 | `src/agent/context_compressor.py` | Long threads can be compressed into structured checkpoints while preserving tool-call/result pairs. |

Main env vars:

```env
MEMORY_ENABLED=true
MEMORY_DIR=data/memory
MEMORY_MD_LIMIT=2200
USER_MD_LIMIT=1375
CONTEXT_COMPRESS_ENABLED=true
CONTEXT_COMPRESS_TRIGGER_MESSAGES=30
MEMORY_CURATOR_ENABLED=true
```

The frontend Memory page directly edits `MEMORY.md` and `USER.md`, shows char
budgets, and can refresh frozen snapshots.

## Verification

Backend (the test fixture drops/recreates tables, so use a disposable PostgreSQL database only):

```bash
export TEST_DATABASE_URL='postgresql+psycopg://user:password@localhost:5432/content_ops_test'
python -m pytest tests -q
python -m compileall src tests migrations examples
```

Frontend:

```bash
cd frontend
npm run build
```

Migrations and Docker production validation:

```bash
alembic upgrade head
alembic current
docker compose up -d --build
docker compose ps
```

Existing pre-Alembic databases must be backed up and verified before `alembic stamp 0001_baseline`; see the Phase 0 operations guide.

## Project Boundary

This is a demo-ready prototype, not a fully hardened commercial SaaS.

Included:

- Single-admin login gate
- Local Docker deployment
- PostgreSQL storage
- Redis/RQ worker mode
- Multi-provider LLM routing
- Agent tool calls and tool traces
- File-based memory and session search

Not included:

- Team accounts and RBAC
- Billing
- Multi-tenant isolation
- Production social-account operations
- Managed cloud deployment manifests
- Enterprise audit logging

The Xiaohongshu publishing path is a local MCP-backed workflow demonstration.
It is useful for product and engineering review, but it should be hardened
before being used as a production publishing system.

Additional deployment notes live in [DEPLOYMENT.md](DEPLOYMENT.md).
