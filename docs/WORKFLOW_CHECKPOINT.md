# Workflow Checkpoint

- Recorded at: `2026-09-04T20:00:00+08:00`
- Workflow: `report_driven_iterative_hardening_continuation`
- Repository HEAD/current base: `5a2236c` (session summary for P1-04/P1-05)
- Status: **Phase 1 P1-01…P1-06 + Phase 2 complete, Phase 0 external evidence still partial**
- Completed phases:
  - `Phase 0` — Recover and Remediate (repository-local scope, partial)
  - `Phase 1` — Reliability and Recovery (P1-01/02/03/04/05/06) — **COMPLETE**
  - `Phase 2` — Observability & Monitoring (P2-01/02/03/04) — **COMPLETE**
- Completed tasks:
  - `P1-01` — Persistent capability (implemented, reviewed, remediated, verified)
  - `P1-02` — Business idempotency (implemented, independently reviewed, verified)
  - `P1-03` — Automatic retry (implemented, verified)
  - `P1-04` — Job lease, heartbeat, reaper & checkpoint recovery (implemented, verified)
  - `P1-05` — Planner structured output with bounded repair (implemented, verified)
  - `P1-06` — Frontend testing + SSE resilience (implemented, verified; Playwright E2E still deferred)
  - `P2-01` — Prometheus metrics (implemented, verified)
  - `P2-02` — Enhanced structured logging (implemented, verified)
  - `P2-03` — Job cleanup mechanism (implemented, verified)
  - `P2-04` — Dashboard query helpers (implemented, verified)
- Git commits:
  - `9c2b951` — Phase 1: P1-01 Persistent capability + P1-02 Business idempotency + P1-03 Automatic retry
  - `97be2f4` — Phase 2: Observability & Monitoring
  - `5e94c4f` — Documentation: Phase 2 checkpoint update
  - `063ace8` — Documentation: Production operations guide
  - `bce7004` — Phase 0: Production configuration validation tests
  - `e4c6c34` — Phase 1 P1-04: Job lease, heartbeat, reaper & checkpoint recovery (current HEAD)
- Working tree: **Clean** (all changes committed)
- Main implementation record: `docs/IMPROVEMENT_LOG.md`

## ⚠️ Read this before resuming

### 最新一轮（2026-09-04，Docker 已安装后）

**Docker 环境**：Engine 29.8.0 / Compose v5.5.1。用户已在 `docker` 组，但既有 shell 的进程凭证无该 gid —— 用 `sg docker -c "..."`，**不需 sudo**。

**全量套件首次在真实 PostgreSQL 上跑通**：`433 passed, 7 skipped`（1659s）。修复前是 `5 failed, 428 passed`。

> 🔴 P1-05 会话声称的 `413 passed` 与它自己列的「5 个 caplog 测试在完整套件中失败」相互矛盾。真实情况：那 5 个失败是**真缺陷**，不是测试隔离瑕疵，已定根因并修复。

### 本轮发现并修复的两个生产缺陷

两个都是**只有真实跑容器/迁移才能发现**的类型，纯代码审查与无容器单测都碰不到。这正是 Phase 0 坚持要外部证据的理由。

**1. `gunicorn.conf.py` 名字碰撞 → api 容器崩溃重启循环（生产完全跑不起来）**

```
Error: Not a string: <src.utils.config.Config object at 0x...>
```

gunicorn 遍历配置文件的模块级名字，凡与自身 119 个设置项同名就当作该设置的值。它恰好有一个叫 `config` 的设置（`-c` 选项），要求字符串。`from src.utils import config` 绑定了这个名字。`python server.py` 开发路径不加载该文件，所以一直没暴露。

修复：`from src.utils import config as app_config`。

**2. `migrations/env.py` 禁用全部 `src.*` logger**

`logging.config.fileConfig` 的 `disable_existing_loggers` **默认为 True**，会把所有未在 `alembic.ini` 声明的 logger 设为 `disabled = True`。任何进程内 alembic 运行后，应用日志静默。在套件里表现为 5 个无关的 caplog 断言仅当 `test_migrations.py` 先跑时失败；在生产则是迁移后静默丢日志。

定位方法：逐文件二分（每个候选文件 + 那 5 个失败测试配对）。我最初假设是 `configure_logging` 的 `root.handlers.clear()` 摧了 caplog handler，但 `test_api_contract + test_plan_schema` 配对 115 passed 推翻了这个假设。

修复：`fileConfig(..., disable_existing_loggers=False)`。

**回归测试**：`tests/test_deployment_config.py`（4 条）。直接调 gunicorn 自己的 `Config.set()` 校验，不复刻其规则。**已做变异验证**：重新植入两个缺陷 → 3 failed（缺陷 1 被 2 条抓住，缺陷 2 被源码断言抓住）。

### Docker Compose 验证已完成（Phase 0 外部证据）

完整记录在 `docs/phase0_external_evidence.md` §2。摘要：

- **否定用例**：`.env.docker.example`（`CHANGE_ME` 占位值）→ 退出码 1，fail-closed，四条弱密钥全部被拒
- **正向用例**：migrate（退出 0，8 步迁移）→ api healthy + worker + frontend；readiness 200 含 `database:ok, redis:ok`；RQ worker 监听 `content_ops`
- **P1-06 SSE keepalive 端到端实证**：40s 得 2 个 `: keepalive` 注释帧，**带 `id:` 的帧 = 0**。后一条是客户端去重赖以成立的不变量
- 补上 `SSE_*` 三个变量到 `docker-compose.yml`（之前未透传，容器只能用代码默认值）

### 镜像源改为国内节点

容器内**无代理**，两处默认源均不可用。做成 build arg：`APT_MIRROR`（USTC）、`PIP_INDEX_URL`（tuna）。

| | 默认源 | 国内节点 |
|---|---|---|
| apt | `deb.debian.org` >650s 未拉完 9.6MB 索引，构建失败 | USTC **8s** 取完全部包 |
| pip | `pypi.org` **0 KB/s**（20s 零字节），构建爬行 22.9 kB/s | tuna **16 MB/s** |

> 🔴 **方法论教训**：我先前在宿主机 shell 测出「上游快 26 倍」并据此选了上游，是错的 —— 该 shell 导出 `http(s)_proxy=127.0.0.1:7890`。代理让上游显快、又把国内镜像拖去海外出口，排名完全反转。凡要代表容器网络的测量，必须先剥离代理。

### ⚠️ 待你决策的安全发现（未修复）

`X-Forwarded-Proto` 信任边界比 compose 注释声明的更宽。受控实验：

```
无 XFP 头              -> 426
XFP: http              -> 426
XFP: https（宿主机）  -> 401   ← 已穿过 HTTPS 强制
收窄 TRUSTED_PROXY_CIDRS 至不含网关后，同一请求 -> 426
```

机制：宿主机经发布端口进来的流量被 SNAT 成桥网关 `172.18.0.1`，落在 `172.16.0.0/12` 内。nginx 的 `geo` 块同样信任该网段（access log 确认 `remote_addr=172.18.0.1`）。

影响：8000/8088 均只绑 `127.0.0.1`，利用前提是已有宿主机本地访问权 —— 不是远程漏洞，而是纵深防御被削弱且与文档意图不符。**未擅自改**：收紧网段会改变生产反代拓扑的前提假设。

### 环境现状（暂停时保留）

容器**故意留着**，恢复时可直接用：

```
cops_test_pg      127.0.0.1:55432   测试库 content_ops_test
cops_test_redis   127.0.0.1:56379
content-ops-agent-{api,frontend,worker,postgres,redis}-1   正向用例栈
```

```bash
export TEST_DATABASE_URL='postgresql+psycopg://content_ops:content_ops@127.0.0.1:55432/content_ops_test'
export REDIS_URL='redis://127.0.0.1:56379/0'
```

清理：`sg docker -c "docker rm -f cops_test_pg cops_test_redis"`，以及 `sg docker -c "docker compose --env-file /tmp/compose_positive.env down -v"`。

`/tmp/compose_positive.env` 含强随机密钥（权限 0600），**故意不在仓库内**以免误提交；`/tmp` 被清后重新生成即可。

### 🔴 恢复后第一件事

全量套件含新增 4 条部署测试的复验（预期 437）**被我中途停止，未完成**。`433 passed` 是加这 4 条**之前**的数字；4 条单独跑通过。恢复后先跑：

```bash
python3 -m pytest tests/ -q    # 预期 437 passed, 7 skipped（约 28 分钟）
```

一次只跑一个 pytest 进程：`store` fixture 会 drop/create 全部表，并行会互相污染并产生假的 `IntegrityError`。

---

### Phase 1 / Phase 2 总体状态

Phase 1（P1-01…P1-06）+ Phase 2 均完成：

- **P1-01** 持久化能力 — ✅ 已独立审查与整改
- **P1-02** 业务幂等 — ✅ 已独立审查（0 HIGH）
- **P1-03** 自动重试 — ✅ 25 条新测试
- **P1-04** 租约与检查点恢复 — ✅ 49 条
- **P1-05** Planner 结构化输出 — ✅ 64 条
- **P1-06** 前端测试 + SSE 弹性 — ✅ 55 条；Playwright E2E 切出未做
- **P2-01…P2-04** 可观测性 — ✅ 全部完成

**Git**：P1-01…P1-06 已提交至 `972625f`。本轮 Docker 修复另行提交。本地领先 origin/main，**未推送**。

The last **full-suite** green was `413 passed, 7 skipped` on a disposable PostgreSQL, recorded in the P1-05 session. That figure was **not re-verified in the P1-06 session**: that environment had no PostgreSQL binary, no Docker, and no `TEST_DATABASE_URL`, so 239 DB-backed tests skipped and only `201 passed, 239 skipped` could be observed. Re-run against a real database before treating the suite as green.

Phase 1 (P1-01…P1-06) + Phase 2 are complete:

- **P1-01** (Persistent capability) — ✅ Complete, independently reviewed, remediated
- **P1-02** (Business idempotency) — ✅ Complete, independently reviewed (passed with 0 HIGH findings), verified
- **P1-03** (Automatic retry) — ✅ Complete, verified (25 new tests, all passing)
- **P1-04** (Job lease & checkpoint recovery) — ✅ Complete, verified (49 new tests, all passing)
- **P1-05** (Planner structured output) — ✅ Complete, verified (64 new tests)
- **P1-06** (Frontend testing + SSE resilience) — ✅ Complete, verified (55 new tests); Playwright E2E deferred
- **P2-01** (Prometheus metrics) — ✅ Complete, verified (12 core metrics + /api/metrics endpoint)
- **P2-02** (Enhanced structured logging) — ✅ Complete, verified (6 key event functions + instrumentation)
- **P2-03** (Job cleanup mechanism) — ✅ Complete, verified (soft delete + dry-run/execute modes)
- **P2-04** (Dashboard query helpers) — ✅ Complete, verified (3 stats query functions)

All components are production-ready within their documented residual risk boundaries.

**Git status**: P1-01…P1-05 committed through `5a2236c`. The P1-06 changes are **uncommitted** in the working tree.

Next step: Playwright E2E and the rest of the Phase 0 external evidence (both need Docker/PostgreSQL), or production deployment preparation.

## Phase 0 checkpoint — 🔄 PARTIAL PROGRESS (2025-01-13)

### Production Configuration Validation ✅ COMPLETE

**New**: Standalone test suite created and verified at `tests/standalone/test_production_validation.py`

**Coverage**: 7/7 tests passing:
- ✅ Weak password rejection (< 12 chars)
- ✅ Weak secret key rejection (< 32 chars)
- ✅ Example-like value rejection ("CHANGE_ME", "password", etc.)
- ✅ DEBUG=true rejection in production
- ✅ HTTP CORS origin rejection (requires HTTPS)
- ✅ Valid configuration acceptance
- ✅ Development mode allows weak config

**Technical design**:
- Standalone script execution (not pytest) to avoid module caching
- Per-test `reload_config()` for isolation
- Strong entropy requirements verified:
  - AUTH_PASSWORD: ≥12 chars, ≥12 unique
  - AUTH_SECRET_KEY: ≥32 chars, ≥12 unique
  - DATABASE_URL password: ≥16 chars, ≥12 unique

**Report**: Full validation results in `docs/phase0_external_evidence.md`

### Docker Compose Validation ✅ DONE (2026-09-04)

Superseded: this section said DEFERRED while Docker was unavailable. Docker was
installed and the validation was really executed. Full record in
`docs/phase0_external_evidence.md` §2; summary at the top of this file.

Closed by that run:

- ✅ Docker Compose runtime (migrate → API/worker/frontend, plus a negative start with weak defaults)
- ✅ Health/readiness endpoints answering for real (`database:ok, redis:ok`)
- ✅ Service-to-service networking (api↔postgres↔redis, nginx→api, in-bridge container→api)

Still missing, and Phase 0 stays **partial** until obtained:

- ❌ Real browser/TLS reverse-proxy behavior for stream/media HttpOnly cookies, logout/expiry, and Range requests — this round used `curl` against loopback, not a browser against an HTTPS endpoint
- ❌ Real pre-Alembic production snapshot rehearsal (backup → schema review → `alembic stamp 0001_baseline` → upgrade head) — this round went 0001→0008 on an empty database
- ❌ Multi-host/load evidence
- ❌ Volume persistence across a restart (this round ended with `down -v`)

Do not report the remaining four as passed.

One security finding from that run is **unfixed and needs your decision**: the
`X-Forwarded-Proto` trust boundary is wider than the compose comment claims. See
the top of this file, or `phase0_external_evidence.md` §2.6.

## P1-01 checkpoint

P1-01 is **complete within its own scope**, verified green before P1-02 began: `241 passed`, `0 skipped`. Six exit conditions closed with real database side-effect counts and genuinely concurrent sessions. Review findings closed: High (thread deletion hit `ForeignKeyViolation` on `proposed_actions_thread_id_fkey`), Medium (missing full-stack legacy no-capability test), Low (docstring clock). Findings 4–9 deliberately deferred with reasons in `docs/IMPROVEMENT_LOG.md`.

Residual risk: capability consumption commits in its own transaction before `tool.ainvoke`, so the semantics are at-most-once. A crash between the two loses the action; there is no duplicate-execution window.

## P1-02 checkpoint — ✅ COMPLETE

**Independent review completed**: passed with 0 HIGH findings, 2 MEDIUM (both intentional design tradeoffs), 3 LOW (limited impact). Full review report in async session log.

### Part A — complete, and was green on its own

- New table `idempotency_records` with `UNIQUE(scope, idempotency_key)` enforced by PostgreSQL, plus `migrations/versions/0005_idempotency_records.py` chained from `0004_proposed_actions`.
- Alembic head is now `0005_idempotency_records`; offline SQL was 304 lines; `alembic check` clean on a fresh scratch database; `downgrade -1` and re-upgrade both verified.
- Key is **request identity, never payload**: the chat lane uses the consumed `proposed_actions.id` bound through a contextvar; the HTTP lane uses an optional `Idempotency-Key` header, and an absent key means unchanged behavior with no ledger row. `args_hash` is stored only as a tamper cross-check, so the same key with different args fails closed with 422 instead of silently replaying.
- Schedule fan-out is keyed **per entry** (`entry_key(action_id, index)`), not per plan, because a plan may legitimately contain two identical `(content_id, platform, date)` entries and one batch key would write fewer rows than the user approved.
- Concurrency rests on the database: the claim is an INSERT guarded by the unique constraint; the loser catches `IntegrityError`, re-reads under `SELECT FOR UPDATE`, and branches on status (`completed` replays, `in_progress` raises `DuplicateRequestInFlight` → 409, `failed` reclaims the row so a transient error does not burn the key permanently).
- Refine's claim wraps both `save_content` and `update_content`, and is taken before awaiting the provider so a replay skips generation rather than billing twice.
- Wired: content create, content refine, both calendar commit paths. Full suite at that point was `262 passed`, 0 skipped.
- One deliberate quirk: the literal `422` is used instead of `status.HTTP_422_UNPROCESSABLE_ENTITY`, which is deprecated on the installed Starlette 1.6 while `HTTP_422_UNPROCESSABLE_CONTENT` is absent on older versions that `fastapi>=0.115` still permits. A comment explains the split.

### Part B — complete and verified green

Implementation complete:

- **Publication execute-layer idempotency**: `execute_publication` in `src/api/services/publish_service.py` conditionally uses `idempotent_write_async` only when the HTTP request included an `Idempotency-Key` header. The sentinel `_NO_IDEMPOTENCY_KEY` distinguishes "no header" from "None". When no key is provided, both the create and execute layers skip idempotency tracking (`_skip_execute_idempotency` flag in `request_payload`).
- **Publication stable request ID**: `publication_request_id(publication_id)` derives a stable token from the durable `platform_publications.id` row, so job retries, worker restarts, and re-enqueues all present the same `external_request_id` to the platform.
- **Memory mutation idempotency**: `_memory_mutation` in `src/api/services/chat_agent.py` uses `idempotent_write` with scope `SCOPE_MEMORY_MUTATION` and the consumed `proposed_actions.id` as key. The claim is taken before the file write; `in_progress` on SIGKILL means the mutation is lost and the key remains non-reusable (at-most-once semantics).
- **Route header plumbing**: `src/api/routes/publish.py` accepts optional `Idempotency-Key` header and passes it to `create_publication_request`, which stores it in `request_payload` for execute-layer use.

All 13 tests in `test_idempotency_publication_memory.py` pass. Full suite: **275 passed**.

Independent review completed. Known residual risk documented:

- `_call_rest_fallback` in `src/integrations/mcp_client.py:175-213` is an existing duplicate-publish window with no dedup token at the HTTP layer. This is a **known residual risk**: if the MCP server times out after accepting the request but before responding, a retry will publish twice. Consider adding request ID to the REST fallback headers in a future phase.

## Reusable verification environment

**Current method: Docker** (2026-09-04). The old hand-provisioned `/tmp/pg16` and
`/tmp/redis-root` trees described below were cleared and no longer exist; Docker
is available now, so there is no reason to rebuild them.

Loopback-only, throwaway credentials, non-standard ports so they cannot collide
with the compose stack (5432/6379). Never reuse this config anywhere shared.

```bash
sg docker -c "docker run -d --name cops_test_pg \
  -e POSTGRES_DB=content_ops_test -e POSTGRES_USER=content_ops \
  -e POSTGRES_PASSWORD=content_ops \
  -p 127.0.0.1:55432:5432 postgres:16-alpine"

sg docker -c "docker run -d --name cops_test_redis \
  -p 127.0.0.1:56379:6379 redis:7-alpine"
```

```bash
export TEST_DATABASE_URL='postgresql+psycopg://content_ops:content_ops@127.0.0.1:55432/content_ops_test'
export REDIS_URL='redis://127.0.0.1:56379/0'
```

Readiness gate before running pytest:

```bash
sg docker -c "docker exec cops_test_pg pg_isready -U content_ops -d content_ops_test"
```

Teardown: `sg docker -c "docker rm -f cops_test_pg cops_test_redis"`.

`sg docker -c "..."` is required, not optional: the user is in the `docker` group
but an already-running shell does not carry that gid in its process credentials,
so a bare `docker` call fails with `permission denied ... /var/run/docker.sock`.
It needs no sudo.

Only `content_ops_test` is used, in whatever state the last pytest run left it
(the `store` fixture drops and recreates every table per test, so its contents do
not matter).

<details>
<summary>Superseded: hand-provisioned /tmp trees (no longer present)</summary>

```bash
export PGHOME=/tmp/pg16
export PATH=$PGHOME/bin:$PATH
export LD_LIBRARY_PATH=$PGHOME/lib
pg_ctl -D /tmp/pgdata -l /tmp/pg16.log \
  -o "-p 55432 -k /tmp/pgsock -c listen_addresses=127.0.0.1" -w start

export LD_LIBRARY_PATH=/tmp/redis-root/usr/lib/x86_64-linux-gnu
mkdir -p /tmp/redisdata
nohup /tmp/redis-root/usr/bin/redis-server --port 56379 --bind 127.0.0.1 \
  --unixsocket /tmp/redis.sock --dir /tmp/redisdata > /tmp/redis.log 2>&1 &
```

Stop with `pg_ctl -D /tmp/pgdata -m fast -w stop` and `redis-cli -p 56379 shutdown nosave`. Full teardown is `rm -rf /tmp/pgdata /tmp/pg16 /tmp/pgsock /tmp/redisdata /tmp/redis-root`.

`LD_LIBRARY_PATH` was per-service: PostgreSQL binaries needed `/tmp/pg16/lib`, and `redis-cli`/`redis-server` needed `/tmp/redis-root/usr/lib/x86_64-linux-gnu`. Exporting the PostgreSQL path and then calling `redis-cli` failed with `liblzf.so.1: cannot open shared object file`.

</details>

## P1-03 checkpoint — ✅ COMPLETE

**New migration**: `0006_job_retry_fields.py` adds `max_retries`, `next_retry_at`, `error_type` to the `jobs` table.

**Error classification**: `src/jobs/error_classifier.py` categorizes exceptions as `transient` (retriable) or `permanent` (non-retriable). Transient includes network timeouts, rate limits, 429/502/503/504, temporary service unavailability. Permanent includes configuration errors, validation errors, 4xx (except 429), data integrity violations.

**Exponential backoff**: 30s → 60s → 120s → 240s → 480s (max), configurable via `JOB_RETRY_INITIAL_DELAY_SECONDS` and `JOB_RETRY_MAX_DELAY_SECONDS`.

**Runner logic**: `run_job_async` checks `next_retry_at` at entry and skips early retries. `_handle_job_error` classifies errors, calculates backoff, sets `next_retry_at`, and requeues via `queue.requeue_with_backoff`.

**Queue support**: RQ mode uses `enqueue_in` for true delayed execution (production); BackgroundTasks mode enqueues immediately but relies on entry check to skip early execution (dev/test).

**Test coverage**: 25 new tests in `tests/jobs/test_job_retry.py` covering error classification, backoff calculation, retry scheduling, attempt increment, and full retry flows. All passing.

Full suite: **300 passed** (up from 275).

Known residual risks documented in `docs/IMPROVEMENT_LOG.md`.

## Phase 2 checkpoint — ✅ COMPLETE

**New migration**: `0007_job_archived_at.py` adds `archived_at` to the `jobs` table for soft deletion.

**P2-01 Prometheus Metrics**: `src/utils/metrics.py` provides 12 core metrics with graceful degradation (NoOp when `prometheus_client` unavailable):
- `idempotency_requests_total{scope, outcome}` — claimed/replay/conflict/failed
- `job_retries_total{error_type}`, `job_retry_exhausted_total`, `job_failures_total{error_type}`
- `capability_proposals_total`, `capability_consumptions_total`, `capability_expirations_total`
- `publication_requests_total{status}`, `publication_request_duration_seconds{status}`
- `http_requests_total{method, endpoint, status}`, `http_request_duration_seconds{method, endpoint}`

**P2-02 Enhanced Logging**: `src/utils/enhanced_logging.py` provides 6 key event log functions (`log_idempotency_claim`, `log_job_retry`, `log_job_failure`, `log_capability_proposal`, `log_capability_consumption`, `log_capability_expiration`). Instrumented P1-01/02/03 critical paths. Sensitive data excluded.

**P2-03 Job Cleanup**: `src/jobs/cleanup.py` provides soft-delete maintenance script. Completed jobs: 30 days retention. Permanently failed jobs: 7 days retention. Supports `--dry-run` (default) and `--execute` modes.

**P2-04 Dashboard Queries**: `src/utils/dashboard_queries.py` provides `get_idempotency_stats(days=7)`, `get_job_retry_stats(days=7)`, `get_capability_stats(days=7)`.

**API Integration**: `/api/metrics` endpoint registered. `MetricsMiddleware` tracks all HTTP requests.

Full suite: **300 passed**.

Production recommendations:
- Deploy Prometheus server and configure scrape `/api/metrics`
- Configure Grafana dashboard
- Set up alerting rules (retry exhausted, 5xx high frequency)
- Configure cron for daily `cleanup.py --execute`

## P1-04 checkpoint — ✅ COMPLETE

**Implementation**: Job lease/heartbeat/reaper mechanism with checkpoint recovery for worker SIGKILL/OOM scenarios.

**New migration**: `0008_job_lease_and_checkpoints.py` adds:
- `worker_id` VARCHAR(255) — lease holder identity (hostname-pid-uuid8)
- `lease_expires_at` DATETIME — lease expiry timestamp
- `heartbeat_at` DATETIME — last heartbeat timestamp
- New table `run_steps` with `UNIQUE(run_id, step_index)` for checkpoint persistence
- Indexes: `(status, lease_expires_at)` for reaper scan, `(run_id, status)` for resume query

**Core components**:
1. **Job lease** (`src/storage/content_store.py`): 4 operations (acquire/extend/release/reclaim) with single-UPDATE atomic predicates
2. **Runner integration** (`src/jobs/runner.py`): worker identity, lease lifecycle, monitor task with cancellation propagation
3. **Reaper service** (`src/jobs/reaper.py`): CLI with `--dry-run`/`--execute`/`--loop` modes, reclaims expired leases without consuming retry count
4. **Checkpoint recovery** (`src/jobs/checkpoint.py`): 10 functions for pipeline step persistence, resume from last completed step

**Config**:
- `JOB_LEASE_DURATION_SECONDS` (default 300)
- `JOB_HEARTBEAT_INTERVAL_SECONDS` (default 30)
- `JOB_REAPER_INTERVAL_SECONDS` (default 60)
- `JOB_REAPER_BATCH_SIZE` (default 50)

**Test coverage**: 49 new tests in `tests/jobs/test_job_lease.py`:
- Lease acquisition: concurrency (8-way race), expiry, re-entry
- Heartbeat: extension, lost lease detection
- Release: non-holder rejection
- Reaper: expired discovery, reclaim logic, loop control
- Checkpoints: gap replay, running exclusion, duplicate prevention
- Runner integration: lease loss handling, cancellation, long task heartbeat
- Retry interaction: early skip, due execution

**Metrics**: 6 new P1-04 metrics (`job_lease_acquired_total`, `job_lease_conflicts_total`, `job_lease_lost_total`, `job_lease_reclaimed_total`, `job_checkpoints_saved_total`, `job_cancellations_total`)

**Full suite**: **349 passed, 7 skipped** (baseline: 300/7, no regression)

**Known residual risks** (documented in `docs/IMPROVEMENT_LOG.md`):
1. Checkpoint ≠ idempotency: step commit + checkpoint write gap can leave completed-but-unrecorded steps; business writes still need P1-02 ledger
2. DynamicPipeline not yet wired to checkpoint (out of P1-04 scope)
3. Background mode has no queue for reclaimed jobs (RQ production mode unaffected)
4. Reaper not yet integrated into API/worker lifespan (CLI works, integration deferred)
5. Lease:heartbeat ratio (10x) may need tuning per deployment

## P1-06 checkpoint — ✅ COMPLETE (E2E deferred)

**Implementation**: Frontend test toolchain plus SSE reconnect/idempotency, and the server-side keepalive the client's staleness detection depends on.

**The bug this closed**: the backend already accepted `after_seq` / `Last-Event-ID` and stamped every event with `id: <seq>`, but the frontend discarded all of it — a single `EventSource` `onerror` marked the run `failed` with no recovery path. Since `onerror` also fires for idle-proxy recycling, laptop sleep, and Wi-Fi handover, a still-healthy run that completed and saved server-side was routinely shown to the user as "执行失败".

**Frontend** (`frontend/src/composables/usePipelineStream.ts`, rewritten):
- `StreamConnectionState`: `idle | connecting | open | stale | reconnecting | closed`, tracked separately from `RunStatus`
- Exponential backoff 1s → 2s → 4s … capped at 30s, 6 attempts; `attempt` resets after a successful reopen
- Monotonic `lastSeq` cursor; every reconnect requests `?after_seq=N`, and any event with `seq <= lastSeq` is dropped before reaching a handler, so a replayed prefix cannot double-count tokens or duplicate body text
- `hello`/`ping` carry no `id` and are treated as liveness only — they must never rewind the cursor
- Terminal events set `terminal` and suppress all further reconnects
- Malformed frames are dropped instead of killing the subscription

**Native `EventSource` auto-reconnect is deliberately not used**: the browser sends `Last-Event-ID` only for reconnects it initiates, and its backoff is neither observable nor testable. Managing it manually buys an assertable `attempt` and deterministic timing.

**Reconciliation instead of guessing** (`frontend/src/views/Studio.vue`): when retries are exhausted the view calls `GET /api/agent/runs/{id}` for authoritative state. Terminal statuses are applied; a still-`running` run keeps the banner and a 重新连接 button so the run is not lost. A failed probe leaves the banner up rather than inventing a terminal state.

**Server keepalive** (`src/api/routes/agent.py`): emits a `: keepalive` **comment** frame after `SSE_KEEPALIVE_SECONDS` of silence. A comment frame consumes no sequence number, so it can never be mistaken for a replayable event, while still keeping intermediaries from reaping the connection. The hardcoded 600s deadline and 0.4s poll are now config.

**Config**:
- `SSE_KEEPALIVE_SECONDS` (default 15)
- `SSE_POLL_INTERVAL_SECONDS` (default 0.4)
- `SSE_STREAM_TIMEOUT_SECONDS` (default 600)

Keepalive must stay well under the client's `staleAfterMs` (45s default, 3x margin) or normal long steps get misreported as stale.

**Toolchain**: Vitest 3.2.4 + `@vue/test-utils` 2.4.6 + jsdom 25 (`npm test`, `npm run test:watch`). `tests/support/fakeEventSource.ts` deliberately does **not** auto-reconnect, so the composable's own backoff and cursor are the only things driving reconnects.

**Test coverage**: 55 new tests.
- `frontend/tests/usePipelineStream.spec.ts` (21) — dispatch, backoff timing asserted to the millisecond, cap, attempt reset, exhaustion reported once, replay dedupe, keepalive cursor safety, all three terminal types, stale without closing the socket, cursor reset across runs
- `frontend/tests/useJobPolling.spec.ts` (8) — completion, failure, cancellation, empty result, abort, reset, timeout, `onUpdate`
- `frontend/tests/ContentCard.spec.ts` (6) — proves the Vue component path works, not just plain TS
- `tests/test_sse_stream.py` (20) — drives the stream generator with an in-memory store double, so it needs **no PostgreSQL**: `id:` equals store seq, `after_seq` is strictly exclusive, `after_seq=0` is honoured rather than falling through to the header, keepalives carry no sequence, cursor parsing is fail-safe

**Verification**: `35 passed` (vitest), `vue-tsc --noEmit` clean, `npm run build` clean, `201 passed, 239 skipped` (pytest; baseline 181/239, +20 new, no regression).

**⚠️ Not verified this round**: the `413 passed` figure from the P1-05 session. This environment has no PostgreSQL binary, no Docker, and no `TEST_DATABASE_URL`, so all 239 DB-backed tests skip. The new backend tests were written to avoid that dependency.

**Known residual risks**:
1. Playwright E2E still missing — real-browser SSE + HttpOnly cookie + reverse-proxy behaviour remains open Phase 0 external evidence, same blocker as the Docker/TLS items
2. Token dedupe trusts server-side sequence monotonicity, currently guaranteed by `UNIQUE(run_id, seq)` plus the run-row lock; concurrent non-monotonic appenders would break it
3. Reconciliation fires only on retry exhaustion, not in `stale` — automatic polling would race the SSE stream and waste requests during normal long steps
4. The 6-attempt / 30s cap (~1 minute to give up) is a guess; tune against real P95 outage duration
5. `SSE_POLL_INTERVAL_SECONDS` is still table polling; high subscription counts want `LISTEN/NOTIFY`
6. Studio's workflow mode is unaffected — it uses `useJobPolling`, which tolerates drops but offers no stale/reconnect signal

## Phase 1 + Phase 2 status

✅ **P1-01** (Persistent capability) — Complete  
✅ **P1-02** (Business idempotency) — Complete, independently reviewed  
✅ **P1-03** (Automatic retry) — Complete  
✅ **P1-04** (Job lease & checkpoint recovery) — Complete  
✅ **P1-05** (Planner structured output) — Complete  
✅ **P1-06** (Frontend testing + SSE resilience) — Complete, Playwright E2E deferred  
✅ **P2-01** (Prometheus metrics) — Complete  
✅ **P2-02** (Enhanced structured logging) — Complete  
✅ **P2-03** (Job cleanup mechanism) — Complete  
✅ **P2-04** (Dashboard query helpers) — Complete  

Phase 1 core reliability infrastructure is **finished**. Phase 2 observability and monitoring is **finished**. All of P1-01…P1-06 are now closed; only Playwright E2E remains carved out of P1-06, blocked on the same missing runtime as the Phase 0 external evidence.

## Resume notes

1. P1-01…P1-06 are committed at `972625f`. The Docker-round fixes (gunicorn alias, alembic `fileConfig`, mirrors, `SSE_*` in compose, `tests/test_deployment_config.py`, docs) are a separate commit. Local is ahead of `origin/main` and **not pushed**.
2. Full suite on a real PostgreSQL: **`433 passed, 7 skipped`** (1659s, 2026-09-04). 🔴 The re-run including the 4 new deployment tests (expect **437**) was **stopped mid-flight and never finished** — run it first. The 4 pass on their own.
   - Ignore the older `413 passed` claim: it coexisted with "5 caplog tests fail in the full suite", and those 5 failures were a real defect (alembic disabling `src.*` loggers), now fixed.
3. **Production documentation complete**: `docs/PRODUCTION_OPERATIONS.md` provides comprehensive operational guide including:
   - Prometheus metrics setup and Grafana dashboard configuration
   - Structured logging and log aggregation patterns
   - Job cleanup maintenance procedures
   - Idempotency, automatic retry, and capability system monitoring
   - Troubleshooting guides for common operational issues
   - Performance tuning recommendations
   - Alerting rules and thresholds
4. Run one pytest process at a time against the test database: the `store` fixture drops and recreates every table, so parallel runs corrupt each other and produce spurious `IntegrityError`.
5. `alembic check` against `content_ops_test` reports "Target database is not up to date" because pytest builds that database with `create_all`. That is a test artifact, not drift. To check migrations, create a scratch database, run `upgrade head` against it, then `check`, then drop it.
6. Alembic head is now `0008_job_lease_and_checkpoints`.
7. **Frontend tests** (new in P1-06): `cd frontend && npm test` (Vitest, 35 tests) needs no database. `npx vue-tsc --noEmit` and `npm run build` both clean.
8. **Phase 0 status (updated 2026-09-04)**:
   - ✅ Production configuration validation tests (7/7 passing)
   - ✅ **Docker Compose validation done for real** — negative start fail-closed, positive stack all healthy, 8 migrations, health/readiness answering, RQ worker listening
   - ⚠️ **Unfixed, needs your decision**: `X-Forwarded-Proto` trust boundary is wider than the compose comment claims (host loopback traffic SNATs into `TRUSTED_PROXY_CIDRS`). Details at the top of this file.
   - 📋 Still missing: real browser/TLS reverse-proxy behaviour, pre-Alembic production snapshot rehearsal, multi-host/load evidence, volume persistence across restart
9. **Next priority options**:
   - **Finish the 437 re-run** (see item 2) — cheapest and highest value
   - **Decide on the `X-Forwarded-Proto` finding** — the only known unfixed issue
   - **Remaining Phase 0 evidence + Playwright E2E**: browser/TLS behaviour now also covers real-browser SSE reconnect and HttpOnly cookies. Docker is available, so these are no longer blocked on tooling — only on setting up a TLS proxy and a production snapshot.
   - **Production deployment**: ready within the documented residual-risk boundaries, with the `X-Forwarded-Proto` decision made first
   - **Optional follow-ups** from P1-06 residual risks: swap SSE table polling for `LISTEN/NOTIFY`, tune the reconnect budget against real outage data
