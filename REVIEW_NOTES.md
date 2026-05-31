# Project Review Notes

Date: 2026-05-26

Scope: FastAPI backend, SQLAlchemy storage, background jobs, frontend API contracts, and test coverage.

## Findings

1. Memory CRUD leaked SQLAlchemy sessions.
   - File: `src/storage/content_store.py`
   - `save_memory`, `get_memory`, `search_memories_text`, `touch_memory`, `delete_memory`, `count_memories`, `evict_memories`, and `list_memories` opened sessions without guaranteed close paths.
   - Impact: repeated memory recall/write operations can hold connections longer than necessary, which matters because chat auto-recall can run on every agent message.
   - Status: fixed locally.

2. Media file endpoints trusted persisted file paths too much.
   - File: `src/api/routes/media.py`
   - `GET /api/media/{id}/file` and `DELETE /api/media/{id}` used `asset["file_path"]` directly.
   - Impact: if a bad path is ever persisted through a bug, migration, manual DB edit, or future generated-media integration, API routes could serve or delete a file outside `MEDIA_STORAGE_ROOT`.
   - Status: fixed locally by constraining file access to the configured media root.

3. Local test command in README may fail on this machine when run as `python ...`.
   - Evidence: `where.exe python` resolves `C:\Users\17832\AppData\Local\Microsoft\WindowsApps\python.exe` before `F:\miniconda\python.exe`; `python -c "print('hello')"` returned exit code 1 with no output.
   - Impact: documented commands are correct in a normal Python setup, but this workstation currently needs an explicit interpreter or conda environment.
   - Status: not changed in README yet; use `conda run -n only python ...` or `F:\miniconda\python.exe ...` locally.

4. Chinese text appears garbled in PowerShell output for several files and tests.
   - Files observed: `src/tools/prompt_templates.py`, `tests/test_memory.py`, parts of `tests/test_api_contract.py`
   - Important nuance: `rg` reads some key source lines correctly as UTF-8, so part of this is terminal/output encoding. Still, any genuinely mojibake text in prompt templates or tests reduces maintainability and can silently lower LLM output quality.
   - Status: not fixed in this pass because it needs careful source-encoding verification, not blind rewriting.

## Changes Made

1. Added `finally: session.close()` coverage to memory CRUD methods in `ContentStore`.
2. Added media path normalization and root-boundary checks in `src/api/routes/media.py`.
3. Added an API contract test that proves media file routes do not serve or delete files outside `MEDIA_STORAGE_ROOT`.

## Higher-Value Follow-Ups

1. Add a small migration layer instead of ad hoc `_ensure_legacy_columns`.
   - Current table evolution is embedded in store initialization. Alembic or a lightweight migration runner would make schema changes auditable and safer for existing SQLite/Postgres data.

2. Separate job enqueueing from synchronous API request behavior.
   - BackgroundTasks is convenient, but production SaaS behavior is more predictable with RQ/Redis as the default and explicit worker health checks.

3. Add a media storage abstraction.
   - Local filesystem is fine for a prototype. A small storage interface would make it easier to support S3/R2/OSS later and centralize path safety.

4. Add end-to-end smoke tests for frontend/backend API contracts.
   - Existing backend contract tests are useful. A minimal Playwright or Vitest smoke layer could catch broken frontend assumptions around content, media, publish, and agent run flows.

5. Normalize developer environment commands.
   - Add a short section documenting the recommended conda interpreter on this workstation or fix the Windows Python launcher alias, so `python -m pytest` behaves as README describes.
