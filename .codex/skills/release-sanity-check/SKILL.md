---
name: release-sanity-check
description: Run consistent pre-delivery sanity checks for this content-ops-agent repository and summarize failures with actionable locations. Use when backend, frontend, or integration code changes before commit or handoff. Trigger for any non-trivial change and especially edits in src/**, tests/**, frontend/**, server.py, worker.py, or requirements and package metadata.
---

# Release Sanity Check

Execute a stable verification sequence and produce a concise pass/fail report.

## Run Order

1. Backend tests:
   - `python -m pytest tests -q`
2. Backend compile safety:
   - `python -m compileall src tests examples`
3. Frontend type and bundle gate:
   - In `frontend/`: `npm run build`

If a stage fails, stop by default and report root cause first. Use continue mode only when a complete failure inventory is required.

## Fast Invocation

Use helper script:

```powershell
python .codex/skills/release-sanity-check/scripts/run_sanity.py
```

Options:

- `--continue-on-error`: run all stages and collect all failures.
- `--skip-frontend`: skip frontend build when frontend is intentionally untouched.
- `--python <exe>`: force a specific Python interpreter.

## Reporting Contract

Always report:

- Stage order and executed commands.
- Pass/fail per stage.
- First failing stage and key error line.
- Final status: ready or not ready.

Use `references/checklist.md` for expected output format.