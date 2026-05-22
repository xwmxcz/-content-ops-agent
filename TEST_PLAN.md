# 测试方案 · 2026-05-22

针对今天的改动，分**自动化测试**（已跑过）和**手动端到端测试**（你跑）。手测部分按"两人轮班"也能覆盖，每个用例预计 2-5 分钟。

---

## 一. 自动化测试（已通过）

### 1.1 后端 pytest 46/46

```bash
python -m pytest tests -q
```

新增 case 覆盖：

| case | 验证 |
|---|---|
| `test_aggregate_performance_returns_grouped_stats` | 按 type / style 聚合，top performer 排序正确 |
| `test_aggregate_performance_handles_empty_window` | 空 db 不爆，返回空结构 |
| `test_get_calendar_conflicts_returns_overlapping_events` | 窗口外的事件不返回 |
| `test_list_optimization_candidates_underperforming` | 互动率低于均值的内容才进候选 |
| `test_list_optimization_candidates_old_drafts` | 14 天以上的 draft 才进候选；新 draft 不进 |

未自动化但已 smoke test：

- chat agent 工具注册：16 个工具都能 `_build_tools` 出来
- storage 新接口在真 db 上运行（用 seed 数据）
- web_search 工具构造（不打网络）

### 1.2 前端 build

```bash
cd frontend && npm run build
```

`vue-tsc` + `vite build` 都通过，无类型错误。

---

## 二. 手动端到端测试

需要：

1. `python server.py` 在跑
2. `cd frontend && npm run dev` 在跑
3. 已经跑过 `python examples/seed_demo_data.py`（库里有 50+ 条带指标的内容）
4. `.env` 里至少一个 LLM provider 有有效 key（推荐 SiliconFlow，已配好）

### 2.1 Workflow 生产 → Chat 优化（核心闭环）

**目的**：验证产品定位"工作台生产 + Chat 优化"的体验是否丝滑。

**步骤**：
1. 浏览器打开 `http://localhost:5173/`
2. 顶部 toggle 切到 **"4 阶段 Workflow"**
3. 主题填："咖啡入门：一杯好咖啡需要什么"
4. 平台 = 小红书，风格 = 轻松，长度 = 中
5. 点"运行"

**预期**：
- ✅ banner 副标题写 "4 步标准生产线 ... 生成保存后，可一键跳到 Chat Agent 继续优化"
- ✅ 运行中按钮区变成蓝色进度条 + 红色"停止"按钮，运行按钮消失
- ✅ 4 步依次 strategy → writer → editor → reviewer，每步右侧显示 duration_ms
- ✅ 最终稿区出现，左上"已保存 #N"，右侧三个按钮：**"在 Chat 中优化"**、"复制"
- ✅ 点"在 Chat 中优化" → 跳到 `/chat`，输入框已经填好类似：
  > 帮我优化 #N（《...》）这篇内容：先调用 view_content 看一下当前版本，然后给出 2-3 条具体的改进方向，等我确认后再调 refine_content。
- ✅ 顶部出现 "已带入待优化提示，确认后点击发送" 提示
- ✅ 刷新页面后输入框是空的（query 已被清掉）

**点发送，期望 Agent 行为**：
- ✅ 调 `view_content(content_id=N)` → tool event 显示
- ✅ 不直接调 `refine_content`（要等用户确认）
- ✅ 给出 2-3 条改进建议（结构 / 语气 / 钩子等）
- ✅ 用户回 "OK，按第 1 和第 3 条改" → Agent 调 `refine_content` → 显示新 content_id

---

### 2.2 选题 Agent（chat 主菜）

**目的**：验证 chat agent 能基于真实数据做选题决策。

**步骤**：
1. `/chat` 页，新建会话
2. 输入：`看一下我们最近 30 天的内容表现，给我推 5 个下周该写的选题`

**预期工具调用序列**（Agent 自行决定，可能略有差异）：
1. `analyze_content_performance(days=30)` → 看到聚合数据
2. （可选）`web_search(query="...近期热点")`
3. `propose_topics(count=5, hint="...")` → 拿到选题情报
4. 最终回复一个 markdown 表，5 个选题，每个带：标题、平台、风格、推荐理由

**验证点**：
- ✅ Agent 解释了"为什么是这 5 个"——引用了聚合数据里的高互动 content_type 或低覆盖类目
- ✅ 没立刻调 `create_content`（要等用户挑）
- ✅ 选题不重复 seed 库里已有的标题（Agent 应该看到 `propose_topics` 返回的 `recently_published_titles`）

**反例**（如果出现说明 prompt 没走通）：
- ❌ 直接编 5 个选题不调 `analyze_content_performance`
- ❌ 直接调 `create_content` 把建议写进库
- ❌ 选题跟 seed 库里某条标题完全相同

---

### 2.3 发布编排（propose-then-commit）

**目的**：验证写入工具的人在回路。

**步骤**：
1. 接着上一个对话（已经有 5 个选题建议）
2. 输入：`帮我把过去一周内 5 篇带 metrics 的小红书排到下周一三五发`

**预期工具调用序列**：
1. `list_recent_contents` 或 `search_history` → 找候选 content_id
2. `propose_publishing_schedule(content_ids=[...], start_date='2026-05-25', end_date='2026-05-31', cadence='mwf')` → 拿到 plan
3. Agent 把 plan 渲染为 markdown 表给用户看
4. **等待**用户确认 — 不直接 commit

**用户回**：`OK，开始排吧`

**预期**：
1. Agent 调 `commit_publishing_schedule(plan=[...])` → 显示 saved 列表
2. Agent 回复"已写入日历"

**手动验证**：
- 切到 `/calendar` 页 → 应该看到下周一三五新增的事件
- 直接刷库验证：
  ```bash
  python -c "from src.storage import ContentStore; print(ContentStore().get_calendar_events())"
  ```

**反例**：
- ❌ Agent 没经过用户确认就 commit
- ❌ propose 时跟 seed 已占用的日期撞日（应该自动跳过）

---

### 2.4 优化候选发现（新工具 `find_optimization_candidates`）

**目的**：验证 Agent 能主动找出"哪些内容值得改"。

**步骤**：
1. 新建会话
2. 输入：`帮我看看库里哪些内容值得优化，按数据表现差的优先`

**预期**：
- ✅ 调 `find_optimization_candidates(criteria='underperforming')`
- ✅ 给出 3-5 个候选，每个带：标题、views、engagement_rate、reason
- ✅ Agent 主动加自己的判断："#X 这条互动率比均值低 30%，可能是钩子太弱，建议重写开头三行"
- ✅ 不直接调 `refine_content`

**变体**：
- "哪些 draft 太久没动了？" → 应该用 `criteria='old_drafts'`
- "最近的 draft 有哪些？" → 应该用 `criteria='recent_drafts'`

---

### 2.5 Dynamic Pipeline（硬题路径）

**目的**：验证 dynamic pipeline 在真正需要外部资料的场景下会触发 researcher / fact_checker。

**步骤**：
1. Studio 顶部 toggle 切到 **"研究型 Pipeline · Dynamic"**
2. 此时左侧应**新增 Research Sources 面板**：
   - Web Search 开关（默认开）
   - History Search 开关（默认开）
   - 研究侧重输入框
   - 顶部右上 `2/2 enabled` 灰胶囊
3. 顶部 banner 应该是 "研究型内容专用：Planner 自动调用 researcher / fact_checker"
4. 主题：`对比 ChatGPT、Claude、Gemini 在 2025 年内容创作场景的真实差异`
5. 研究侧重填：`重点对比模型质量、价格和上手难度`
6. 关键词：`AI对比, 模型评测`
7. 运行

**预期**：
- ✅ Plan 出现 4-7 步，**早期就有 researcher**（index 1 或 2），写作前还有 fact_checker
- ✅ Timeline 上 researcher / fact_checker 步显示 **🔍 / 🛡 图标 + 紫色边框 + research 标签**
- ✅ 右侧 step box 同样有紫色凸显 + 顶部 "research" 小徽章
- ✅ researcher / fact_checker 的 tool-trace 区显示 `▸ search_history(...)` 和 `▸ web_search(...)` 调用
- ✅ Timeline 每行右侧出现 `N tool calls` 浅紫胶囊
- ✅ 顶部 stat row 显示 "Mode: Research / Plan: 5+ / Tool calls: N+ / Revisions: 0 或 1+"
- ✅ 总耗时 60-180 秒（取决于 LLM 速度 + 工具调用次数）

**变体**（关掉 Web Search）：
- 把 Web Search 开关关掉，再跑一次
- 预期：Tool call 列表里不再出现 `web_search`，只有 `search_history`
- 顶部胶囊变成 `1/2 enabled`

**对比**：
- 同一个主题切到 workflow → 4 步固定，**绝不会**走到 researcher，故事会更"飘"
- 同一个主题切回 dynamic + 关掉所有研究开关 → 仍会跑研究型 plan，但 web 路径被 planner 跳过

---

### 2.6 边界 / 容错

**A. Stop 按钮（部分中断）**
1. 跑一个 dynamic 任务
2. 中途点 "停止"
3. 预期：UI 立刻断开 SSE，进度条停下，状态变 `stopped`，能立刻再点运行下一次。后端 sub-agent 还会跑完当前 step，但下一步不会启动（实际是 SSE 断开后前端不再接收事件，后端继续跑完 plan 但用户不可见）

**B. Reviewer 输出长（max_tokens 撞顶）**
1. dynamic mode，主题选信息密集型（如 "盘点 2026 年最重要的 10 个 AI 产品发布"）
2. 预期：reviewer 的 step_token 持续累加超过 1024 tokens 仍然能正常 step_complete，不再 `LLM streaming failed`

**C. SiliconFlow 429**
- 短时间连续触发 5+ 次运行 → 部分会 429。无需修复，验证错误信息可读：UI 显示"步骤失败：..."，server 控制台有 `[litellm.stream] iteration failed: ...`

**D. Chat 工具失败兜底**
- 如果某个工具实现报错，chat agent 应当：
  - tool_event 标 failed，UI 显示红色
  - Agent 看到错误信息后不会无限重试同一工具（chat_agent.py 有 `MAX_FAILURES_PER_TOOL=2`）

---

## 三. 测试 checklist（演示前一次性跑完）

| # | 用例 | 预期 |
|---|---|---|
| 1 | pytest 全跑 | 46/46 通过 |
| 2 | npm run build | 通过无类型错误 |
| 3 | seed 后访问 /chat | seed 出来的 demo thread 在左侧能看到 |
| 4 | Workflow 生成 + 在 Chat 中优化 | 流程贯通，输入框自动填好 |
| 5 | 选题 Agent 三件套（analyze / web_search / propose_topics） | 都被调用，给出 markdown 选题表 |
| 6 | 发布编排 propose-then-commit | propose 不写库，confirm 后 commit 生效 |
| 7 | find_optimization_candidates | 三种 criteria 都能跑出合理候选 |
| 8 | Dynamic 硬题主题触发 researcher | plan 包含 researcher / fact_checker，tool_trace 可见 |
| 9 | reviewer 长输出 | 不再随机 streaming failed |
| 10 | Stop 按钮 | UI 立刻断 SSE，能立刻再次发起 |

---

## 四. 已知遗留 / 故意不修

- workflow 模式仍是纯 prompt chaining，没加工具（产品定位刻意保持快和确定）
- 小红书真实发布未接入 chat agent 工具池（基础设施已具备，待后续 30 分钟可接）
- chat agent "Stop" 在 dynamic 路径只断前端 SSE，不真正中断后端 step（NEXT_STEPS 第 3B 节，留给以后做 `DELETE /api/agent/runs/{id}` 端点）
- DuckDuckGo HTML 端点：偶发解析失效（每年 1-2 次），失败时返回空数组、Agent 会自动放弃这条工具调用，不阻塞主流程
- 中文标题在 Windows cmd 显示乱码（数据库 UTF-8 正确，纯终端显示问题）

---

## 五. 跑测试时遇到问题怎么办

| 现象 | 大概率原因 | 处理 |
|---|---|---|
| Agent 不调 `propose_topics` 直接编选题 | LLM 没遵守 system prompt | 重启 server（确保改后的 prompt 加载到），换更强的模型 |
| `web_search` 一直返回 `[]` | DuckDuckGo 临时不通 / 解析失效 | 等几分钟重试；如长期失效，可临时把 researcher prompt 里 web_search 提示注释掉 |
| `commit_publishing_schedule` 报 "content not found" | content_id 不存在 | 让 Agent 先 `search_history` 或 `list_recent_contents` 拿真实 id |
| reviewer 仍然 `streaming failed` | provider 完全断流没给任何 chunk | 已经会 fallback 到非流式；如果非流式也失败 → 真的是 provider 问题，换 provider |
| Stop 按钮点完后再点"运行"无反应 | 状态没切回 idle | 已修，如果再现请记下重现步骤 |
