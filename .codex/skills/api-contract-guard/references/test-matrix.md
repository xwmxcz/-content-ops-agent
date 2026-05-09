# Test Matrix

Use this mapping to select the smallest safe verification set for contract-sensitive changes.

## Path To Test Mapping

- `src/api/routes/**`, `src/api/schemas/**`, `src/api/services/**`
  - `python -m pytest tests/test_api_contract.py -q`
  - `python -m compileall src tests examples`

- `src/storage/**`, `src/models/**`
  - `python -m pytest tests/test_api_contract.py -q`
  - `python -m compileall src tests examples`

- `src/jobs/**`
  - `python -m pytest tests/test_jobs_contract.py -q`
  - `python -m compileall src tests examples`

- `src/utils/config.py`
  - `python -m pytest tests/test_config_contract.py -q`
  - `python -m compileall src tests examples`

- `frontend/src/api/**`
  - `npm run build` (in `frontend/`)
  - Add `tests/test_api_contract.py` if backend response usage changed

## Full Gate Before Merge

Run full gate when there is any uncertainty about contract behavior:

- `python -m pytest tests -q`
- `python -m compileall src tests examples`
- `cd frontend && npm run build`

## Fast Helper

- Dry run:
  - `python .codex/skills/api-contract-guard/scripts/contract_guard.py --changed <files...>`
- Execute:
  - `python .codex/skills/api-contract-guard/scripts/contract_guard.py --changed <files...> --run`