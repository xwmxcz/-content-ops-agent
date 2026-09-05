# Workflow Checkpoint

更新日期：2026-09-05。验证起始代码基线：`e7e9744`，本轮修复与验证证据随提交保留。

本文件只保留当前状态。此前交接记录含互相矛盾的历史测试数和环境状态，已原样保存于
[2026-09-04 归档](archive/WORKFLOW_CHECKPOINT_2026-09-04.md)。历史记录中的“恢复后第一件事”
和“已完成”不覆盖本文件；详细实施历史仍见 [IMPROVEMENT_LOG.md](IMPROVEMENT_LOG.md)。

## 当前阶段

- Phase 1 P1-01…P1-06 的主体实现已完成：工具授权、幂等、重试、租约/心跳/检查点基础设施、Planner 结构化输出、前端测试与 SSE 恢复。
- Phase 2 的指标、结构化日志、任务清理和统计查询已实现。
- Phase 0 外部验证继续补齐，仍不能据此认定所有生产验收项已通过。

## 本轮工作（2026-09-05）

1. 恢复独立 PostgreSQL/Redis 测试容器，执行包含 4 条部署回归的完整后端套件。
2. 新增可重复执行的 Playwright/TLS 验证脚本，隔离运行生产 Compose 配置。
3. 验证 SSE 心跳在真实 EventSource 中的表现，并补前后端回归。
4. 验证浏览器登录、资源 Cookie、图片、Range、退出/过期、重连，以及卷持久化。
5. 整理当前交接与历史记录，避免把旧测试数字当作本轮结果。

| 验证 | 最终结果 |
| --- | --- |
| 真实 PostgreSQL 完整后端基线 | **437 passed、7 skipped**，2172.58 秒，退出 0 |
| 最终 SSE/部署专项 | **24 passed**，退出 0 |
| 独立生产配置检查 | **7/7**，退出 0；对应完整套件中有意跳过的 7 条 |
| 前端单测 | **37 passed**，退出 0 |
| 前端类型检查与 Vite 构建 | 通过 |
| 真实浏览器/TLS | **6 passed**，约 86 秒，无跳过/重试后通过 |
| 容器重建后持久化 | 内容记录、媒体字节、记忆目录文件和运行事件均通过 |
| 整体验证脚本与清理 | **退出 0**，临时容器、网络和卷全部删除 |

验证顺序：完整后端套件在 SSE 修改前启动，Python 模块在收集时已加载；
最终 SSE 修改另由 24 条后端专项与真实浏览器验证。**没有将专项数量与全量相加，也没有声称修改后重新跑了第二遍全量。**
此前交接中“包含新增 4 条部署测试的 437 复验未完成”现已闭环。

机器可读摘要（含源码校验值）见 [validation.json](evidence/2026-09-05-validation.json)，
详细行为证据见 [外部验证报告](phase0_external_evidence.md)。

## 验证入口

后端（只允许指向一次性测试库，fixture 会 drop/create 所有表）：

```bash
docker start cops_test_pg cops_test_redis
TEST_DATABASE_URL='postgresql+psycopg://content_ops:content_ops@127.0.0.1:55432/content_ops_test' \
REDIS_URL='redis://127.0.0.1:56379/0' \
python3 -m pytest tests/ -q --durations=15
```

一次只运行一个使用该库的 pytest 进程。完整测试套件有大量 DDL，运行时间较长。

前端和浏览器：

```bash
cd frontend
npm test
npm run build
cd ..
python3 scripts/verify_browser.py
```

浏览器脚本所需镜像、浏览器安装、测试边界和清理策略见
[BROWSER_VERIFICATION.md](BROWSER_VERIFICATION.md)。它创建自己的数据库和卷，
可与使用 `content_ops_test` 的后端套件同时运行。

## 尚未闭环

- **代理信任范围**：当前 Compose/前端 Nginx 信任 `172.16.0.0/12`。已有实测表明宿主机流量经 SNAT 落入信任范围。本轮浏览器验证不能视为此问题已修复；需按实际部署的反代身份与拓扑收紧并验证。见 [外部证据 §2.6](phase0_external_evidence.md)。
- **真实旧库迁移**：缺少 pre-Alembic 生产快照，不能用空库迁移或模拟数据代替验收。
- **多主机与负载证据**：未执行，需要实际目标拓扑、负载模型和验收指标。
- **完整 Studio 页面 E2E**：本轮 SSE 用例覆盖真实 composable + 浏览器 + 服务端，尚未自动操作 Studio 创建并恢复真实 LLM 流水线。
- **任务恢复边界**：DynamicPipeline 尚未接入检查点；reaper 目前是 CLI，尚未接入默认 Compose/lifespan；background 模式没有重排队恢复。
- **认证边界**：logout 清资源 Cookie，不立即撤销已签发的 Bearer；已打开的 SSE 也没有逐帧重新认证。本轮只验证后续请求。

## 环境与后续顺序

- **后续本机启动（2026-09-05，用户请求）已完成**：入口 `http://localhost:8088`，API `http://127.0.0.1:8000`。当前应用容器已运行工作区最新 API、前端构建及 Nginx 修复；页面、readiness（DB/Redis）和管理员登录均验证通过。
- 本机使用 `APP_ENV=development`、`ENFORCE_HTTPS=false`、`AUTH_ENABLED=true`、`SCHEMA_MANAGEMENT=validate`，端口仍只绑定回环地址。原有 PostgreSQL/Redis 凭据、管理员凭据与数据卷保留。私有配置恢复到 Git 忽略的根目录 `.env`（0600）。
- **模型配置尚未就绪**：保留的 `DEEPSEEK_API_KEY` 是验证占位值。使用生成能力前需在本机 `.env` 填真实 Key，再执行 `docker compose up -d --force-recreate api worker`。不要提交凭据。
- 构建说明：API/worker/migrate 已正常构建；前端容器 `npm ci` 耗时较长而中止，改用本机 `npm run build` 的产物与最新 Nginx 配置生成运行镜像。`docker compose up -d --no-build --wait` 已退出 0；运行文件哈希与工作区一致。后续启动已有镜像用 `docker compose up -d`。
- 当前账号已具备 Docker 组权限，可直接使用 `docker`，不再需要旧记录中的 `sg docker`。
- 前述验证使用独立 E2E 项目；之后的本机启动只重建应用服务，没有删除原有数据卷。
- `cops_test_pg`（55432）和 `cops_test_redis`（56379）用于后端测试；E2E 项目结束后自动删除自己的容器和卷。
- 数据库迁移 head 为 `0008_job_lease_and_checkpoints`。
- pytest 的库由 create_all 重建，不能直接用它做迁移漂移判断；迁移检查应在单独空库先 upgrade head，再 alembic check。
- 本轮修复、浏览器验证工具和进度文档一并纳入版本控制，具体提交与远程同步状态以 Git 记录为准；已按用户请求用于本机开发容器，未对外部署生产站点。
- 后续优先处理代理信任拓扑，再推进 Studio 页面恢复验证和真实旧库迁移；负载验证先定义目标。
