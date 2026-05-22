# NEXT_STEPS.md

明天接着开发的清单。按"演示价值 × 工作量"排序。

---

## 当前状态（截至本文档写入时）

- Git: `main` 分支干净，已推到 GitHub。最近 5 个 commit:
  - `c282c96` Constrain list/detail panels with internal scroll on Chat, Refine, History
  - `d46f4a2` Add dynamic Plan-then-Execute pipeline with SSE streaming
  - `39b5f95` Redesign frontend in Linear/Vercel style
  - `df8b1f8` Fix Studio responsive layout in 1180-1440 viewport range
  - `33d1965` Add plan-then-execute, retry loop, and search_history to chat Agent
- 测试: **41/41 通过**（30 基线 + 5 chat-agent + 6 dynamic pipeline）
- 前端 build: 通过（`npm run build` = `vue-tsc + vite build`）
- 后端 dynamic pipeline 已可用：
  - `POST /api/agent/runs` → 返回 `{run_id}`
  - `GET /api/agent/runs/{id}` → 查 run 详情
  - `GET /api/agent/runs/{id}/stream` → SSE 事件流
- **缺：前端没接 SSE**，Studio 页还在用旧的 `/jobs/agent-run` polling

---

## 1. 接 Pipeline v2 前端（**优先级最高**）

后端的 dynamic pipeline 已经全部就绪，缺的就是前端来订阅 SSE 把它演示出来。这是面试的主菜。

### 1A. 路径选择（之前定的）

**走路径 1**：新建独立页面 `/pipeline`，旧 Studio.vue 不动。
- 演示时双 tab 对比 workflow vs agent
- 风险最低，旧页保护好
- 工时 1.5 小时

### 1B. 要做的文件

| 文件 | 改动 |
|---|---|
| `frontend/src/views/PipelineV2.vue` | **新建**。布局类似 Studio，但右侧改"plan timeline + 流式 token + token/cost 计数器"。订阅 SSE。 |
| `frontend/src/router/index.ts` | 加路由 `{ path: '/pipeline', component: () => import('../views/PipelineV2.vue') }` |
| `frontend/src/components/AppLayout.vue` | sidebar nav 加一项"动态 Pipeline"，icon 用 `MagicStick` 或 `Cpu` |

### 1C. 关键 UI 模块（按优先级）

1. **Plan Timeline**（顶部）：横向步骤条，每步显示 agent_id + status + duration_ms。被 revision 新增的步用 Linear 紫高亮。
2. **流式 token 区**（中间 main）：每个 step 一个 box，`step_token` 事件追加到对应 step 的输出区，自动滚动到底。
3. **Token / Cost 计数器**（顶部 stat row）：实时累加 `step_complete` 事件里的 tokens 和 cost。
4. **Final Content 区**（最下方）：`run_complete` 后显示，可复制。

### 1D. SSE 订阅核心代码

```ts
import { createPipelineRun, pipelineStreamUrl, type PipelinePlanStep } from '../api/agent'

async function runPipeline() {
  const { run_id } = await createPipelineRun(payload)
  const evt = new EventSource(pipelineStreamUrl(run_id))

  evt.addEventListener('plan_ready', e => { plan.value = JSON.parse(e.data).plan })
  evt.addEventListener('step_start', e => updateStep(JSON.parse(e.data), 'running'))
  evt.addEventListener('step_token', e => appendToken(JSON.parse(e.data)))
  evt.addEventListener('step_complete', e => updateStep(JSON.parse(e.data), 'completed'))
  evt.addEventListener('step_failed', e => updateStep(JSON.parse(e.data), 'failed'))
  evt.addEventListener('plan_revised', e => { plan.value = JSON.parse(e.data).plan })
  evt.addEventListener('run_complete', e => {
    finalContent.value = JSON.parse(e.data).final_content
    evt.close()
  })
  evt.addEventListener('run_failed', e => { evt.close() })
}
```

### 1E. 验证

```bash
# 后端
"/f/miniconda/envs/only/python.exe" server.py

# 前端
cd frontend && npm run dev

# 浏览器 → http://localhost:5173/pipeline
# 输入"周末徒步路线推荐" + 小红书 + 专业风格 → 期望：
#   1. 立刻出现 plan timeline（4-5 步）
#   2. 每步状态依次变 ●，token 实时追加
#   3. reviewer 步如果给低分，timeline 出现 +1 step (revision)
#   4. 顶部 token / cost 计数器持续累加
#   5. 完成后 final 区显示完整内容
```

---

## 2. 演示前的事实排查（**必做**）

### 2A. 真实 LLM 跑一次

测试用的是 fake LLM，演示用 deepseek（你 .env 默认配置）。**演示前 1 小时务必跑一次完整真实 LLM**，看 plan 质量是否稳定。

```bash
"/f/miniconda/envs/only/python.exe" server.py
# 浏览器试 Pipeline v2，跑两到三个不同主题
```

如果 plan 质量不稳定，临时降级：
- 在 `src/utils/config.py` 加 `PIPELINE_DYNAMIC_PLAN=true`，false 时 `dynamic_pipeline.py` 直接调 `_default_plan()` 跳过 LLM

### 2B. 长 connection 兼容

SSE 端点 `time.time() + 600` 硬上限 10 分钟。演示用的小红书内容大约 60 秒以内，没问题。但如果你演示长内容（博客/视频脚本），可能需要把上限调大。

### 2C. 演示话术清单

| 场景 | 话术 |
|---|---|
| 打开 Chat 页 | "这是真 Agent，工具循环 + 自我规划 + 失败重试" |
| 打开 Studio v1（旧） | "这是 prompt-chaining workflow，4 步固定顺序" |
| 打开 Pipeline v2（新） | "这是动态 Agent — Planner 自己决定要哪几步、什么顺序、要不要回头改" |
| 中途触发 revision | "看，reviewer 给了 70 分，Planner 自己加了一步 editor 重写" |
| 顶部 token 计数器 | "每一次 LLM 调用的 prompt/completion tokens 都在埋点，价格也算了" |

---

## 3. 工程化补充（如果时间富余）

### 3A. 修两个会被现场问出来的暗坑（半天）

- **`chat_agent.py:124` 的 `for _ in range(MAX_LOOPS)`** 已经改成 8 + per-tool 上限，但缺一个时长熔断（30 秒）。面试官问"会不会死循环？"时这个是兜底答案。
- **`count_inflight_jobs`** 在 RQ 模式下基于 `Job.status` 行数判断容量，但 worker 进程崩溃不会回写状态，job 卡在 `running` 永久占用名额。最少加个"started_at 超过 5 分钟视为僵尸"的清理逻辑。

### 3B. 可取消的长任务（半天）

新增 `DELETE /api/agent/runs/{run_id}` 端点 → 把 run.status 设成 `cancelling`，pipeline 在每步开始前检查状态然后 `raise CancelledError`。前端 PipelineV2.vue 加红色 "Cancel" 按钮。

### 3C. README 截图更新（1 小时）

`docs/screenshots/` 里的 chat.png 和 studio.png 都是旧版米黄风。重拍：
- chat.png → 现 Linear 风 + plan-board + tool-event 折叠卡
- studio.png → 现 Linear 风 4-stage pipeline
- 新增 pipeline.png → Pipeline v2 的 timeline + 流式 token

---

## 4. 已知小问题（不阻塞演示，看时间）

### 4A. `agent_pipeline.py:_derive_title` 在中文 markdown 上经常失败

如果 LLM 返回的第一行是 `## 周末徒步路线推荐`，title 会变成 `# 周末徒步路线推荐` —— 已经修过一些，但仍偶发。修法：在 `_derive_title` 里 strip 掉 `#`、`*`、`-`、`【】` 这些 markdown 装饰符。

### 4B. Element Plus bundle 909KB

build 警告里那个，演示用没影响。如果想优化：vite.config.ts 配 `manualChunks` 把 Element Plus 拆包，或者按需引入 Element Plus 组件（element-plus auto-import plugin）。**面试不会问这个**，跳过。

### 4C. AppLayout sidebar 没做 active nav 的视觉强化

designer agent 改完后 active 状态的对比度比之前弱。如果你看着不顺眼，把 `.nav-link.active` 的 `background` 从 `var(--c-accent-soft)` 改成 `rgba(110, 86, 207, 0.16)`，文字加 `font-weight: 600`。

---

## 5. 文件路径速查

| 概念 | 文件 |
|---|---|
| 后端 dynamic pipeline 主类 | `src/api/services/dynamic_pipeline.py` |
| Sub-agent 池 | `src/api/services/sub_agents.py` |
| Chat agent | `src/api/services/chat_agent.py` |
| 4-stage workflow（旧） | `src/api/services/agent_pipeline.py` |
| LLM 客户端 + streaming | `src/llm/litellm_client.py` |
| ORM | `src/storage/content_store.py` |
| Pipeline 路由 | `src/api/routes/agent.py`（POST /runs, GET /runs/{id}/stream） |
| 前端 API 类型 | `frontend/src/api/agent.ts` |
| 设计 token | `frontend/src/styles.css` |
| 主壳 | `frontend/src/components/AppLayout.vue` |
| 计划文件（参考） | `C:\Users\17832\.claude\plans\sparkling-frolicking-mccarthy.md` |

---

## 6. 命令速查

```bash
# 激活环境
conda activate only
cd F:/VSworkspace/AI-agent/content-ops-agent

# 后端
python server.py            # 0.0.0.0:8000
python -m pytest tests -q   # 41/41
python -m pytest tests/test_dynamic_pipeline.py -q  # 仅新 pipeline 测试

# 前端
cd frontend
npm run dev                 # 5173
npm run build               # vue-tsc + vite build

# Git
git status --short
git log --oneline -10
git diff HEAD~3..            # 看这次会话三个 commit 的总和
```

---

明天先做 **第 1 节** —— Pipeline v2 前端。1.5 小时拿下后，演示 narrative 就完整了。
