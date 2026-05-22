# CHANGELOG · 2026-05-22

今天的工作把这个项目从"会写一篇内容的 LLM demo"重新定位成"三档复杂度的 agentic system 范例"，并补齐了端到端流程。

## 产品定位重置

三个 surface 现在有了清晰的角色分工：

| Surface | 角色 | 适合的工作 |
|---|---|---|
| **Workflow**（Studio mode=workflow）| 写手 | 标准化批量产出，固定 4 步、可预期耗时 |
| **Dynamic Pipeline**（Studio mode=dynamic）| 资深写手 | 需要事实校验或外部资料的硬题，3-6 步动态计划 |
| **Chat Agent**（/chat）| 主编 / 运营 | 跨多篇内容的优化、选题、排期，16 个工具 |

新的故事线：**用 Workflow 或 Dynamic 生产 → 在 Chat 中优化 + 排期**。两条产线一个调度器。

---

## 后端改动

### 1. `src/api/services/sub_agents.py`
- `SubAgentSpec` 新增 `max_tokens: int | None`，可覆盖请求级 max_tokens；reviewer 设 2048 避免输出截断
- `SubAgentRunner.run()` 新增 `tool_sink` 回调；`_run_with_tools` 在每次工具调用前后向 sink 推送 `tool_call_start / tool_call_result`
- 修复 token 累计 bug：从 `ai_message.usage_metadata` 累计真实 prompt/completion tokens（之前 tool 路径固定返回 0）
- researcher / fact_checker 的 system prompt 改为软引导（不强制调用工具，由 LLM 决定）
- researcher 和 fact_checker 的工具白名单加上 `web_search`

### 2. `src/api/services/dynamic_pipeline.py`
- 给 `runner.run()` 传 `tool_sink`，把工具事件转写成 SSE 的 `tool_call_start / tool_call_result`
- `step.tool_events` 跟着 `step_complete` 一起回传（强类型 `SubAgentToolEvent`）
- planner 失败 / 空 / JSON 错误时打印 `[planner] ...` 诊断日志
- 修：`step.tool_events` 改用 Pydantic 模型构造，消除序列化 warning

### 3. `src/llm/litellm_client.py`
- `generate_stream` 加 `stream_options={"include_usage": True}`，OpenAI 兼容 provider 流式返回 usage
- 流到一半异常 + 已有累积内容 → 吞掉异常用累积内容 finish；没内容才 fallback 到非流式（修 reviewer 撞 max_tokens 时随机失败）
- 异常时在 stderr 打 `[litellm.stream] ...` 诊断日志

### 4. `src/storage/content_store.py`
- 新增 `aggregate_performance(days)`：按 content_type / style 聚合，返回 ~1KB 紧凑结构 + top performers
- 新增 `get_calendar_conflicts(start_date, end_date)`：避免发布编排撞日
- 新增 `list_optimization_candidates(criteria, limit)`：三档 criteria — `underperforming` / `recent_drafts` / `old_drafts`

### 5. `src/api/services/chat_agent.py` — 工具池扩张 11 → 16
- 新工具 `web_search`：DuckDuckGo HTML 端点，无 key
- 新工具 `analyze_content_performance`：包装 `aggregate_performance`
- 新工具 `find_optimization_candidates`：包装 `list_optimization_candidates`
- 新工具 `propose_topics`：返回"选题情报"（数据聚合 + 最近标题），让外层 chat agent 自己合成具体选题
- 新工具 `propose_publishing_schedule`：算排期 **不写库**，避开冲突
- 新工具 `commit_publishing_schedule`：把上面的 plan 写库
- 系统 prompt 加 propose-then-commit 流程规范，加"哪些内容值得改"的优化分支

### 6. `src/tools/web_search.py` 新文件
- DuckDuckGo HTML 端点，无 API key，15 秒超时，失败兜底空数组

### 7. `src/api/schemas/agent.py`
- 新增 `SubAgentToolEvent` schema
- `PipelinePlanStep` 加 `tool_events: list[SubAgentToolEvent]`

### 8. `examples/seed_demo_data.py` 重写
- 50 条覆盖 6 题材域（科技10 / 职场10 / 生活12 / 金融8 / 餐饮6 / 教育4）
- 36 条带指数分布的真实指标（views/likes/comments/shares）
- 平台分布：xhs 35 / blog 10 / weibo 7 / video 5 / twitter 4
- 5 种 status 混合，60 天时间窗散布，6 个排到未来 14 天的发布日历

---

## 前端改动

### 1. `frontend/src/views/Studio.vue`
- 重写为单页 + 顶部 segmented control 切 `Workflow / Dynamic`
- 配置区两种 mode 共用，timeline + step output 共用同一份 `PipelinePlanStep[]` 数据结构
- mode 状态同步到 URL `?mode=...`
- running 时按钮区切换成 progress strip（蓝色进度条 + "停止"按钮），消除"运行按钮在转"的体验割裂
- step output 区分四种状态：流式输出 / 运行中 / 已完成无输出 / 已失败 / 已跳过 / 等待执行
- 工具调用以 `tool-trace` 列表渲染：`▸ search_history(query: 徒步) → 3 results · 280 ms`，failed 标红
- final-surface 加 **"在 Chat 中优化"** 按钮：跳到 `/chat?seed=帮我优化 #N（《标题》）...`
- workflow / dynamic 文案改写，强调各自的产品意义
- 移除 UI 上的 token / cost 显示（顶部卡片改成 Mode / Plan / Status / Revisions；step timeline 只剩 duration）

### 2. `frontend/src/views/Chat.vue`
- onMounted 时读 `route.query.seed`，自动填到输入框（不自动发送，让用户看一眼）
- 填完用 `router.replace` 清掉 query，避免刷新重新种入

### 3. `frontend/src/components/AppLayout.vue`
- sidebar 暂时移除"动态 Pipeline"独立项（Studio 内部 toggle 已经覆盖）

### 4. `frontend/src/router/index.ts`
- `/pipeline` 改成 redirect 到 `/?mode=dynamic`，老链接不 404

### 5. `frontend/src/api/agent.ts`
- 新增 `SubAgentToolEvent` 类型；`PipelinePlanStep` 加 `tool_events?`

### 6. 删除 `frontend/src/views/PipelineV2.vue`（被 Studio 合并模式取代）

---

## 测试

- pytest 41 → 46（新增 5 个 case：`aggregate_performance` 正常 / 空窗 / `get_calendar_conflicts` / `list_optimization_candidates` 两档）
- frontend `vue-tsc + vite build` 成功
- web_search 不打外部网络，未单测

---

## 仍未完成

- 真实 LLM 端到端跑一遍 chat agent（选题 → 排期 → 优化 → 提交日历）的全链路验证。需要你启 server，参考 `TEST_PLAN.md` 跑一遍
- 小红书真实发布尚未接入 chat agent 工具池（XHS_MCP 配置已就位，只缺一个 `publish_xiaohongshu(content_id)` 工具）
- workflow 模式仍是纯 prompt chaining，未加工具（按本次重定位的产品故事，刻意保持简单）

---

## 后续追加：Dynamic Pipeline 重新定位为研究型专用（B1）

把 dynamic 从"另一种生产模式"明确为"**研究型内容专用通道**"，让它在产品里有独立存在意义。

### 后端
- `src/api/schemas/agent.py` `PipelineRunRequest` 加 3 个字段：
  - `use_web_search: bool = True`
  - `use_history_search: bool = True`
  - `research_focus: str | None = None` （研究侧重提示，传给 planner）
- `src/api/services/dynamic_pipeline.py`
  - `PLANNER_SYSTEM_PROMPT` 重写：明确告诉 planner "用户选了 dynamic 就是要 researcher / fact_checker"，把研究步骤强引导到 plan 早期
  - `_make_plan` 把 `available_tools` / `research_focus` 注入 user prompt
  - `_default_plan` fallback 由 4 步纯 prompt 链改为 5 步研究型默认计划：researcher → strategy → writer → fact_checker → editor

### 前端
- `frontend/src/api/agent.ts` `PipelineRunPayload` 加 `use_web_search / use_history_search / research_focus` 字段
- `frontend/src/views/Studio.vue`
  - 默认 mode 改为 `workflow`（普通题入口默认快路径）
  - mode toggle 文案 "**内容生产线 · Workflow / 研究型 Pipeline · Dynamic**"
  - dynamic banner 改为 "研究型内容专用：Planner 自动调用 researcher / fact_checker"
  - Quick prompts 按 mode 切换：dynamic 模式预置 4 条研究型示例（横评、对比、盘点、理财筛选）
  - 左侧加 **Research Sources 面板**（仅 dynamic 显示）：
    - Web Search 开关 + 卡片说明（DuckDuckGo · 适合查时事 / 横评）
    - History Search 开关 + 卡片说明（本地内容库 · 复用过往沉淀）
    - 研究侧重输入框（可选 research_focus）
    - 顶部 pill 显示 `N/2 enabled`
  - signal-row 按 mode 区分：dynamic 模式第三卡变成 **Tool calls** 实时计数；workflow 模式第四卡变成 **Saved**（提示可去 Chat 优化）
  - timeline 给 researcher / fact_checker 步加 `is-research` 紫色基调 + 🔍 / 🛡 图标
  - step box 同样加 `is-research` 视觉强化 + "research" 标签徽章
  - timeline 每步右侧加 **`N tool calls` 浅紫胶囊**，工具调用次数一目了然

### 测试
- `tests/test_dynamic_pipeline.py::test_planner_fallback_on_invalid_json` 调整预期：默认 plan 的 agent 序列从 `[strategy, writer, editor, reviewer]` 改为 `[researcher, strategy, writer, fact_checker, editor]`
- 全套 46/46 仍然通过

### 产品故事最终成型

| Surface | 角色 | 适合 | 默认进入 |
|---|---|---|---|
| **Workflow** (Studio mode=workflow) | 写手 | 普通主题、批量产出 | ✅ 默认 |
| **Dynamic** (Studio mode=dynamic) | 研究员 | 横评、对比、有数字时间点的硬题 | URL 主动选择 |
| **Chat Agent** (`/chat`) | 主编 | 跨多篇优化、选题、排期 | sidebar 入口 |

三档边界清晰、互不替代、且每档对应真实运营场景。

---

## UI 微调（后续）

### `frontend/src/views/Studio.vue`
- Dynamic 模式 banner 标题和描述文案修正：去掉"搜外网"等未实现功能的描述，改为准确表述
- Studio 布局调整：`studio-grid` 使用 `grid-template-rows: 1fr`，右侧 `studio-center` 使用 `grid-template-rows: 1fr auto` 让 Pipeline Timeline card 撑满左侧高度
