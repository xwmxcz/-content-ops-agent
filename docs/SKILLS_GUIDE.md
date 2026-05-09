# Skills Guide

This repository includes three local productivity skills under `.codex/skills`:

- `api-contract-guard`
- `frontend-page-pattern`
- `release-sanity-check`

Use them to standardize API contract safety, frontend page delivery, and pre-release verification.

## Prerequisites

- Recommended Python executable:
  - `F:\miniconda\envs\only\python.exe`
- Frontend build requires `npm` available in shell.

## 1. api-contract-guard

Purpose:

- Choose minimal backend/frontend verification commands based on changed files.
- Optionally run the commands in safe order.

Commands:

```powershell
# Recommend only
& "F:\miniconda\envs\only\python.exe" ".codex\skills\api-contract-guard\scripts\contract_guard.py" --changed src/api/routes/content.py src/api/services/content_service.py

# Recommend + execute
& "F:\miniconda\envs\only\python.exe" ".codex\skills\api-contract-guard\scripts\contract_guard.py" --changed src/api/routes/content.py src/api/services/content_service.py --run
```

## 2. frontend-page-pattern

Purpose:

- Scaffold a Vue page and optional API/store files following current project conventions.

Commands:

```powershell
& "F:\miniconda\envs\only\python.exe" ".codex\skills\frontend-page-pattern\scripts\scaffold_page.py" --name TrendsBoard --route /trends --with-api --with-store
```

What it creates:

- `frontend/src/views/<PageName>.vue`
- optional `frontend/src/api/<module>.ts`
- optional `frontend/src/stores/<module>.ts`

Then add the printed route entry to `frontend/src/router/index.ts`.

## 3. release-sanity-check

Purpose:

- Run a fixed sanity pipeline before handoff.

Default stages:

1. `python -m pytest tests -q`
2. `python -m compileall src tests examples`
3. `cd frontend && npm run build`

Commands:

```powershell
# Full sanity (includes frontend build)
& "F:\miniconda\envs\only\python.exe" ".codex\skills\release-sanity-check\scripts\run_sanity.py"

# Backend-only sanity
& "F:\miniconda\envs\only\python.exe" ".codex\skills\release-sanity-check\scripts\run_sanity.py" --skip-frontend

# Continue after failures to collect all failing stages
& "F:\miniconda\envs\only\python.exe" ".codex\skills\release-sanity-check\scripts\run_sanity.py" --continue-on-error
```

## One-Command Entry

Use `scripts/run-skill.ps1` to call these scripts with one interface.

If your machine blocks local PowerShell scripts by execution policy, call it with:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-skill.ps1 <mode> [options]
```

Examples:

```powershell
# Contract guard (dry run)
.\scripts\run-skill.ps1 contract --changed src/api/routes/content.py src/storage/content_store.py

# Contract guard (execute)
.\scripts\run-skill.ps1 contract --changed src/api/routes/content.py --run

# Frontend scaffold
.\scripts\run-skill.ps1 frontend --name TrendsBoard --route /trends --with-api --with-store

# Release sanity
.\scripts\run-skill.ps1 release
.\scripts\run-skill.ps1 release --skip-frontend
```

Fallback examples with execution-policy bypass:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-skill.ps1 contract -Changed src/api/routes/content.py src/storage/content_store.py
powershell -ExecutionPolicy Bypass -File .\scripts\run-skill.ps1 release -SkipFrontend
```

## Suggested Team Workflow

1. Implement code change.
2. Run `contract` mode with changed files.
3. If frontend page work is needed, generate baseline with `frontend` mode.
4. Before commit/merge, run `release` mode.
