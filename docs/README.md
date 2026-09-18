# Documentation Index

Start here. The documents below are maintained; anything in [`archive/`](archive/)
is a frozen record of a past working session and is kept only for provenance —
it may describe code that has since changed, and it is not a source of truth.

## Core

| Document | What it covers |
| --- | --- |
| [../README.md](../README.md) | What the project is, architecture, quick start, API surface. |
| [../README.zh-CN.md](../README.zh-CN.md) | 简体中文版 README。 |
| [../DEPLOYMENT.md](../DEPLOYMENT.md) | Deploying the Compose stack, environment variables, TLS proxy. |
| [../RELEASE_NOTES.md](../RELEASE_NOTES.md) | User-visible changes per release. |

## Operations

| Document | What it covers |
| --- | --- |
| [PRODUCTION_OPERATIONS.md](PRODUCTION_OPERATIONS.md) | Monitoring, metrics, maintenance tasks, troubleshooting, tuning. |
| [PHASE0_SECURITY_AND_MIGRATIONS.md](PHASE0_SECURITY_AND_MIGRATIONS.md) | Runtime profiles, fail-closed production, migration operations. |
| [PHASE0_VERIFICATION_PLAN.md](PHASE0_VERIFICATION_PLAN.md) | The verification plan those production guarantees are held to. |
| [BROWSER_VERIFICATION.md](BROWSER_VERIFICATION.md) | Reproducing the real-browser / TLS end-to-end verification run. |
| [USER_WORKSPACES_RELEASE.md](USER_WORKSPACES_RELEASE.md) | The breaking account/workspace change: migration steps and rollout. |

## Development

| Document | What it covers |
| --- | --- |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | Local setup, the gates CI enforces, and how to run them. |
| [IMPROVEMENT_LOG.md](IMPROVEMENT_LOG.md) | Engineering log: defects found during verification and how they were fixed. |
| [SKILLS_GUIDE.md](SKILLS_GUIDE.md) | Notes on the agent skill surfaces used during development. |
| [evidence/](evidence/) | Machine-readable validation artifacts. |

## Archive

[`archive/`](archive/) holds session hand-off notes, implementation summaries,
and Phase 0 external evidence as of the date they were written. Useful when
tracing *why* a decision was made; never the current state of the code.
