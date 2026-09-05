# Phase 0 External Evidence Validation Report

**Status**: 🟡 Phase 0 部分完成，当前结果见 §0

**Date**: 2025-01-13（初稿）/ 2026-09-04（Docker）/ 2026-09-05（浏览器与持久化）

**Validator**: PostgreSQL tests + Docker Compose + Chromium/Playwright + TLS proxy

## Executive Summary

生产配置验证逻辑已通过独立测试套件（7/7）。**Docker 容器化验证已于 2026-09-04 真实执行完成**（此前因环境无 Docker 而推迟）。

这轮容器验证的价值在于它找出了**两个纯代码审查与无容器测试无法发现的真实缺陷**：

1. 🔴 `gunicorn.conf.py` 的 `config` 名字与 gunicorn 自身设置项碰撞 → api 容器崩溃重启循环，**生产完全跑不起来**。已修复。
2. 🔴 `migrations/env.py` 的 `fileConfig` 默认禁用所有 `src.*` logger → 迁移后应用日志静默。已修复（该缺陷同时是全量套件 5 个失败的根因）。

另有一项 `X-Forwarded-Proto` 信任边界的发现，属于需用户决策的安全变更，**未擅自修改**（见 2.6）。

## 0. 2026-09-05 续验

新增可重复运行入口 `python3 scripts/verify_browser.py`，详见
[浏览器验证指南](BROWSER_VERIFICATION.md)。当前源码与前端构建产物挂载到独立 Compose 项目，
使用真实 Chromium → TLS Nginx → 生产前端 Nginx → Gunicorn API → PostgreSQL。
证书为临时自签，测试浏览器将 `content-ops.test` 解析到回环地址；未使用公网证书或实际社交账号。

### 本轮发现的两个缺陷

- **SSE 注释心跳不可见**：原生 EventSource 不派发注释；未指定 ID 的 ping 又会继承上一条 ID，
  被原前端去重逻辑忽略。真实浏览器在长步骤中进入 stale；后端改发不占序号的 ping，
  前端 liveness 独立于业务序号处理。详见 [实施日志](IMPROVEMENT_LOG.md)。
- **Nginx 默认日志仍记录查询凭据**：请求虽返回 400，但镜像默认 main 日志仍输出查询值，
  与额外的 sanitized 日志同时存在。改在 server 层设置 access_log，覆盖父层默认日志。
  回归不仅检查探测值消失，也检查每个请求仍有且仅有一条脱敏记录。

修复前真实浏览器：**4 passed、2 failed**；两条失败分别捕获上述问题。
修复后的前端单测：**37 passed**；SSE/部署专项：**24 passed**；独立生产配置校验：**7/7**。
修复后真实浏览器 **6 passed（85.98 秒）**；完整后端基线 **437 passed、7 skipped（2172.58 秒）**。
7 条跳过项均为要求独立运行的生产配置检查，单独运行 **7/7**，不存在缺少数据库导致的跳过。
完整套件在 SSE 修改前已收集 Python 模块，最终修改另由 24 条专项和真实浏览器验证；
不把这些数字相加，也不声称对最终修改重跑了第二遍全量。

最终 `scripts/verify_browser.py` **退出码 0**，包含测试、容器重建、持久化断言与清理。
中间一轮工具报告退出 143，虽然浏览器报告与持久化断言均已通过，仍未把该轮当作脚本完整成功；
补充运行器退出状态标记后重新执行，确认完整命令退出 0。未将该异常归因于未经证实的原因。
机器可读结果和相关源码 SHA-256 见 [validation.json](evidence/2026-09-05-validation.json)。

| 浏览器检查 | 结果 |
| --- | --- |
| Vue 登录、HttpOnly/Secure/SameSite/Path、Cookie 权限隔离 | 通过 |
| 原生图片加载、Range 206/正确字节、越界 416 | 通过 |
| URL 凭据拒绝 400、查询/Referer 脱敏且保留单条日志 | 通过 |
| logout 清 Cookie，后续媒体/SSE 返回 401 | 通过 |
| 业务事件后持续空闲，心跳保持 open 且 lastSeq=1 | 通过 |
| 到期断流后 after_seq=1 重连，补收 B，AB 只出现一次，终态 lastSeq=3 | 通过 |
| 真实一分钟 TTL 后，浏览器清 Cookie，服务端拒绝过期 Cookie/Bearer | 通过 |

环境：Docker 29.8.0、Compose 5.5.1、PostgreSQL 16、宿主 Python 3.12.3、Node 24.18.1、
Playwright 1.63.0、Google Chrome 152.0.7977.82。API 使用现有 Python 3.11 镜像运行时，
挂载当前源码；本轮没有重新安装镜像内的后端依赖。

### 已完成的卷持久化证据

独立项目先生成内容、PNG 媒体、记忆目录标记文件及运行事件，然后 `docker compose down`
（保留卷），重新 `up --wait`。数据库和文件断言均通过：

```text
Persistence verified after container recreation: content, media bytes, memory file, run events
```

这是正常停机、重建全部容器后的持久化验证，不等同于断电恢复或备份恢复演练。
结束时仅对本轮临时项目执行 `down --volumes`；既有应用容器和数据未用于测试。

---

## 1. Production Configuration Validation ✅

### Test Coverage

创建了独立测试套件 `tests/standalone/test_production_validation.py`，验证生产配置强化逻辑：

#### 1.1 弱密码拒绝 ✅
- **测试**: `test_production_validation_rejects_weak_password`
- **验证**: 生产环境正确拒绝短密码（< 12 字符）
- **结果**: ✅ PASS

#### 1.2 弱密钥拒绝 ✅
- **测试**: `test_production_validation_rejects_weak_secret`
- **验证**: 生产环境正确拒绝短密钥（< 32 字符）
- **结果**: ✅ PASS

#### 1.3 示例值拒绝 ✅
- **测试**: `test_production_validation_rejects_example_values`
- **验证**: 生产环境正确拒绝包含 "CHANGE_ME" 等不安全标记的值
- **结果**: ✅ PASS

#### 1.4 调试模式拒绝 ✅
- **测试**: `test_production_validation_rejects_debug_mode`
- **验证**: 生产环境正确拒绝 DEBUG=true
- **结果**: ✅ PASS

#### 1.5 HTTP CORS 拒绝 ✅
- **测试**: `test_production_validation_rejects_http_cors`
- **验证**: 生产环境正确拒绝 HTTP CORS 源（要求 HTTPS）
- **结果**: ✅ PASS

#### 1.6 有效配置接受 ✅
- **测试**: `test_production_validation_accepts_valid_config`
- **验证**: 符合所有要求的配置被正确接受
- **结果**: ✅ PASS

#### 1.7 开发环境宽松验证 ✅
- **测试**: `test_development_allows_weak_config`
- **验证**: 开发环境允许弱配置（符合预期行为）
- **结果**: ✅ PASS

### Test Execution

```bash
$ python3 tests/standalone/test_production_validation.py
Production Configuration Validation Tests
======================================================================

Results: 7/7 tests passed

🎉 All production validation tests passed!
```

### Technical Notes

1. **独立测试设计**: 测试文件作为独立脚本运行，避免 pytest 的模块缓存问题
2. **配置重载**: 每个测试使用 `reload_config()` 强制重新加载配置模块
3. **强密码要求**: 
   - AUTH_PASSWORD: ≥12 字符，≥12 唯一字符
   - AUTH_SECRET_KEY: ≥32 字符，≥12 唯一字符
   - DATABASE_URL 密码: ≥16 字符，≥12 唯一字符
4. **不安全标记检测**: 正确识别 "password", "secret", "CHANGE_ME", "example" 等

---

## 2. Docker Compose Validation ✅ 已完成（2026-09-04）

### 环境

```
Docker Engine 29.8.0 / Compose v5.5.1
```

此前该节记为「环境限制推迟」（`docker: command not found`）。Docker 安装后本节已真实执行。

注意：用户已加入 `docker` 组，但既有 shell 的进程凭证里没有该 gid，需 `sg docker -c "..."` 起一个带新组的会话，不需要 sudo。

### 2.1 否定用例 — 弱默认值必须拒绝启动 ✅

用仓库自带的 `.env.docker.example`（仍是 `CHANGE_ME` 占位值）启动 `migrate`：

```bash
docker compose --env-file .env.docker.example run --rm --no-deps migrate \
  python -c 'from src.utils import config; config.validate_runtime()'
```

结果：**退出码 1，fail-closed**，四条弱密钥全部被拒，schema 未被触碰：

```
ValueError: Unsafe production configuration: production requires a high-entropy
AUTH_PASSWORD of at least 12 characters; production requires a high-entropy
AUTH_SECRET_KEY of at least 32 characters; production DATABASE_URL must include a
high-entropy password of at least 16 characters; production REDIS_URL must include
a high-entropy password of at least 16 characters
```

### 2.2 正向用例 — migrate → api/worker → frontend ✅

用四个互不相同的强随机密钥（`validate_runtime()` 拒绝复用）生成 env 文件，置于 `/tmp` 而非仓库内以免误提交。

```
SERVICE    STATUS                    PORTS
api        Up (healthy)              127.0.0.1:8000->8000/tcp
frontend   Up                        127.0.0.1:8088->80/tcp
postgres   Up (healthy)              127.0.0.1:5432->5432/tcp
redis      Up (healthy)              127.0.0.1:6379->6379/tcp
worker     Up                        8000/tcp
migrate    Exited (0)
```

逐项证据：

| 检查 | 结果 |
|------|------|
| `migrate` 退出码 | 0 |
| 迁移链 | `0001_baseline` → … → `0008_job_lease_and_checkpoints`，8 步全部执行 |
| 库内 `alembic_version` | `0008_job_lease_and_checkpoints` |
| `GET /api/health` | 200 `{"status":"ok"}` |
| `GET /api/health/ready` | 200 `{"database":"ok","redis":"ok"}` |
| frontend 静态站点 | 200，873B |
| RQ worker | `*** Listening on content_ops...`（rq 2.12.0） |
| 明文调普通 API（无 XFP 头） | 426 HTTPS is required |

### 2.3 构建期发现：镜像源必须用国内节点 ✅ 已修复

构建在容器内**无代理**，两处默认源均不可用：

- `apt`：`deb.debian.org` 拉 9.6MB Packages 索引 **>650 秒未完成**并使构建失败；换 USTC 后 **8 秒**取完全部包。
- `pip`：上游 `pypi.org` 实测 **0 KB/s**（20 秒零字节），构建爬行在 22.9 kB/s；换 tuna 后达 **16 MB/s**。

容器视角（无代理）实测吞吐，10 秒持续读一个 botocore wheel：

```
tuna    6880 KB/s      tencent  195 KB/s
huawei  6512 KB/s      aliyun    89 KB/s
ustc    6118 KB/s      pypi.org    0 KB/s
```

⚠️ **方法论教训**：先前一轮在宿主机 shell 里测出「上游快 26 倍」，是因为该 shell 导出了 `http(s)_proxy=127.0.0.1:7890`。代理让上游显快、又把国内镜像流量拖去海外出口，**排名完全反转**。凡是要代表容器网络的测量，必须剥离代理再测。

两处都做成 build arg（`APT_MIRROR` / `PIP_INDEX_URL`），非中国大陆网络可覆盖。

### 2.4 运行期发现：真实生产缺陷 🔴 已修复

`api` 容器起不来，崩溃重启循环，healthcheck 永不通过：

```
Invalid value for config: <src.utils.config.Config object at 0x...>
Error: Not a string: <src.utils.config.Config object at 0x...>
```

根因：`gunicorn.conf.py` 用 `from src.utils import config` 在模块级绑定了名字 `config`。gunicorn 会遍历配置文件的模块级名字，凡与自身 119 个设置项同名就当作该设置的取值 —— 它恰好有一个叫 `config` 的设置（即 `-c` 选项），要求值必须是字符串。

这类缺陷**只有真实启动容器才能发现**：`python server.py` 的开发路径不加载该文件，纯单测与代码审查都碰不到。这正是 Phase 0 坚持要外部证据的理由。

修复：改为 `from src.utils import config as app_config`（与 `migrations/env.py` 已有写法一致）。回归测试见 `tests/test_deployment_config.py`，直接调用 gunicorn 自己的 `Config.set()` 校验，而非复刻其规则。

### 2.5 P1-06 SSE keepalive 端到端验证 ✅

造一个 `running` 且无事件的 run，读流 40 秒：

```
event: hello$
data: {}$
$
: keepalive$
$
: keepalive$
$
```

| 断言 | 结果 |
|------|------|
| keepalive 注释帧 | 2 个（与 15s 默认间隔吻合） |
| **带 `id:` 的帧** | **0** |

第二条是关键：keepalive **不占序号**。客户端的重放去重完全依赖这个不变量，现在它有了真实容器里的端到端实证，不再只是单测断言。

顺带补上一处缺口：`SSE_KEEPALIVE_SECONDS` / `SSE_POLL_INTERVAL_SECONDS` / `SSE_STREAM_TIMEOUT_SECONDS` 此前未透传到 compose，容器只能用代码默认值，现已加入 `docker-compose.yml`。

### 2.6 待你决策的安全发现 ⚠️ 未修复

**`X-Forwarded-Proto` 的信任边界比文档所述更宽。**

`docker-compose.yml` 注释写的是「只有私有 Docker 桥可以向 API 断言 X-Forwarded-Proto」。实测并非如此：

```
无 XFP 头              -> 426   （HTTPS 强制生效）
XFP: http              -> 426
XFP: https（宿主机发出）-> 401   （已穿过 HTTPS 强制，仅被认证拦下）
```

受控实验确证因果：把 `TRUSTED_PROXY_CIDRS` 收窄到不含桥网关后，同一请求由 401 变回 426。

机制：宿主机经发布端口进来的流量被 SNAT 成桥网关地址 `172.18.0.1`，落在 `TRUSTED_PROXY_CIDRS=172.16.0.0/12` 内，于是被判定为可信代理。nginx 侧的 `geo` 块同样信任该网段，其 `remote_addr` 亦为 `172.18.0.1`（access log 已确认），因此经 8088 走 nginx 也是同样结果。

**影响范围**：`8000` 与 `8088` 均只绑定 `127.0.0.1`，因此利用前提是已有宿主机本地访问权；这不是远程可达的漏洞，而是纵深防御被削弱、且与文档声明的意图不符。

**未擅自修改**：收紧信任网段会改变生产反代拓扑的前提假设，属于需要你决策的安全变更。可选方向：改用 `X-Real-IP` 结合真实反代身份判定、把网段收窄到 nginx 容器的确切地址、或修正注释以承认宿主机本地流量同属可信面。

---

## 3. Additional Verification Completed ✅

### 3.1 Configuration File Structure ✅
- 检查了 `docker-compose.yml` 语法和结构
- 验证了环境变量配置
- 确认了服务依赖关系

### 3.2 Test Suite Integrity ✅

最新（2026-09-05）：**437 passed、7 skipped**，完整基线退出 0；最终变更的专项覆盖与顺序见 §0。

初稿时记录为 `300 passed`，但那是无 `TEST_DATABASE_URL` 的环境，大量测试被 skip。

2026-09-04 在一次性 PostgreSQL 16（Docker）上的真实全量结果：

```bash
$ TEST_DATABASE_URL=postgresql+psycopg://... python3 -m pytest tests/ -q
5 failed, 428 passed, 7 skipped   # 修复 fileConfig 前
433 passed, 7 skipped             # 修复后（1659s）
```

那 5 个失败不是测试瑕疵，而是 `migrations/env.py` 禁用应用 logger 的真实缺陷（见 2.4 同类问题的记录方式）。P1-05 会话曾把它归为「caplog fixture 问题」并同时声称 `413 passed`，两者矛盾；现已定根因并修复。

### 3.3 Git Repository State（2026-09-05）

基线 `e7e9744`，`main` 领先本地记录的 `origin/main` 3 个提交；验证结束时改动未提交、未推送、未部署。
之后用户请求启动项目，最新代码已用于本机开发容器；入口及模型 Key 的待配置状态见 [当前交接记录](WORKFLOW_CHECKPOINT.md)。
此前此节的“与 origin 同步且工作树干净”是旧记录，已替换。

---

## 4. Recommendations

### Immediate Actions
✅ **完成** - 生产配置验证测试已创建并通过  
✅ **完成** - Docker Compose 容器化验证已真实执行（见 §2），并修复由此暴露的两个生产缺陷

### Before Production Deployment

⚠️ **待你决策** - `X-Forwarded-Proto` 信任边界（见 §2.6）。宿主机本地流量经 SNAT 后落入 `TRUSTED_PROXY_CIDRS`，得以断言 HTTPS。上线前应明确反代拓扑并相应收窄网段，或确认接受现状。

📋 **仍需补齐**：
- 真实生产快照的 pre-Alembic 演练（备份 → schema 审阅 → `alembic stamp 0001_baseline` → `upgrade head`）。本轮是空库从 0001 跑到 0008。
- 多主机/负载证据。
- 完整 Studio 页面创建/恢复真实流水线的 E2E。本轮 SSE 验证使用真实 composable，但事件由隔离库 fixture 生成。
- 实际部署域名、公有证书与反代拓扑的验收。本轮是本机真实 TLS 链路，见 §0 的边界说明。

### CI/CD Integration
📋 **建议** - 将本轮两个用例固定进 CI：
- 否定用例：`.env.docker.example` 启动必须退出非 0
- 正向用例：强密钥下 `api` 必须达 healthy（这一条能拦住 §2.4 类型的崩溃循环）
- `tests/test_deployment_config.py` 已将两个缺陷锁在单测层，无需容器即可拦回归

---

## 5. Conclusion

已完成:
- ✅ 生产配置验证逻辑（7/7 测试通过）
- ✅ **Docker Compose 端到端验证**：否定用例 fail-closed、正向用例全栈 healthy、8 步迁移、health/ready 实际响应、RQ worker 监听
- ✅ **两个生产缺陷修复并附回归测试**（gunicorn 名字碰撞、alembic 禁用 logger）
- ✅ **历史真实全量套件（2026-09-04）**：`433 passed, 7 skipped`（本轮结果见 §0）
- ✅ P1-06 SSE keepalive 端到端实证（keepalive 不占序号）
- ✅ 镜像源改为国内节点（apt → USTC，pip → tuna），构建从失败/爬行变为可用

待决策:
- ⚠️ `X-Forwarded-Proto` 信任边界比文档声明更宽（§2.6）

仍缺:
- 📋 pre-Alembic 生产快照演练、多主机负载证据、实际部署拓扑验收
- 📋 完整 Studio 页面工作流 E2E（浏览器/协议集成见 §0）

---

## Appendix: Test Artifacts

### A.1 Standalone Test Location
- **路径**: `tests/standalone/test_production_validation.py`
- **运行器**: `tests/standalone/run_production_validation.sh`
- **执行**: `python3 tests/standalone/test_production_validation.py`

### A.2 Test Independence
- 使用空 `tests/standalone/conftest.py` 避免继承共享配置
- 每个测试独立设置环境变量
- 强制重载配置模块以避免缓存

### A.3 Coverage Gaps

已补齐（2026-09-04，见 §2）：
- ✅ Docker 容器启动
- ✅ 服务间网络通信（api↔postgres↔redis、nginx→api、桥内容器→api）
- ✅ 健康检查端点实际响应（liveness 200、readiness 200 含 DB/Redis 子检查）

2026-09-05 卷持久化已验证，浏览器/TLS 的本轮结果见 §0。

仍缺：
- ❌ pre-Alembic 生产快照演练
- ❌ 多主机/负载证据
- ❌ 完整 Studio 页面工作流 E2E 与实际部署拓扑验收

旧库与多主机验收需要相应数据和目标环境；不能仅因工具可用就标为通过。
