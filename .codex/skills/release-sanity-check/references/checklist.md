# Sanity Checklist

## Stage Commands

1. Backend tests
- `python -m pytest tests -q`

2. Compile safety
- `python -m compileall src tests examples`

3. Frontend build (run in `frontend/`)
- `npm run build`

## Summary Template

- Stage 1: pass/fail
- Stage 2: pass/fail
- Stage 3: pass/fail
- Final: ready / not ready
- Next action: fix list with file hints

## Typical Failure Clusters

- Test regressions: API response shape, dependency overrides, data persistence assertions.
- Compile failures: syntax or import errors in touched Python modules.
- Frontend build failures: TS type mismatch, API type drift, missing imports.