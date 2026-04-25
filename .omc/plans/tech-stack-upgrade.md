# Content Ops Agent 技术栈现代化升级计划

## 需求摘要

将 content-ops-agent 从原型阶段升级为生产级架构。当前技术栈存在以下核心问题：

1. **Streamlit 前端无法扩展** — `src/web/app.py` 使用 Streamlit 多页路由，每次交互全页重渲染，无组件复用，无法做实时流式对话
2. **自定义 LLM 客户端维护成本高** — 4 个独立客户端 (`src/llm/claude_client.py`, `src/llm/openai_compatible.py`, `src/llm/siliconflow_client.py`) + 手动工厂模式，模型更新需逐个修改
3. **SQLite 不适合生产环境** — `src/storage/content_store.py:67-71` 硬编码 SQLite 路径，无并发支持
4. **SQLAlchemy 旧式写法** — `src/storage/content_store.py:8` 使用已废弃的 `declarative_base()`，`content_store.py:15-62` 使用 `Column()` 而非 2.0 的 `mapped_column()`
5. **LangGraph checkpointer 不持久化** — `src/graph/workflow.py:128-131` 使用 `MemorySaver`，重启丢失所有对话
6. **FastAPI 已声明未使用** — `requirements.txt:6` 声明了 `fastapi>=0.115.0` 但无任何路由代码
7. **模型标识过时** — `src/utils/config.py:20` 默认 `claude-3-5-sonnet-20241022`，`src/llm/factory.py:37` 同步硬编码
8. **CLI 将被移除** — `src/main.py` Rich CLI 循环和 `run.py` 启动脚本

## 用户决策记录

| 领域 | 当前 | 目标 |
|------|------|------|
| 后端 | 无 API 层 | FastAPI REST API |
| 前端 | Streamlit (Python 全栈) | Vue 3 + Vite + Element Plus |
| LLM | 自定义工厂 + requests 同步 | litellm 统一接口 |
| 数据库 | SQLite + SQLAlchemy 旧式 | PostgreSQL + SQLAlchemy 2.0 |
| CLI | Rich 交互式 | **移除** |
| 部署 | 单进程 | 前后端分离 |
| LangGraph | MemorySaver (内存) | PostgreSQL checkpointer |

## RALPLAN-DR 摘要

### 原则 (5)

1. **渐进式迁移** — 每个 Phase 完成后可独立验证，不跨 Phase 依赖
2. **接口优先** — 先定义 API contract (OpenAPI)，前端后端并行开发
3. **数据安全** — 迁移过程不丢数据，SQLite→PG 有回滚路径
4. **最小破坏** — 保留 LangGraph agent 核心逻辑 (`src/graph/workflow.py`)，仅替换外围适配层
5. **可测试性** — 每个 Step 有明确的验证命令

### 决策驱动因素 (Top 3)

1. **生产可用性** — 当前架构无法部署到生产环境（SQLite 并发、Streamlit 重渲染、内存 checkpointer）
2. **维护成本** — 4 个自定义 LLM 客户端 + 旧式 SQLAlchemy 每次升级都需逐文件修补
3. **用户体验** — Streamlit 无法实现实时流式对话、组件复用、前端状态管理

### 可选方案分析

#### 选项 A: 全面重构 (推荐)

全量替换：FastAPI + Vue 3 + PostgreSQL + litellm，移除所有旧代码。

- **Pros**: 架构一致性好，无技术债残留，长期维护成本最低
- **Cons**: 工作量大（4 个 Phase），迁移期间旧系统不可用

#### 选项 B: 渐进式共存

保留 Streamlit 作为备用，FastAPI + Vue 3 新系统并行运行，逐步切换。

- **Pros**: 可回退，风险更低
- **Cons**: 双系统维护成本高，SQLite 和 PG 数据同步问题，Streamlit 代码仍需维护

**选项 B 无效理由**: Streamlit 和 Vue 3 共存意味着要维护两套前端 + 两套路由 + 数据同步，复杂度超过全面重构。项目尚无生产用户，无回退必要。

## 验收标准 (100% 可测试)

1. `curl http://localhost:8000/api/health` 返回 `{"status": "ok"}`，FastAPI docs `/docs` 可访问
2. `curl -X POST http://localhost:8000/api/content/generate -d '{"topic":"测试","content_type":"xiaohongshu"}'` 返回 201 + content_id
3. Vue 3 SPA `npm run build` 零错误，`npm run dev` 可访问所有 6 个页面
4. `litellm.completion(model="deepseek/deepseek-chat", ...)` 4 个提供商均返回有效响应
5. PostgreSQL 中 `SELECT count(*) FROM contents` 等于迁移前 SQLite 的 count
6. LangGraph 对话重启后通过 `GET /api/agent/history?thread_id=xxx` 可恢复
7. `src/main.py`, `run.py`, `src/web/`, `src/llm/claude_client.py`, `src/llm/openai_compatible.py`, `src/llm/siliconflow_client.py` 已删除
8. `alembic upgrade head` 成功，`alembic downgrade -1` 可回滚
9. SSE 端点 `GET /api/agent/stream?message=xxx` 返回 `text/event-stream`，逐 token 推送
10. CORS 配置允许 `http://localhost:5173` (Vite dev) 访问后端

---

## 实施步骤

### Phase 1: 后端基础设施 (FastAPI + SQLAlchemy 2.0 + PostgreSQL)

> 目标：FastAPI 服务可启动，PostgreSQL 数据读写正常，所有 CRUD API 可用

#### Step 1.1: 项目结构重组 + 依赖更新

**新建文件:**
- `src/api/__init__.py`
- `src/api/main.py` — FastAPI app, CORS, lifespan (PG 连接池初始化)
- `src/api/dependencies.py` — `get_db_session()`, `get_llm_client()`, `get_agent()` 依赖注入
- `src/api/routes/__init__.py`
- `src/api/schemas/__init__.py`

**修改文件:**
- `requirements.txt` — 替换为:
  ```
  fastapi>=0.115.0
  uvicorn[standard]>=0.32.0
  pydantic>=2.10.0
  python-dotenv>=1.0.0
  sqlalchemy[asyncio]>=2.0.0
  asyncpg>=0.30.0
  alembic>=1.14.0
  litellm>=1.60.0
  httpx>=0.28.0
  sse-starlette>=2.0.0
  langgraph>=0.4.0
  langgraph-checkpoint-postgres>=2.0.0
  langchain>=0.3.0
  langchain-core>=0.3.0
  ```
  移除: `anthropic`, `requests`, `streamlit`, `rich`, `pandas`, `plotly`, `langchain-anthropic`

**验证**: `pip install -r requirements.txt` 成功，`python -c "from src.api.main import app; print(app.title)"` 输出应用名

#### Step 1.2: SQLAlchemy 2.0 迁移

**当前问题定位:**
- `src/storage/content_store.py:8` — `from sqlalchemy.ext.declarative import declarative_base` (已废弃)
- `src/storage/content_store.py:12` — `Base = declarative_base()` (旧式)
- `src/storage/content_store.py:15-34` — `Column(Integer, primary_key=True)` (旧式)
- `src/storage/content_store.py:64-71` — `ContentStore.__init__` 硬编码 `sqlite:///{db_path}`
- `src/storage/content_store.py:74-75` — 同步 `SessionLocal = sessionmaker(bind=self.engine)`

**新建文件:**
- `src/storage/base.py` — 新式 Base: `class Base(DeclarativeBase): pass`
- `src/storage/async_engine.py` — `create_async_engine(DATABASE_URL)`, `async_sessionmaker`

**重写 `src/storage/content_store.py`:**
- ORM 模型: `Column()` → `mapped_column()`, 添加 `Mapped[int]` 类型注解
- `Content.id: Mapped[int] = mapped_column(primary_key=True)`
- `Content.title: Mapped[Optional[str]] = mapped_column(Text)`
- 所有 `session.query(Content).filter(...)` → `await session.execute(select(Content).where(...))`
- `ContentStore` → `AsyncContentStore`，所有方法加 `async`/`await`
- 构造函数接受 `DATABASE_URL`，不再硬编码 SQLite

**验证**: `python -c "from src.storage.base import Base; print(Base.metadata)"` 无报错

#### Step 1.3: PostgreSQL + Alembic 配置

**新建文件:**
- `alembic.ini` — 配置 `sqlalchemy.url` 指向 PG
- `alembic/env.py` — async migration 配置 (`run_async_migrations`)
- `alembic/versions/001_initial.py` — 初始 migration (autogenerate)

**修改文件:**
- `src/utils/config.py:30` — `DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://localhost/content_ops")`
- 新增 `ASYNC_DATABASE_URL` 属性

**新建脚本:**
- `scripts/migrate_sqlite_to_pg.py` — 读取 SQLite → 写入 PG:
  1. 读取 `data/content_ops.db` 所有表数据
  2. 通过 PG async engine 写入对应表
  3. 验证 count 一致
  4. 输出迁移报告

**验证**: `alembic upgrade head` 成功, `alembic downgrade -1` 成功, PG 中 `SELECT * FROM contents` 有数据

#### Step 1.4: FastAPI API 层 — Pydantic Schemas

**新建文件:**
- `src/api/schemas/content.py`:
  ```python
  class GenerateRequest(BaseModel):
      topic: str
      content_type: ContentType  # "xiaohongshu"|"weibo"|"blog"|"video_script"|"twitter"
      style: ContentStyle = "casual"
      keywords: Optional[list[str]] = None
      length: Optional[str] = "medium"
      provider: Optional[str] = None  # "claude"|"siliconflow"|"deepseek"|"moonshot"
      model: Optional[str] = None
      temperature: float = 0.7
      max_tokens: int = 2048

  class RefineRequest(BaseModel):
      content_id: int
      instruction: Optional[str] = None
      new_style: Optional[str] = None
      provider: Optional[str] = None
      model: Optional[str] = None

  class ContentResponse(BaseModel):
      id: int
      title: Optional[str]
      content: str
      content_type: str
      style: str
      tags: Optional[list[str]]
      status: str
      created_at: Optional[str]
  ```
- `src/api/schemas/calendar.py` — `CalendarEventCreate`, `CalendarEventResponse`
- `src/api/schemas/agent.py` — `ChatRequest(message: str, thread_id: Optional[str])`
- `src/api/schemas/models.py` — `ProviderInfo`, `ModelInfo`

**验证**: `python -c "from src.api.schemas.content import GenerateRequest; print(GenerateRequest.model_json_schema())"` 输出有效 JSON Schema

#### Step 1.5: FastAPI 路由实现

**当前功能映射 (Streamlit → API):**

| Streamlit 页面 | API 路由 |
|---------------|---------|
| `generate_page.py:204-299` 生成按钮 | `POST /api/content/generate` |
| `generate_page.py:306-318` 标题生成 | `POST /api/content/titles` |
| `refine_page.py:181-243` 改写 | `POST /api/content/refine` (instruction) |
| `refine_page.py:245-302` 风格切换 | `POST /api/content/refine` (new_style) |
| `refine_page.py:304-335` 标题优化 | `POST /api/content/titles` (content_id) |
| `refine_page.py:337-369` SEO | `POST /api/content/seo` |
| `calendar_page.py` 添加事件 | `POST /api/calendar/events` |
| `calendar_page.py` 查看日历 | `GET /api/calendar/events?days=7` |
| `calendar_page.py` 批量生成 | `POST /api/calendar/batch-week` |
| `stats_page.py:29-43` 统计指标 | `GET /api/stats` |
| `app.py:82-136` 首页最近内容 | `GET /api/content?limit=5` |
| `history_page.py` 历史列表 | `GET /api/content?status=&content_type=&limit=50` |
| Agent 对话 (无对应) | `POST /api/agent/chat` + `GET /api/agent/stream` |

**新建路由文件:**
- `src/api/routes/content.py` — 内容 CRUD + 生成/打磨/SEO/标题
- `src/api/routes/calendar.py` — 日历事件 CRUD + 批量生成
- `src/api/routes/stats.py` — 统计聚合
- `src/api/routes/agent.py` — Agent 对话 (同步 + SSE 流式)
- `src/api/routes/models.py` — 可用模型列表 (从 litellm 动态获取)
- `src/api/routes/health.py` — 健康检查

**修改 `src/api/main.py`:**
- 注册所有路由前缀
- CORS middleware: `allow_origins=["http://localhost:5173"]`
- lifespan: 初始化 PG 连接池

**验证**: `uvicorn src.api.main:app --reload` 启动成功, `/docs` 可见所有端点, `curl /api/health` 返回 200

#### Step 1.6: LangGraph 持久化升级

**当前问题定位:**
- `src/graph/workflow.py:7` — `from langgraph.checkpoint.memory import MemorySaver`
- `src/graph/workflow.py:128` — `checkpointer = MemorySaver()` (重启丢失)
- `src/graph/workflow.py:86-99` — `ChatAnthropic` / `ChatOpenAI` fallback (需替换为 litellm)
- `src/graph/workflow.py:141-152` — `chat()` 同步方法 (需改为 async)

**修改 `src/graph/workflow.py`:**
- `MemorySaver` → `AsyncPostgresSaver.from_conn_string(DATABASE_URL)`
- `ChatAnthropic` → `ChatLiteLLM` (from langchain-litellm) 或直接用 litellm
- `ContentOpsAgent.chat()` → `async def achat()`
- `ContentOpsAgent.stream()` → `async def astream()`
- 新增 `aget_history()` 方法读取对话历史

**新增依赖:**
- `langgraph-checkpoint-postgres>=2.0.0`
- `langchain-litellm` (如存在) 或自定义 ChatLiteLLM 适配

**验证**: Agent 对话重启后 `GET /api/agent/history?thread_id=test` 返回历史消息

### Phase 2: LLM 客户端迁移 (litellm)

> 目标：所有 LLM 调用通过 litellm 统一接口，移除 4 个自定义客户端

#### Step 2.1: litellm 统一客户端

**当前架构问题:**
- `src/llm/claude_client.py:9` — 硬编码 `model="claude-3-5-sonnet-20241022"` (过时)
- `src/llm/openai_compatible.py:53` — 手动 `requests.post()` (同步, 无重试)
- `src/llm/siliconflow_client.py:60-82` — 自带重试但 `time.sleep()` 阻塞 (同步)
- `src/llm/factory.py:37-51` — if/elif 分支逐个创建客户端

**新建文件:**
- `src/llm/litellm_client.py`:
  ```python
  import litellm

  class LiteLLMClient:
      """统一 LLM 客户端"""
      async def generate(self, model: str, messages: list[dict],
                         temperature: float = 0.7, max_tokens: int = 2048) -> str:
          response = await litellm.acompletion(
              model=model, messages=messages,
              temperature=temperature, max_tokens=max_tokens
          )
          return response.choices[0].message.content

      def get_available_models(self) -> dict[str, list[dict]]:
          """返回各提供商可用模型列表"""
          ...
  ```

**修改 `src/utils/config.py`:**
- `CLAUDE_MODEL` 默认值: `"claude-3-5-sonnet-20241022"` → `"claude-sonnet-4-6"`
- 新增 `LITELLM_MODEL_MAP` 映射表:
  ```python
  LITELLM_MODEL_MAP = {
      "claude": "claude-sonnet-4-6",          # litellm 原生支持 Anthropic
      "siliconflow": "openai/Qwen/Qwen2.5-7B-Instruct",  # OpenAI 兼容前缀
      "deepseek": "deepseek/deepseek-chat",   # litellm 前缀
      "moonshot": "moonshot/moonshot-v1-8k",  # litellm 前缀
  }
  ```
- `SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"` 保留，litellm 通过 `api_base` 参数传入

**修改 `src/llm/factory.py`:**
- 简化为: `LLMFactory.create()` → 返回 `LiteLLMClient` 实例
- `get_supported_providers()` 从配置读取

**修改 `src/tools/content_generator.py:30-35`:**
- `LLMFactory.create_client(provider, api_key, model)` → `LiteLLMClient()`
- `self.client.generate(system_prompt, user_prompt, ...)` → `await self.client.generate(model=self.litellm_model, messages=[...], ...)`

**修改 `src/tools/content_tools.py` 所有 @tool 函数:**
- 每个 tool 内的 `ContentGenerator()` → 注入 async `LiteLLMClient`
- `generator.client.generate(system_prompt, user_prompt)` → `await llm.generate(model, messages)`
- 注意: LangGraph `@tool` 需要 async 支持，使用 `@tool` + `async def`

**修改 `src/tools/calendar_tools.py:70-99`:**
- `batch_generate_week` 内的 `generator.generate(request)` → async 调用

**验证**: 4 个提供商各执行一次 `litellm.acompletion()` 均返回有效文本

#### Step 2.2: 移除旧客户端

**删除文件:**
- `src/llm/claude_client.py`
- `src/llm/openai_compatible.py`
- `src/llm/siliconflow_client.py`

**修改文件:**
- `src/llm/base.py` — 简化接口: `generate()` 签名改为 `(model, messages, **kwargs)`
- `src/llm/__init__.py` — 导出 `LiteLLMClient` 替代 `LLMFactory`

**保留:**
- `src/llm/base.py` (接口适配层)
- `src/llm/factory.py` (简化为 LiteLLMClient 创建)

**验证**: `python -c "from src.llm import LiteLLMClient; print(LiteLLMClient)"` 成功，旧客户端 import 全部报错 (确认已移除)

### Phase 3: Vue 3 前端 (Vite + Element Plus)

> 目标：Vue 3 SPA 完全替代 Streamlit，所有功能对等

#### Step 3.1: 项目初始化

```bash
cd content-ops-agent
npm create vite@latest frontend -- --template vue-ts
cd frontend
npm install element-plus @element-plus/icons-vue vue-router pinia axios @vueuse/core echarts vue-echarts
```

**新建 `frontend/vite.config.ts`:**
```typescript
export default defineConfig({
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true }
    }
  }
})
```

**验证**: `npm run dev` 启动成功，浏览器打开 `http://localhost:5173`

#### Step 3.2: 项目骨架

**新建文件结构:**
```
frontend/src/
├── api/
│   ├── index.ts          — axios.create({ baseURL: '/api' }) + 拦截器
│   ├── content.ts        — generateContent, refineContent, getContentList, getContent, deleteContent
│   ├── calendar.ts       — addEvent, getEvents, batchGenerateWeek
│   ├── stats.ts          — getStats
│   └── agent.ts          — chat, streamChat (SSE)
├── views/
│   ├── Home.vue          — 首页: 快速入口 + 最近内容
│   ├── Generate.vue      — 对应 generate_page.py 全部功能
│   ├── Refine.vue        — 对应 refine_page.py 全部功能 (改写/风格/标题/SEO 四个 tab)
│   ├── Calendar.vue      — 对应 calendar_page.py (日历视图 + 事件)
│   ├── History.vue       — 对应 history_page.py (列表 + 筛选 + 搜索)
│   ├── Stats.vue         — 对应 stats_page.py (ECharts 图表)
│   └── Chat.vue          — 新增: Agent 对话 (SSE 流式)
├── components/
│   ├── AppLayout.vue     — Element Plus Container + Aside 侧栏导航
│   ├── ModelSelector.vue — 提供商+模型+参数选择器 (复用于 Generate/Refine)
│   └── ContentCard.vue   — 内容卡片组件
├── stores/
│   ├── content.ts        — Pinia: 内容列表 + 当前内容 + CRUD actions
│   └── model.ts          — Pinia: 可用模型列表 + 当前选择
├── router/
│   └── index.ts          — 6 页面 + Chat 路由
├── App.vue
└── main.ts               — Element Plus 全局注册
```

**验证**: 所有空页面路由可访问，侧栏导航切换正常

#### Step 3.3: 页面实现 — 生成 (Generate.vue)

**功能映射 (来自 `src/web/pages/generate_page.py`):**
- `generate_page.py:80-107` 提供商选择 → `ModelSelector.vue` 组件
- `generate_page.py:109-125` 模型 + Token + Temperature → `ModelSelector.vue` 参数区
- `generate_page.py:140-174` 平台/风格/长度/关键词 → Element Plus `el-form`
- `generate_page.py:185-189` 主题输入 → `el-input` textarea
- `generate_page.py:194-299` 生成结果展示 → Markdown 渲染 + 标签 + 操作按钮
- `generate_page.py:306-318` 标题生成 → 对话框展示

**关键组件:**
- `ModelSelector.vue`:
  - 提供商下拉 → 请求 `GET /api/models` 获取可用列表
  - 模型下拉 → 联动切换
  - Temperature slider (0.0-1.0, step 0.1)
  - Max tokens 选择器

**验证**: 选择提供商+模型，输入主题，点击生成，结果展示完整（标题+正文+标签）

#### Step 3.4: 页面实现 — 打磨 (Refine.vue)

**功能映射 (来自 `src/web/pages/refine_page.py`):**
- `refine_page.py:77-111` 内容 ID 输入 + 最近内容列表 → `el-select` 远程搜索
- `refine_page.py:179-243` 改写 tab → `el-input` 指令 + 执行按钮
- `refine_page.py:245-302` 风格切换 tab → `el-radio-group`
- `refine_page.py:304-335` 标题优化 tab → 数量 slider + 结果列表
- `refine_page.py:337-369` SEO 分析 tab → 分析结果 markdown

**使用 Element Plus `el-tabs`** 对应 Streamlit 的 `st.tabs(["改写", "风格切换", "标题优化", "SEO 分析"])`

**验证**: 加载内容 → 执行改写 → 新版本保存 → 历史可查

#### Step 3.5: 页面实现 — 日历 + 历史 + 统计

**Calendar.vue (对应 `src/web/pages/calendar_page.py`):**
- Element Plus `el-calendar` 组件
- 事件列表 + 添加事件对话框
- 批量生成一周内容按钮

**History.vue (对应 `src/web/pages/history_page.py`):**
- `el-table` + 分页 + 筛选 (状态/类型)
- 行点击查看详情 (抽屉/对话框)

**Stats.vue (对应 `src/web/pages/stats_page.py:29-158`):**
- `stats_page.py:31-43` 核心指标 → Element Plus `el-statistic` 卡片
- `stats_page.py:48-68` 类型分布饼图 → ECharts `pie` (替代 plotly)
- `stats_page.py:73-89` 状态分布柱图 → ECharts `bar`
- `stats_page.py:96-126` 发布趋势折线 → ECharts `line`

**验证**: 日历展示事件，历史列表可筛选，统计图表正常渲染

#### Step 3.6: Agent 对话界面 (Chat.vue)

**新增功能 (Streamlit 无对应):**
- SSE 连接 `GET /api/agent/stream?message=xxx&thread_id=yyy`
- 消息气泡 (用户/AI 分左右对齐)
- 打字机效果 (逐 token 渲染)
- 对话历史加载
- 新会话/清空按钮

```typescript
// agent.ts - SSE 实现
export function streamChat(message: string, threadId: string, onChunk: (token: string) => void) {
  const eventSource = new EventSource(`/api/agent/stream?message=${encodeURIComponent(message)}&thread_id=${threadId}`)
  eventSource.onmessage = (event) => onChunk(event.data)
  eventSource.onerror = () => eventSource.close()
}
```

**验证**: 输入消息 → AI 逐字流式回复 → 刷新页面后对话历史仍在

### Phase 4: 清理与整合

> 目标：移除所有旧代码，项目干净可部署

#### Step 4.1: 移除旧代码

**删除文件:**
- `src/web/` 整个目录 (Streamlit 页面: `app.py`, `pages/generate_page.py`, `pages/refine_page.py`, `pages/calendar_page.py`, `pages/history_page.py`, `pages/stats_page.py`)
- `src/main.py` (Rich CLI 交互循环)
- `run.py` (CLI 启动脚本)
- `src/llm/claude_client.py` (Phase 2 已标记删除，确认)
- `src/llm/openai_compatible.py` (Phase 2 已标记删除，确认)
- `src/llm/siliconflow_client.py` (Phase 2 已标记删除，确认)
- `examples/` 目录 (quick_start.py, multi_api_demo.py — 依赖旧 CLI)

**修复:**
- `src/models/content.py:43` — `created_at: datetime = None` → `created_at: Optional[datetime] = None` (类型安全)

**验证**: `grep -r "streamlit\|from rich\|import requests" src/` 返回零结果

#### Step 4.2: 新启动入口 + 配置

**新建文件:**
- `server.py`:
  ```python
  import uvicorn
  if __name__ == "__main__":
      uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)
  ```
- `.env.example` — 更新所有环境变量说明

**修改文件:**
- `.env.example` — 添加 `DATABASE_URL`, `PG_HOST`, `PG_PORT`, `PG_NAME` 等
- 更新 CLAUDE.md 中的运行命令

**验证**: `python server.py` 启动成功, `curl http://localhost:8000/api/health` 返回 200

#### Step 4.3: 数据迁移脚本

**新建 `scripts/migrate_sqlite_to_pg.py`:**
1. 读取 `data/content_ops.db` (SQLite)
2. 连接 PostgreSQL (通过 async engine)
3. 遍历 `contents`, `calendar_events`, `content_metrics` 三张表
4. 逐行 INSERT INTO PG
5. 验证: `SELECT count(*) FROM contents` PG count == SQLite count
6. 输出迁移报告: 每张表迁移行数 + 是否一致

**验证**: 脚本执行成功，PG 数据完整

---

## 风险与缓解

| 风险 | 严重度 | 文件/行 | 缓解措施 | 验证方法 |
|------|--------|---------|----------|----------|
| SQLAlchemy async 全量重写，查询语法差异大 | 高 | `content_store.py:74-219` | 先写同步版本跑通，再逐步改 async；参考 SQLAlchemy 2.0 迁移指南 | `pytest tests/test_storage.py` |
| langgraph-checkpoint-postgres 与当前 LangGraph 版本不兼容 | 高 | `workflow.py:128` | 锁定兼容版本：`langgraph>=0.4.0` + `langgraph-checkpoint-postgres>=2.0.0` | Agent 对话 + 重启恢复 |
| litellm 对 SiliconFlow 自定义 base_url 支持可能有限 | 中 | `siliconflow_client.py:14` | litellm 支持 `api_base` 参数传入自定义 URL；测试不通过则用 `openai/Qwen/...` 前缀 | 4 个提供商各跑一次 completion |
| LangGraph @tool 不支持 async | 中 | `content_tools.py:20-53` | LangGraph 0.4+ 支持 `@tool` + `async def`，需验证版本 | `agent.chat("帮我写一篇小红书")` |
| Vue 3 前端工作量大 | 中 | 6 个页面 + 组件 | 优先核心页面 (Generate + History)，Chat 用最简实现 | `npm run build` 零错误 |
| SQLite→PG 数据类型差异 (如 Date 序列化) | 低 | `content_store.py:163-174` | Alembic migration 处理 schema 差异，迁移脚本做类型转换 | 迁移脚本验证 count |

## 验证计划

| Phase | 验证命令 | 预期结果 |
|-------|----------|----------|
| 1.1 | `pip install -r requirements.txt && python -c "from src.api.main import app"` | 无报错 |
| 1.2 | `python -c "from src.storage.base import Base; print(list(Base.metadata.tables))"` | 输出 3 个表名 |
| 1.3 | `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` | 全部成功 |
| 1.4 | `curl http://localhost:8000/docs` | 返回 HTML (Swagger UI) |
| 1.5 | `curl -X POST /api/content/generate -H "Content-Type: application/json" -d '{"topic":"测试","content_type":"xiaohongshu"}'` | 201 + content_id |
| 1.6 | Agent 对话 → 重启 → 获取历史 | 历史消息完整 |
| 2.1 | 对每个 provider 执行 `litellm.acompletion()` | 4/4 成功 |
| 2.2 | `grep -r "claude_client\|openai_compatible\|siliconflow_client" src/` | 零匹配 |
| 3.1 | `cd frontend && npm run dev` | 浏览器可访问 |
| 3.3-3.6 | 手动操作每个页面 | 功能与 Streamlit 对等 |
| 4.1 | `grep -r "streamlit\|from rich" src/` | 零匹配 |
| 4.2 | `python server.py` | 启动成功 |
| 4.3 | `python scripts/migrate_sqlite_to_pg.py` | 迁移报告: count 一致 |

## 端到端验证流程

```
1. 启动: python server.py → FastAPI 运行在 :8000
2. 启动: cd frontend && npm run dev → Vue 运行在 :5173
3. 浏览器打开 http://localhost:5173
4. 首页 → 点击"内容生成" → 输入"测试主题" → 选择小红书 → 点击生成
5. 等待生成完成 → 查看标题+正文+标签
6. 点击"去打磨" → 切换到"风格切换" tab → 选择"专业严谨" → 执行
7. 点击"加入日历" → 选择日期 → 确认
8. 点击"统计分析" → 查看饼图+柱图
9. 点击"Agent 对话" → 输入消息 → 查看 SSE 流式回复
10. 刷新页面 → 对话历史仍在
```

---

## ADR: 技术栈现代化架构决策

### Decision

采用 FastAPI + Vue 3 + PostgreSQL + litellm 全量重构方案，移除 Streamlit/CLI/自定义客户端。

### Drivers

1. **生产可用性** — 当前架构无法满足并发、持久化、可扩展需求
2. **维护成本** — 4 个 LLM 客户端 + 旧式 ORM + Streamlit 全栈耦合
3. **用户体验** — 需要实时流式对话、组件复用、现代 UI

### Alternatives Considered

| 方案 | 优势 | 劣势 | 结论 |
|------|------|------|------|
| 全面重构 (选定) | 架构一致，无技术债 | 工作量大 | 最适合，项目无生产用户 |
| 渐进共存 | 可回退 | 双系统维护成本 > 重构成本 | 无效 — 无回退必要 |
| 仅升级后端 (保留 Streamlit) | 工作量小 | Streamlit 仍是瓶颈 | 无效 — 未解决核心问题 |
| Django + DRF 替代 FastAPI | 全功能框架 | 与 LangGraph async 不匹配，重 | 无效 — FastAPI 已在依赖中 |

### Why Chosen

- **FastAPI**: 已在 `requirements.txt` 声明，async 原生，自动 OpenAPI 文档，与 LangGraph async 架构匹配
- **Vue 3 + Element Plus**: 中文组件库完善，学习曲线低，Vue 3 Composition API + TypeScript 支持好
- **PostgreSQL**: 生产级数据库，LangGraph 官方支持 PG checkpointer，并发性能好
- **litellm**: 统一 100+ LLM 提供商接口，自动重试/fallback，减少 4 个自定义客户端维护

### Consequences

- 破坏性变更：Streamlit 前端、CLI、自定义 LLM 客户端完全移除
- 新增运维依赖：PostgreSQL 服务
- 新增前端技术栈：Node.js + npm 构建流程
- 向上兼容：litellm 未来新增 provider 零代码改动

### Follow-ups

- Phase 5 (未来): 用户认证 (JWT/OAuth)、内容发布到平台 API、多租户
- 监控: 接入 Prometheus + Grafana (API 指标 + LLM 调用指标)
- CI/CD: GitHub Actions 自动测试 + 前端构建 + Docker 镜像
