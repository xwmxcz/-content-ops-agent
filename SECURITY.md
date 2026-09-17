# Security Policy

## Reporting a vulnerability

Report suspected vulnerabilities privately — do not open a public issue for
anything exploitable. Use GitHub's **Report a vulnerability** (Security →
Advisories) on this repository, or contact the maintainer directly.

Please include the affected version or commit, a reproduction, and the impact you
believe it has. Expect an initial response within a few days. This is a
portfolio-scale project maintained by one person; please calibrate expectations
accordingly.

## Supported versions

Only the `main` branch is supported. There are no maintained release branches.

## Deployment security model

The project ships a fail-closed production profile, and it is worth understanding
what it does and does not cover before deploying.

**What the application enforces at startup** (see
[`docs/PHASE0_SECURITY_AND_MIGRATIONS.md`](docs/PHASE0_SECURITY_AND_MIGRATIONS.md)):

- `APP_ENV` defaults to `production`; the permissive local settings must be opted
  into explicitly.
- Production refuses to start without a high-entropy `AUTH_SECRET_KEY` (32+
  characters, distinct from the database and Redis credentials), `DEBUG=false`,
  `SCHEMA_MANAGEMENT=validate`, and explicit HTTPS CORS origins.
- Signing, database, and Redis credentials must be distinct; placeholders shipped
  in the Compose defaults intentionally fail validation.
- API and worker never run DDL in production; they verify the PostgreSQL schema is
  at Alembic head and fail closed on drift.
- Passwords are stored as Argon2id hashes. Login is rate-limited and has a
  lockout path.
- Every business record carries a user id, and tenant scoping is applied at the
  query layer; cross-workspace reads are covered by tests in
  `tests/test_account_isolation.py` and `tests/test_tenant_storage.py`.

## Your responsibility

- **TLS termination is yours.** The API expects HTTPS in production and rejects
  plain HTTP with `426`; put a real proxy in front of the frontend.
- **The trusted-proxy range must match your topology.** `TRUSTED_PROXY_CIDRS`
  controls when `X-Forwarded-Proto` is believed. The Compose default is a private
  bridge range, and traffic routed through NAT has been observed to fall inside
  it. Tighten this to your reverse proxy's actual identity before exposing the
  service; the open item is recorded in `docs/archive/WORKFLOW_CHECKPOINT_2026-09-05.md`.
- **Provider API keys are operator-supplied.** A key that can spend money should
  be scoped and budget-limited at the provider, since the application does not
  meter per-user LLM spend.
- **The Xiaohongshu publishing path is a demonstration**, not production
  publishing infrastructure.

## Dependency hygiene

`requirements.lock` is the resolved pin set. Run `make audit` (`pip-audit` and
`npm audit`) after changing dependencies. CI runs the same audit as an advisory
job on every push.
