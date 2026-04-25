# Interview Demo Guide

This guide is designed for a 3-5 minute interview walkthrough of the AI Content Ops SaaS prototype.

## Before the Demo

Seed demo data:

```powershell
python examples/seed_demo_data.py
```

Start the backend:

```powershell
python server.py
```

Start the frontend:

```powershell
cd frontend
npm run dev
```

Open:

- `http://localhost:5173`
- `http://localhost:8000/docs` if you want to show API contracts.

Live LLM generation requires a configured provider API key. If no key is available, use the seeded content, calendar, stats, and sample Agent thread to demonstrate the product loop without external calls.

## 3-5 Minute Demo Route

### 1. Content Studio, 60-90 seconds

Open the first screen, Content Studio.

Show that the workspace is centered on the actual content workflow:

- Left: creative brief, platform, style, length, keywords, provider/model.
- Center: editable final draft and platform preview.
- Right: Strategy / Writer / Editor / Review Agent console.

If you have a provider key configured, run a short prompt:

```text
如何用 AI 把一周内容选题、写作和复盘流程标准化
```

Explain that the pipeline is 4 stages and each stage returns status, duration, input summary, and output. The final content can be saved into the library.

If no provider key is configured, do not run the live pipeline. Say that the same endpoint is contract-tested with fake LLM clients and continue to the seeded data.

### 2. Agent Chat, 60 seconds

Open Agent 对话.

Select the seeded thread named `Demo: content operations weekly plan`.

Point out:

- Thread persistence.
- Provider/model metadata.
- Saved user and assistant messages.
- Tool event records.
- The 9 available tools shown in the control panel.

Suggested explanation:

```text
The pipeline Agent is structured and stage-based. The chat Agent is flexible and tool-based. It can call content and calendar tools, and the backend persists the thread and tool events so the frontend can replay the operational trace.
```

### 3. Content Library and Refinement, 45-60 seconds

Open 历史内容.

Show seeded content across multiple platforms and statuses. Open or reference one content item, then go to 内容打磨.

Explain:

- Generated and refined content are stored as separate records.
- Refined versions can keep a parent relationship.
- Content is available for later scheduling and analytics.

### 4. Calendar and Stats, 45-60 seconds

Open 发布日历.

Show the seeded future events. Explain that this prototype models content planning and scheduling; it does not claim live publishing to social platforms.

Open 统计分析.

Show the distribution by content type and status. Explain that the current analytics are intentionally simple and based on persisted local workflow data.

### 5. API and Tests, 30 seconds

Optionally open `http://localhost:8000/docs`.

Point out these endpoints:

- `POST /api/agent/run`
- `POST /api/agent/chat`
- `GET /api/agent/threads`
- `GET /api/content`
- `GET /api/calendar/events`
- `GET /api/stats`

Close with:

```text
This is packaged as a SaaS prototype: the implemented value is the end-to-end Agent workflow, model routing, persistence, and UI loop. Production login, billing, multi-tenancy, and real publishing integrations are the next commercialization layer, not current claims.
```

## Screenshot Checklist

Good screenshots for a resume or portfolio:

- Content Studio with the 4 Agent cards visible.
- Final draft preview after a successful pipeline run.
- Agent Chat showing a persisted thread and tool events.
- History page with several saved content records.
- Calendar page with scheduled content events.
- Stats page with type and status charts.
- FastAPI docs showing the Agent/content/calendar endpoints.

No screenshot files are required in the repository. Keep screenshots out of git unless you intentionally add a portfolio asset folder.
