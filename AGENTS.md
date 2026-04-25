# Repository Guidelines

## Project Structure & Module Organization

This is an AI content operations SaaS prototype with a FastAPI backend and Vue 3 frontend.

- `server.py` starts the FastAPI application in `src/api/main.py`.
- `src/api/` contains REST routes, Pydantic schemas, dependencies, and service-layer orchestration.
- `src/api/services/agent_pipeline.py` contains the Strategy / Writer / Editor / Review pipeline.
- `src/api/services/chat_agent.py` contains the persistent tool-calling chat Agent.
- `src/models/` defines request and generated-content data structures.
- `src/llm/` contains the current LiteLLM adapter.
- `src/tools/prompt_templates.py` contains reusable content prompt templates.
- `src/storage/` manages persisted content, calendar events, metrics, Agent threads, and messages.
- `frontend/` contains the Vue 3 + Vite + Element Plus application.
- `examples/seed_demo_data.py` creates repeatable local demo data without external LLM calls.
- `tests/` contains pytest contract tests for the API and configuration behavior.

## Build, Test, and Development Commands

- `pip install -r requirements.txt` installs Python dependencies.
- `cp .env.example .env` creates local configuration; then set the chosen provider API key for live LLM calls.
- `python examples/seed_demo_data.py` seeds local demo data without calling any provider.
- `python server.py` starts the FastAPI backend.
- `cd frontend && npm install` installs frontend dependencies.
- `cd frontend && npm run dev` starts the Vue frontend.
- `cd frontend && npm run build` builds the frontend.
- `python -m pytest tests -q` runs the API/config contract tests.
- `python -m compileall src tests examples` checks Python syntax.

## Coding Style & Naming Conventions

Use standard Python style: 4-space indentation, `snake_case` for functions and variables, `PascalCase` for classes and dataclasses, and uppercase names for enum members and constants. Keep provider routing behind the LiteLLM adapter and shared orchestration under `src/api/services/`. Prefer type hints for new public functions and small dataclasses or enums for structured content concepts.

## Testing Guidelines

Default tests must not require real API calls. Mock provider clients or use fake LLM clients for contract tests. Add focused tests under `tests/` and name new files `test_*.py`.

## Commit & Pull Request Guidelines

Use concise imperative commits such as `Add Agent workflow tests` or `Clean legacy startup paths`. Pull requests should include a short change summary, test commands run, configuration changes, and screenshots for web UI updates.

## Security & Configuration Tips

Do not commit `.env` or real API keys. Use `.env.example` for documented variables only. Keep `data/content_ops.db` out of reviews unless a fixture or migration explicitly requires it.
