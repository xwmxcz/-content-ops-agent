# Resume Packaging

Target role: AI Full-stack Engineer

Project name: AI Content Ops SaaS Prototype

One-line positioning: Built a demo-ready AI content operations workspace that connects a Vue 3 frontend, FastAPI backend, multi-provider LLM routing, Agent orchestration, tool-calling chat, and persistent content workflow data.

## 中文简历版

项目：AI Content Ops SaaS Prototype | AI 内容运营工作台

- 独立设计并实现 AI 内容运营 SaaS 原型，覆盖内容策略、初稿生成、编辑润色、质量审核、内容库、发布日历和统计分析等核心流程。
- 基于 FastAPI + Vue 3 + Element Plus 搭建前后端分离应用，使用 SQLAlchemy + SQLite 持久化内容、日历事件、Agent thread 和消息记录。
- 实现 4-stage Agent pipeline，将 Strategy / Writer / Editor / Review 拆分为可观测步骤，支持保存最终内容并回流到内容库。
- 实现工具型对话 Agent，支持 9 个内容运营工具动作，包括生成内容、打磨内容、标题生成、SEO 分析、查看内容、列出历史、加入日历、查看日历和统计查询。
- 通过 LiteLLM / LangChain 统一接入 Claude、SiliconFlow、DeepSeek、Moonshot，支持前端模型选择、默认模型配置和多 provider 路由。
- 编写 API contract tests，覆盖健康检查、模型列表、内容生成持久化、Agent pipeline、Agent chat thread 持久化和 tool events。

可放在简历技能关键词：

FastAPI, Vue 3, TypeScript, SQLAlchemy, SQLite, LiteLLM, LangChain, Agent orchestration, tool calling, multi-provider model routing, API contract tests

## English Resume Version

Project: AI Content Ops SaaS Prototype

- Built an AI content operations SaaS prototype covering strategy generation, drafting, editing, review, content history, publishing calendar, and analytics.
- Developed a full-stack application with Vue 3, TypeScript, Element Plus, FastAPI, SQLAlchemy, and SQLite for a complete local demo workflow.
- Implemented a 4-stage Agent pipeline with Strategy, Writer, Editor, and Review steps, including step-level outputs and final content persistence.
- Built a persistent tool-calling chat Agent with 9 content operations tools for generation, refinement, title ideation, SEO analysis, content lookup, calendar scheduling, and stats.
- Integrated multi-provider LLM routing through LiteLLM and LangChain, supporting Claude, SiliconFlow, DeepSeek, and Moonshot model selection.
- Added API contract tests covering health checks, model metadata, content persistence, Agent pipeline behavior, chat thread persistence, and tool event recording.

Suggested role keywords:

AI Full-stack Engineer, LLM Application Engineer, Agent Engineer, Full-stack Product Engineer

## Interview Talk Track

Use this explanation when the interviewer asks what the project demonstrates:

1. Problem: content teams need a repeatable workflow, not just a one-off text generator. The product turns topic input into strategy, draft, edit, review, storage, scheduling, and statistics.
2. Architecture: the frontend is Vue 3; the backend is FastAPI; LLM access is abstracted through LiteLLM and provider config; operational data is persisted through SQLAlchemy.
3. Agent engineering: the pipeline Agent is deterministic at the orchestration layer because each stage has a role, prompt, status, duration, and output. The chat Agent is more flexible and uses tool calling for content operations tasks.
4. Product loop: saved content can be refined, scheduled, listed, and counted. That makes it a small content operations system rather than only a prompt demo.
5. Engineering quality: API contracts are tested with fake LLM clients so default tests do not require real provider calls.
6. Commercial boundary: this is a SaaS prototype suitable for demos and portfolio review. Production login, billing, multi-tenancy, cloud deployment, and real publishing integrations are future work, not current claims.

## Verifiable Metrics

Use only metrics that are true in the repository:

- 4-stage Agent pipeline.
- 9 tool actions in the chat Agent.
- 4 supported LLM providers.
- 11 API/config contract tests in the current pytest suite.
- Local demo seed script that does not call external LLM APIs.

Avoid claims that are not implemented:

- Do not claim real paying customers or revenue.
- Do not claim production deployment unless you deploy it.
- Do not claim OAuth/login, billing, role-based access control, tenant isolation, or real platform publishing.
- Do not claim autonomous posting to social platforms; the calendar is a planning/scheduling data model in this prototype.
