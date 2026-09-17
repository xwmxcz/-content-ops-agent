# Contributing

## Setup

```bash
python -m venv .venv && . .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
make install                                    # backend dev deps + npm ci
pre-commit install                              # optional but recommended
```

`make install` reads `requirements.txt` (intent) via `requirements-dev.txt`; the
resolved, cross-platform pin set is `requirements.lock`, which is what Docker and
CI actually install. Change a dependency by editing `requirements.txt` and running
`make lock` — never by editing `requirements.lock` by hand.

## Before you push

```bash
make check
```

That runs everything CI runs: `ruff check`, `ruff format --check`, `mypy`, the
full backend suite against PostgreSQL, and the frontend typecheck plus tests. The
`Makefile` is deliberately the same set of commands as
[`.github/workflows/ci.yml`](.github/workflows/ci.yml) so the two cannot drift.

If you only touched Python and want a fast loop:

```bash
make test           # unit tests; database-backed tests skip
make lint && make typecheck
```

Then, before pushing, run the real thing once:

```bash
make db-up          # throwaway PostgreSQL on :55432
make test-db        # full suite, silent database skips forbidden
```

## Testing expectations

- **A database-backed test must actually run.** Without `TEST_DATABASE_URL`
  roughly half the suite skips; `make test-db` sets `REQUIRE_TEST_DATABASE=1`
  to make that a hard failure. Do not "fix" a red build by unsetting it.
- **Use a disposable database.** The `store` fixture drops and recreates every
  table around each test.
- **Prefer behaviour over the HTTP layer** when the logic is reachable directly.
  A test that exercises a service or a pure function is cheaper and sharper than
  one that goes through FastAPI.
- **New dependencies need a lock update**: `make lock`, and commit both files.

## Type checking

`mypy` covers `src/`. Fifteen legacy modules that predate type checking are listed
in `[tool.mypy.overrides]` in `pyproject.toml`, where only `assignment`, `misc`
and `valid-type` are waived — the noise produced by legacy SQLAlchemy `Column`
declarations and duck-typed request payloads. Every other check stays on for those
files too, and that is deliberate: it is how a real `None`-dereference and a
reused request variable were found in the job runner.

If you fix one of those modules, delete its line from the override list. That
list should only ever shrink.

## Lint exceptions

`ruff` selects a fairly opinionated rule set. Where a rule genuinely does not
apply, add a **narrow** `# noqa: CODE -- reason`, and say why in the comment.
The `BLE001` (blind `except Exception`) markers are the precedent: each one names
the boundary it protects and why degrading is correct there.

## Architecture notes

Before changing the agent surfaces, read the "Agent Surfaces" section of the
[README](README.md). The split between the Studio pipeline (read/search tools
only, no side effects) and the Chat Agent (write tools, confirmation required) is
a deliberate safety boundary, not an accident of layout — see
`src/api/services/tool_policy.py`.

## Docs

Maintained documents live in `docs/`; see the [index](docs/README.md). Anything
in `docs/archive/` is a frozen session record kept for provenance. Do not update
archived files, and do not treat them as current.

## Commits

Conventional-commit style prefixes (`feat:`, `fix:`, `chore:`, `docs:`, `ci:`)
matching the existing history. Use `!` or a `BREAKING CHANGE:` trailer when you
change an API contract or a migration in a way existing deployments must act on —
the workspace change (`feat(accounts)!`) is the model to follow, including a
matching entry in `RELEASE_NOTES.md` and a migration note in `docs/`.
