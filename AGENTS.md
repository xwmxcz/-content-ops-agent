# Repository Guidelines

## Project Structure & Module Organization

This is a Python content operations agent with CLI and Streamlit interfaces.

- `src/main.py` contains the interactive CLI entry point used by `run.py`.
- `src/models/` defines request and generated-content data structures.
- `src/llm/` contains provider clients and the LLM factory for Claude, SiliconFlow, DeepSeek, and Moonshot.
- `src/tools/` holds content generation, prompt templates, calendar, and content helper tools.
- `src/graph/` contains the LangGraph workflow and state definitions.
- `src/storage/` manages persisted content, backed by `data/content_ops.db`.
- `src/web/` contains the Streamlit app and page modules.
- `examples/` contains runnable demos. Root-level `test_setup.py` and `test_api.py` are smoke tests.

## Build, Test, and Development Commands

- `pip install -r requirements.txt` installs runtime dependencies.
- `cp .env.example .env` creates local configuration; then set the chosen provider API key.
- `python run.py` starts the CLI agent.
- `streamlit run src/web/app.py` starts the web UI. On Windows, `run_web.bat` runs the same app through the `only` conda environment.
- `python examples/quick_start.py` runs a basic usage example.
- `python examples/multi_api_demo.py` exercises multiple LLM providers.
- `python test_setup.py` checks imports, config, models, and generator initialization.
- `python test_api.py` tests SiliconFlow connectivity and requires a valid API key.

## Coding Style & Naming Conventions

Use standard Python style: 4-space indentation, `snake_case` for functions and variables, `PascalCase` for classes and dataclasses, and uppercase names for enum members and constants. Keep provider-specific logic isolated under `src/llm/` and shared orchestration in `src/graph/`. Prefer type hints for new public functions and small dataclasses or enums for structured content concepts.

## Testing Guidelines

Current tests are script-based smoke checks rather than a pytest suite. Add focused tests near the repository root or introduce a `tests/` package if adding broader coverage. Name new test files `test_*.py`. Avoid real API calls in default tests unless clearly documented; mock provider clients or gate live calls behind environment variables.

## Commit & Pull Request Guidelines

No local Git history is available in this workspace, so use concise imperative commits such as `Add Streamlit history page` or `Fix SiliconFlow timeout handling`. Pull requests should include a short change summary, test commands run, configuration changes, and screenshots for web UI updates.

## Security & Configuration Tips

Do not commit `.env` or real API keys. Use `.env.example` for documented variables only. Keep `data/content_ops.db` out of reviews unless a fixture or migration explicitly requires it.
