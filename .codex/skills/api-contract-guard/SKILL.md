---
name: api-contract-guard
description: Guard API contracts for the content-ops-agent FastAPI plus Vue project. Use when Codex changes backend routes, schemas, services, storage, models, jobs, config, or frontend API clients and must prevent response-shape regressions. Trigger for edits under src/api/**, src/storage/**, src/models/**, src/jobs/**, src/utils/config.py, frontend/src/api/**, and tests/test_api_contract.py. Select minimal checks first, then expand to full gates before final delivery.
---

# Api Contract Guard

Protect API and data contracts with a minimal-first verification workflow.

## Follow This Workflow

1. Collect changed files from git diff, task scope, or user-provided paths.
2. Classify risk by touched modules.
3. Run the smallest valid checks first.
4. Expand to broader checks when contract risk is medium or high.
5. Report exactly what was verified and what remains unverified.

## Classify Contract Risk

Treat these paths as contract-sensitive:

- `src/api/routes/**`
- `src/api/schemas/**`
- `src/api/services/**`
- `src/storage/**`
- `src/models/**`
- `src/jobs/**`
- `src/utils/config.py`
- `frontend/src/api/**`

Escalate to full backend contract validation when status codes, response fields, enum values, pagination, or persistence behavior may change.

## Select Commands Quickly

Run the helper script to get recommended checks:

```powershell
python .codex/skills/api-contract-guard/scripts/contract_guard.py --changed <file1> <file2>
```

Execute recommended commands automatically:

```powershell
python .codex/skills/api-contract-guard/scripts/contract_guard.py --changed <file1> <file2> --run
```

If no changed file list is available, run broad contract checks.

## Enforce Verification Order

Run checks in this order:

1. Focused contract tests for touched modules.
2. `tests/test_api_contract.py` when API/storage/schema/service behavior may change.
3. `python -m compileall src tests examples` for backend syntax safety.
4. `npm run build` in `frontend/` when frontend API clients or API response usage changes.

Use `references/test-matrix.md` for path-to-command mapping.

## Report Results

Always include:

- Changed files considered.
- Commands executed.
- Pass or fail per command.
- Whether full contract gate was executed.
- Residual risk if any command was skipped.