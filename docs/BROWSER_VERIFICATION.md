# 浏览器、TLS 与卷持久化验证

入口：`python3 scripts/verify_browser.py`。

脚本从当前 `docker-compose.yml` 生成独立的临时 Compose 项目，包含 PostgreSQL、
Redis、迁移、Gunicorn API、RQ worker、前端 Nginx 和测试 TLS 代理。它挂载当前源码
和本轮构建的前端产物；不连接现有应用库或 pytest 的测试库，也不调用 LLM 或发布平台。

## 准备与运行

需要 Docker Compose、Python 3、Node.js 20+/npm、OpenSSL，以及 API/前端运行镜像。
首次准备：

```bash
docker compose --env-file .env.docker.example build api frontend
cd frontend
npm ci
npx playwright install chromium
cd ..
python3 scripts/verify_browser.py
```

已有 `/opt/google/chrome/chrome` 时脚本自动使用该浏览器，可省略 Chromium 下载。
其他路径可通过 `E2E_CHROMIUM_EXECUTABLE` 指定。自定义镜像名可设置
`E2E_API_IMAGE` 和 `E2E_FRONTEND_IMAGE`，默认分别为
`content-ops-agent-api:latest` 和 `content-ops-agent-frontend:latest`。
后端依赖或 Dockerfile 变化后应先重建镜像；挂载源码不能更新镜像内的依赖。

脚本自动生成独立随机凭据和一天有效的自签证书，只在回环地址映射随机 HTTPS 端口。
`content-ops.test` 仅在测试浏览器内解析到回环地址，不修改系统 hosts；CORS 使用实际 HTTPS 来源。
Playwright 为该测试环境设置 `ignoreHTTPSErrors`，因此验证的是真实 TLS 链路和浏览器行为，
不包含公有证书签发、信任链或线上域名配置。

## 验证边界

| 检查 | 实际路径与断言 |
| --- | --- |
| 登录 | 操作构建后的 Vue 登录页，检查 HttpOnly、Secure、SameSite=Strict 和 `/api` Cookie 范围 |
| Cookie 隔离 | 在 `/api` 页面读取 `document.cookie`；Cookie 不能代替普通内容 API 的 Bearer 鉴权 |
| 媒体 | 原生 Image 加载 PNG；浏览器 Range 返回 206、正确字节与 Content-Range；越界返回 416 |
| URL 凭据 | 生产前端 Nginx 拒绝 access_token/access_ticket，日志不含探测值 |
| 退出 | 清除资源 Cookie；后续媒体和 SSE 请求返回 401 |
| 到期 | 等待真实一分钟 TTL；验证浏览器移除 Cookie，以及服务端拒绝重新送入的过期令牌 |
| SSE 心跳 | 真实 EventSource + 当前 usePipelineStream；收到业务事件后持续空闲仍保持 open，游标不变 |
| SSE 重连 | 服务端到达 8 秒连接期限后关闭；前端携带 after_seq 重连，补收事件一次并进入终态 |
| 持久化 | 移除并重建该项目全部容器、保留卷；核对内容记录、媒体字节、记忆目录文件和运行事件 |

SSE 用例通过 Vite 编译并注入仓库中的真实 composable，使用原生 EventSource 与实际服务通信，
没有 mock SSE 服务。这覆盖网络/协议集成；尚未覆盖在完整 Studio 页面中创建和恢复真实 LLM 流水线。
数据库内的运行事件由测试专用容器命令生成，没有向生产 API 增加测试接口。

本测试沿用当前 Compose 的代理信任配置，不能视为已修复 `X-Forwarded-Proto`
信任范围偏宽的问题。退出和过期检查针对**后续请求**，不声称撤销已经打开的流，
也不声称 logout 会使已签发的 Bearer 令牌在服务端立即失效。

## 产物与清理

Playwright 报告写入 `frontend/test-results/e2e-results.json`（git 忽略）。
为避免凭据进入产物，关闭 trace、视频和截图。运行结束，无论断言是否通过，
脚本都会删除自己创建的容器、网络、卷和临时配置；不会清理已有 Compose 项目。
首次 `up` 失败的诊断可用控制台日志；运行被 SIGKILL 或宿主机断电打断时，需按输出中的
`content-ops-e2e-*` 项目名识别并手动清理残留。

最新执行结果见 [当前交接记录](WORKFLOW_CHECKPOINT.md) 和
[外部证据报告](phase0_external_evidence.md)。
