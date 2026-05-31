"""Tool-capable persistent chat Agent service for the API layer."""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta
from typing import Any, Callable
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool

from src.agent.context_engine import ContextEngine
from src.api.schemas.agent import ChatRequest, ChatResponse, ChatToolEvent, PlanStep
from src.api.schemas.content import GenerateRequest, RefineRequest, SeoRequest, TitleRequest
from src.api.services.publish_service import create_publish_service
from src.api.services import content_service
from src.api.services.content_service import resolve_provider
from src.llm.litellm_client import LLMConfigurationError, LiteLLMClient
from src.models import ContentStyle, ContentType
from src.storage import ContentStore
from src.storage.file_memory import AGENT as MEMORY_AGENT, USER as MEMORY_USER, FileMemory, MemoryAmbiguous, MemoryLimitExceeded, MemoryNotFound
from src.utils import config


MAX_LOOPS = 8
MAX_FAILURES_PER_TOOL = 2
WRITE_TOOLS = {
    "create_content", "refine_content", "add_to_calendar",
    "memory_add", "memory_replace", "memory_remove",
}
PLANNER_TEMPERATURE = 0.3
PLANNER_MAX_TOKENS = 1024
AVAILABLE_TOOL_NAMES = [
    "create_content", "refine_content", "generate_title_options", "optimize_seo",
    "view_content", "list_recent_contents", "add_to_calendar", "view_calendar",
    "get_content_stats", "check_xiaohongshu_login", "search_history",
    "web_search", "analyze_content_performance", "find_optimization_candidates",
    "propose_topics", "propose_publishing_schedule", "commit_publishing_schedule",
    "memory_add", "memory_replace", "memory_remove", "session_search",
]


_FROZEN_PROMPTS: dict[str, str] = {}
PLANNER_SYSTEM_PROMPT = (
    "You are a planner. Given the user's request and the available tools, "
    "output a JSON array of steps.\n"
    'Schema: [{"index": 1, "description": "...", "tool_hint": "tool_name_or_null"}].\n'
    "Rules: at most 5 steps; output JSON only, no prose, no markdown fence.\n"
    f"Available tools: {', '.join(AVAILABLE_TOOL_NAMES)}."
)


SYSTEM_PROMPT_TEMPLATE = """You are Content Ops Agent, a production assistant for content operations.

Current date anchors (always trust these over your own memory or training cutoff):
- Today: {today} ({weekday})
- Tomorrow: {tomorrow}
- This week (Mon..Sun): {this_week}
- Next Monday: {next_monday}
- Next week (Mon..Sun): {next_week}

When the user uses relative dates like "tomorrow", "next Monday", or "下周一",
resolve them to an absolute YYYY-MM-DD value using the anchors above before calling any tool.
Never invent a date from training data; the resolved date MUST be ≥ {today}.
When you mention a date back to the user, quote the exact YYYY-MM-DD you used in the tool call.
Answer in the user's language. Use tools when the user asks to create content, refine stored content,
inspect recent content, manage the publishing calendar, or check content statistics.
Do not claim that content was saved or scheduled unless a tool result confirms it.

When the user asks for topic ideas, "what should we write next", weekly planning, or content strategy:
1. Call analyze_content_performance to see what kinds of past content actually performed.
2. Optionally call web_search for recent external trends related to the user's domain.
3. Call propose_topics to synthesize a topic list grounded in step 1+2.
Present the proposal as a markdown table — do not commit anything yet.

When the user asks "哪些内容值得改 / 帮我看看哪些要优化 / 复盘":
1. Call find_optimization_candidates with the appropriate criteria
   ('underperforming' / 'recent_drafts' / 'old_drafts'). When unsure, default to
   'underperforming'.
2. For each candidate, briefly explain WHY it qualifies (the `reason` field is a
   starting point; add your own judgment about how to fix it).
3. Suggest specific refinement directions for 2-3 of them.
4. Wait for the user to pick which ones to actually refine before calling refine_content.

When the user asks to "schedule" or "plan publishing" for content items:
1. Use propose_publishing_schedule first — it returns a plan but does NOT write to the calendar.
2. Show the plan to the user as a markdown table.
3. Wait for the user to confirm naturally (e.g. "好的", "开始排吧", "OK"). If they ask for changes
   first, call propose_publishing_schedule again with adjusted parameters.
4. Only after explicit confirmation, call commit_publishing_schedule with the same plan.

Write tools (create_content, refine_content, add_to_calendar, commit_publishing_schedule)
have side effects — never call them without first showing the user what you intend to do
and getting confirmation, unless the user's original request was already an explicit
"please do X now" instruction.

Long-term memory (file-based, frozen per session):
- The MEMORY.md (your own notes) and USER.md (user profile) sections above
  were loaded once at session start. Anything you write back via the memory
  tools takes effect in the NEXT session, not this one.
- Use `memory_add` to record a durable note (`target="agent"` for project
  conventions, tool quirks, brand vocabulary; `target="user"` for user name,
  language, style preferences).
- Use `memory_replace` to update an existing entry (substring match must be
  unique).
- Use `memory_remove` to delete an outdated entry.
- Do NOT save ephemeral or single-turn information; the files are small (~2KB
  and ~1KB respectively). Quality over quantity.

Session search:
- Use `session_search` to recall what was said earlier in this or past
  threads. It runs full-text search over `agent_messages` and works on Chinese
  via FTS5 trigram tokenizer. Prefer this over guessing from memory."""


_WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _build_system_prompt(memory_snapshot: dict[str, str] | None = None) -> str:
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    monday_this_week = today - timedelta(days=today.weekday())
    sunday_this_week = monday_this_week + timedelta(days=6)
    next_monday = monday_this_week + timedelta(days=7)
    next_sunday = next_monday + timedelta(days=6)
    base = SYSTEM_PROMPT_TEMPLATE.format(
        today=today.strftime("%Y-%m-%d"),
        weekday=_WEEKDAY_CN[today.weekday()],
        tomorrow=tomorrow.strftime("%Y-%m-%d"),
        this_week=f"{monday_this_week.strftime('%Y-%m-%d')}..{sunday_this_week.strftime('%Y-%m-%d')}",
        next_monday=next_monday.strftime("%Y-%m-%d"),
        next_week=f"{next_monday.strftime('%Y-%m-%d')}..{next_sunday.strftime('%Y-%m-%d')}",
    )
    snap = memory_snapshot or {}
    memory_md = (snap.get("memory") or "").strip()
    user_md = (snap.get("user") or "").strip()
    blocks = [base]
    if memory_md:
        blocks.append(
            "\n══════════════════════════════════════════════\n"
            "MEMORY.md (your personal notes — frozen for this session)\n"
            "══════════════════════════════════════════════\n"
            f"{memory_md}"
        )
    if user_md:
        blocks.append(
            "\n══════════════════════════════════════════════\n"
            "USER.md (user profile — frozen for this session)\n"
            "══════════════════════════════════════════════\n"
            f"{user_md}"
        )
    return "".join(blocks)


ModelFactory = Callable[[str, str, float, int], Any]


class ChatAgentExecutionError(RuntimeError):
    """Raised when the chat Agent cannot complete a request."""


class ChatAgentService:
    def __init__(
        self,
        store: ContentStore,
        llm: LiteLLMClient | None = None,
        model_factory: ModelFactory | None = None,
        file_memory: FileMemory | None = None,
        context_engine: ContextEngine | None = None,
    ):
        self.store = store
        self.llm = llm or LiteLLMClient()
        self.model_factory = model_factory or self._create_chat_model
        self.file_memory = file_memory
        self.context_engine = context_engine

    async def chat(self, request: ChatRequest) -> ChatResponse:
        provider = resolve_provider(request.provider)
        model = request.model or config.get_model(provider)
        thread_id = request.thread_id or f"chat_{uuid4().hex[:10]}"
        title = self._make_thread_title(request.message)

        # Title here is an auto-generated suggestion. ContentStore guards against
        # overwriting an existing thread's title (and respects title_pinned set
        # via PATCH /threads/{id}), so this is safe on rename-locked threads.
        self.store.upsert_agent_thread(thread_id, title=title, provider=provider, model=model)
        history = self.store.list_agent_messages(thread_id, limit=20)
        self.store.save_agent_message(
            thread_id=thread_id,
            role="user",
            content=request.message,
            provider=provider,
            model=model,
        )

        plan: list[PlanStep] = []
        if config.CHAT_PLAN_ENABLED:
            try:
                plan = await self._make_plan(
                    message=request.message,
                    history=history,
                    provider=provider,
                    model=model,
                )
            except Exception:
                plan = []

        try:
            response, tool_events, plan = await self._run_agent(
                history=history,
                message=request.message,
                provider=provider,
                model=model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                plan=plan,
                thread_id=thread_id,
            )
        except LLMConfigurationError:
            raise
        except Exception as exc:
            failure = f"Agent execution failed: {exc}"
            self.store.save_agent_message(
                thread_id=thread_id,
                role="assistant",
                content=failure,
                provider=provider,
                model=model,
                status="failed",
            )
            raise ChatAgentExecutionError(failure) from exc

        message_id = self.store.save_agent_message(
            thread_id=thread_id,
            role="assistant",
            content=response,
            provider=provider,
            model=model,
            tool_events=[event.model_dump() for event in tool_events],
            plan=[step.model_dump() for step in plan] if plan else None,
        )
        return ChatResponse(
            message_id=message_id,
            thread_id=thread_id,
            response=response,
            provider=provider,
            model=model,
            tool_events=tool_events,
            plan=plan,
        )

    async def _make_plan(
        self,
        message: str,
        history: list[dict[str, Any]],
        provider: str,
        model: str,
    ) -> list[PlanStep]:
        chat_model = self.model_factory(provider, model, PLANNER_TEMPERATURE, PLANNER_MAX_TOKENS)
        messages: list[BaseMessage] = [SystemMessage(content=PLANNER_SYSTEM_PROMPT)]
        messages.extend(self._history_to_messages(history))
        messages.append(HumanMessage(content=message))
        ai_message = await chat_model.ainvoke(messages)
        raw = self._message_content_to_text(ai_message.content).strip()
        if not raw:
            return []
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE | re.DOTALL).strip()
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        steps: list[PlanStep] = []
        for raw_step in payload[:5]:
            if not isinstance(raw_step, dict):
                continue
            try:
                steps.append(
                    PlanStep(
                        index=int(raw_step.get("index") or len(steps) + 1),
                        description=str(raw_step.get("description") or "").strip(),
                        tool_hint=(raw_step.get("tool_hint") or None) or None,
                        status="pending",
                    )
                )
            except Exception:
                continue
        return [s for s in steps if s.description]

    async def _run_agent(
        self,
        history: list[dict[str, Any]],
        message: str,
        provider: str,
        model: str,
        temperature: float,
        max_tokens: int,
        plan: list[PlanStep] | None = None,
        thread_id: str | None = None,
    ) -> tuple[str, list[ChatToolEvent], list[PlanStep]]:
        plan = plan or []
        tools = self._build_tools(provider, model, temperature, max_tokens)
        tools_by_name = {tool.name: tool for tool in tools}
        chat_model = self.model_factory(provider, model, temperature, max_tokens)
        if hasattr(chat_model, "bind_tools"):
            chat_model = chat_model.bind_tools(tools)

        frozen = self._get_frozen_system_prompt(thread_id)
        messages: list[BaseMessage] = [SystemMessage(content=frozen)]
        if plan:
            numbered = "\n".join(
                f"  {step.index}. {step.description}"
                + (f" [hint: {step.tool_hint}]" if step.tool_hint else "")
                for step in plan
            )
            plan_block = (
                "Here is your plan for this request:\n"
                f"{numbered}\n"
                "Mark progress by calling tools roughly in this order. "
                "If a step does not need a tool, you may skip it."
            )
            messages.append(SystemMessage(content=plan_block))
        messages.extend(self._history_to_messages(history))
        messages.append(HumanMessage(content=message))

        tool_events: list[ChatToolEvent] = []
        if self.context_engine is not None:
            try:
                result = await self.context_engine.maybe_compress(
                    messages, provider=provider, model=model
                )
                if result.compressed:
                    messages = result.messages
                    tool_events.append(ChatToolEvent(
                        name="context_compress",
                        args={"dropped": result.dropped_count},
                        output=(result.summary or "")[:1200],
                        status="completed",
                        attempt=1,
                    ))
            except Exception:
                pass

        attempt_count: dict[str, int] = {}
        failure_count: dict[str, int] = {}
        last_content = ""
        for _ in range(MAX_LOOPS):
            ai_message = await chat_model.ainvoke(messages)
            messages.append(ai_message)
            last_content = self._message_content_to_text(ai_message.content)
            tool_calls = getattr(ai_message, "tool_calls", None) or []
            if not tool_calls:
                break

            for call in tool_calls:
                name = call.get("name", "")
                args = call.get("args") or {}
                tool = tools_by_name.get(name)
                attempt_count[name] = attempt_count.get(name, 0) + 1
                attempt_no = attempt_count[name]

                if not tool:
                    output = f"Unknown tool: {name}"
                    event = ChatToolEvent(
                        name=name or "unknown",
                        args=args,
                        output=output,
                        status="failed",
                        error=output,
                        attempt=attempt_no,
                    )
                    messages.append(ToolMessage(content=output, tool_call_id=call.get("id") or name or "unknown"))
                    tool_events.append(event)
                    continue

                started = time.perf_counter()
                try:
                    output = await tool.ainvoke(args)
                    output_text = self._stringify_tool_output(output)
                    duration_ms = int((time.perf_counter() - started) * 1000)
                    step_index = self._associate_plan_step(plan, name, success=True)
                    event = ChatToolEvent(
                        name=name,
                        args=args,
                        output=output_text[:1200],
                        attempt=attempt_no,
                        duration_ms=duration_ms,
                        plan_step_index=step_index,
                    )
                    messages.append(ToolMessage(content=output_text, tool_call_id=call.get("id") or name))
                except Exception as exc:
                    duration_ms = int((time.perf_counter() - started) * 1000)
                    failure_count[name] = failure_count.get(name, 0) + 1
                    error_text = str(exc) or exc.__class__.__name__
                    step_index = self._associate_plan_step(plan, name, success=False)
                    event = ChatToolEvent(
                        name=name,
                        args=args,
                        output=f"Tool failed: {error_text}",
                        status="failed",
                        error=error_text,
                        attempt=attempt_no,
                        duration_ms=duration_ms,
                        plan_step_index=step_index,
                    )
                    if failure_count[name] > MAX_FAILURES_PER_TOOL:
                        feedback = (
                            f"Tool `{name}` has now failed {failure_count[name]} times. "
                            "Stop calling it. Tell the user clearly that this sub-task cannot complete "
                            "and continue with whatever else you can finish."
                        )
                    elif name in WRITE_TOOLS:
                        feedback = (
                            f"Tool `{name}` failed (attempt {attempt_no}): {error_text}\n"
                            "This is a write tool with side effects. Decide carefully:\n"
                            "  (a) retry with corrected arguments,\n"
                            "  (b) call a different tool to discover the right input first,\n"
                            "  (c) tell the user the action cannot complete.\n"
                            "Do not silently give up."
                        )
                    else:
                        feedback = (
                            f"Tool `{name}` failed (attempt {attempt_no}): {error_text}\n"
                            "Decide: (a) retry with corrected arguments, "
                            "(b) try a different tool to discover the right input, "
                            "or (c) tell the user the action cannot complete."
                        )
                    messages.append(ToolMessage(content=feedback, tool_call_id=call.get("id") or name))
                tool_events.append(event)

        for step in plan:
            if step.status in ("pending", "running"):
                step.status = "skipped"

        final = last_content or "The Agent completed tool work but did not produce a final reply."
        return final, tool_events, plan

    @staticmethod
    def _associate_plan_step(plan: list[PlanStep], tool_name: str, *, success: bool) -> int | None:
        if not plan:
            return None
        target = next(
            (s for s in plan if s.status == "pending" and s.tool_hint == tool_name),
            None,
        )
        if target is None:
            target = next((s for s in plan if s.status == "pending"), None)
        if target is None:
            return None
        target.status = "completed" if success else "failed"
        return target.index

    def _build_tools(
        self,
        provider: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> list[StructuredTool]:
        async def create_content(
            topic: str,
            content_type: str,
            style: str = "casual",
            keywords: str | None = None,
            length: str = "medium",
        ) -> str:
            """Create and save a new content draft."""
            request = GenerateRequest(
                topic=topic,
                content_type=ContentType(content_type),
                style=ContentStyle(style),
                keywords=self._split_keywords(keywords),
                length=length,
                provider=provider,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content_id, generated, used_provider, used_model = await content_service.generate_content(
                request,
                self.llm,
                self.store,
            )
            return json.dumps(
                {
                    "id": content_id,
                    "title": generated.title,
                    "content": generated.content,
                    "provider": used_provider,
                    "model": used_model,
                    "saved": True,
                },
                ensure_ascii=False,
            )

        async def refine_content(content_id: int, instruction: str) -> str:
            """Refine an existing saved content item and save the new version."""
            request = RefineRequest(
                content_id=content_id,
                instruction=instruction,
                provider=provider,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            new_id, refined, used_provider, used_model = await content_service.refine_content(
                request,
                self.llm,
                self.store,
            )
            return json.dumps(
                {
                    "id": new_id,
                    "parent_id": content_id,
                    "title": refined.title,
                    "content": refined.content,
                    "provider": used_provider,
                    "model": used_model,
                    "saved": True,
                },
                ensure_ascii=False,
            )

        async def generate_title_options(
            topic: str | None = None,
            content_id: int | None = None,
            content_type: str = "xiaohongshu",
            count: int = 5,
        ) -> str:
            """Generate title options for a topic or saved content item."""
            request = TitleRequest(
                topic=topic,
                content_id=content_id,
                content_type=ContentType(content_type),
                count=count,
                provider=provider,
                model=model,
            )
            return await content_service.generate_titles(request, self.llm, self.store)

        async def optimize_seo(content_id: int) -> str:
            """Analyze a saved content item and return SEO recommendations."""
            request = SeoRequest(content_id=content_id, provider=provider, model=model)
            return await content_service.analyze_seo(request, self.llm, self.store)

        def view_content(content_id: int) -> str:
            """Read a saved content item by id."""
            content = self.store.get_content(content_id)
            if not content:
                return f"Content {content_id} was not found."
            return json.dumps(content, ensure_ascii=False)

        def list_recent_contents(limit: int = 10) -> str:
            """List recent saved content items."""
            return json.dumps(self.store.list_contents(limit=limit), ensure_ascii=False)

        def add_to_calendar(content_id: int, publish_date: str, platform: str) -> str:
            """Schedule a saved content item on the publishing calendar.

            publish_date MUST be an absolute YYYY-MM-DD string ≥ today's date.
            Convert relative phrases like "tomorrow", "next Monday", or "下周一" to YYYY-MM-DD
            using the date anchors in the system prompt before calling.
            Never use dates from your training data or memory — always compute from today.
            """
            content = self.store.get_content(content_id)
            if not content:
                return f"Content {content_id} was not found."
            try:
                scheduled_date = datetime.strptime(publish_date, "%Y-%m-%d").date()
            except ValueError:
                return f"Invalid date format: {publish_date}. Must be YYYY-MM-DD."
            today = datetime.now().date()
            if scheduled_date < today:
                return (
                    f"Cannot schedule in the past. You provided {publish_date}, but today is {today}. "
                    f"Use the date anchors in the system prompt to compute the correct future date."
                )
            event_id = self.store.save_calendar_event(content_id, platform, scheduled_date)
            return json.dumps(
                {
                    "event_id": event_id,
                    "content_id": content_id,
                    "platform": platform,
                    "scheduled_date": publish_date,
                    "saved": True,
                },
                ensure_ascii=False,
            )

        def view_calendar(days: int = 7) -> str:
            """List publishing calendar events from today through the next N days."""
            from datetime import date, timedelta

            start_date = date.today()
            end_date = start_date + timedelta(days=days)
            return json.dumps(self.store.get_calendar_events(start_date, end_date), ensure_ascii=False)

        def get_content_stats() -> str:
            """Return content library statistics."""
            return json.dumps(self.store.get_content_stats(), ensure_ascii=False)

        async def check_xiaohongshu_login() -> str:
            """Check whether the Xiaohongshu MCP integration is currently logged in."""
            status_payload = await create_publish_service(self.store).get_login_status()
            return json.dumps(status_payload, ensure_ascii=False)

        def search_history(query: str, limit: int = 10) -> str:
            """Search saved content by keyword across title, body, and keywords.

            Use this to recall what the team has written before, e.g. "previous hiking posts"
            or to discover the right content_id when the user refers to past work by topic.
            """
            return json.dumps(self.store.search_contents(query, limit), ensure_ascii=False)

        async def web_search(query: str, limit: int = 5) -> str:
            """Run a public web search via DuckDuckGo and return top results as JSON.

            Use this for current trends, recent news, or external context the saved content
            library does not cover.
            """
            from src.tools.web_search import web_search as run_web_search
            results = await run_web_search(query, limit=limit)
            return json.dumps(results, ensure_ascii=False)

        def analyze_content_performance(days: int = 30) -> str:
            """Aggregate the engagement performance of saved content over the last N days.

            Returns averages by content_type, by style, and the top 5 performers ranked by
            engagement rate. Use this before recommending what to write next.
            """
            return json.dumps(self.store.aggregate_performance(days), ensure_ascii=False)

        def find_optimization_candidates(criteria: str = "underperforming", limit: int = 5) -> str:
            """Surface saved content items that likely need refinement.

            criteria:
              - 'underperforming': items whose engagement rate is below the cohort average
              - 'recent_drafts':   drafts/refined created in the last 7 days, not finalized
              - 'old_drafts':      drafts older than 14 days, never finalized

            Use this when the user asks "哪些内容值得改 / 帮我看看哪些要优化 / 复盘一下".
            After calling this, suggest 2-3 candidates to the user with WHY each one
            qualifies — do not call refine_content directly until the user confirms.
            """
            return json.dumps(self.store.list_optimization_candidates(criteria, limit), ensure_ascii=False)

        def propose_topics(count: int = 5, hint: str | None = None) -> str:
            """Build a structured "topic brief" for the agent to use when proposing new
            content topics. This tool does NOT generate topics itself — it gathers the
            evidence the agent needs to formulate them: which content types are winning,
            which are underrepresented, and what recent items already cover so the agent
            does not repeat them.

            Use this when the user asks for topic ideas / weekly planning / "what to write
            next". After calling this, formulate `count` topic ideas as a markdown table
            and present them to the user — do not call create_content yet.
            """
            perf = self.store.aggregate_performance(days=30)
            recent = self.store.list_contents(limit=15)
            by_type = perf.get("by_type") or []
            winners = [t for t in by_type if t.get("with_metrics") and t.get("avg_engagement_rate", 0) >= 0.04]
            underrepresented = sorted(by_type, key=lambda t: t.get("count", 0))[:2]
            brief = {
                "requested_count": count,
                "user_hint": hint,
                "winning_content_types": [
                    {"content_type": t["content_type"], "avg_engagement_rate": t["avg_engagement_rate"],
                     "avg_views": t["avg_views"], "sample_size": t["with_metrics"]}
                    for t in winners[:3]
                ],
                "underrepresented_content_types": [
                    {"content_type": t["content_type"], "count": t["count"]}
                    for t in underrepresented
                ],
                "top_performers": perf.get("top_performers") or [],
                "recently_published_titles": [r.get("title") for r in recent if r.get("title")][:10],
                "guidance": (
                    "Use winners as a positive signal — propose 1-2 topics in those content_types. "
                    "Use underrepresented buckets as exploration — propose 1 topic that fills the gap. "
                    "Avoid repeating any title in recently_published_titles. "
                    "When user_hint is provided, weigh proposals toward that direction."
                ),
            }
            return json.dumps(brief, ensure_ascii=False)

        def propose_publishing_schedule(
            content_ids: list[int],
            start_date: str,
            end_date: str,
            cadence: str = "mwf",
        ) -> str:
            """Plan publishing dates for the given content_ids over [start_date, end_date].

            cadence: 'daily' | 'weekdays' | 'mwf' (Mon/Wed/Fri).
            Returns a proposed plan as a list of {content_id, title, platform, scheduled_date}.
            DOES NOT write to the calendar — the agent must show the plan to the user and
            wait for confirmation, then call commit_publishing_schedule with the same plan.
            """
            from datetime import date as _date
            try:
                start = datetime.strptime(start_date, "%Y-%m-%d").date()
                end = datetime.strptime(end_date, "%Y-%m-%d").date()
            except ValueError as exc:
                return json.dumps({"error": f"Invalid date format: {exc}. Use YYYY-MM-DD."}, ensure_ascii=False)
            if end < start:
                return json.dumps({"error": "end_date must be on or after start_date."}, ensure_ascii=False)

            valid_contents: list[dict[str, Any]] = []
            missing: list[int] = []
            for cid in content_ids:
                row = self.store.get_content(int(cid))
                if row is None:
                    missing.append(int(cid))
                else:
                    valid_contents.append(row)
            if missing:
                return json.dumps(
                    {"error": f"Content ids not found: {missing}. Use list_recent_contents or search_history first."},
                    ensure_ascii=False,
                )

            cadence = (cadence or "mwf").lower()
            cursor = start
            candidate_dates: list[_date] = []
            while cursor <= end:
                weekday = cursor.weekday()  # Mon=0
                ok = (
                    cadence == "daily"
                    or (cadence == "weekdays" and weekday < 5)
                    or (cadence == "mwf" and weekday in (0, 2, 4))
                )
                if ok:
                    candidate_dates.append(cursor)
                cursor = cursor + timedelta(days=1)

            existing = self.store.get_calendar_conflicts(start, end)
            occupied: set[tuple[str, str]] = {(e["scheduled_date"], e["platform"]) for e in existing}

            plan: list[dict[str, Any]] = []
            date_iter = iter(candidate_dates)
            for content in valid_contents:
                platform = content.get("content_type") or "unknown"
                slot = None
                for d in date_iter:
                    if (d.isoformat(), platform) in occupied:
                        continue
                    slot = d
                    occupied.add((d.isoformat(), platform))
                    break
                if slot is None:
                    plan.append({
                        "content_id": content["id"],
                        "title": content.get("title"),
                        "platform": platform,
                        "scheduled_date": None,
                        "warning": "no available date in range under given cadence",
                    })
                else:
                    plan.append({
                        "content_id": content["id"],
                        "title": content.get("title"),
                        "platform": platform,
                        "scheduled_date": slot.isoformat(),
                    })

            return json.dumps({
                "plan": plan,
                "cadence": cadence,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "committed": False,
                "reminder": "This is a PROPOSAL. Show it to the user as a markdown table and wait for confirmation before calling commit_publishing_schedule.",
            }, ensure_ascii=False)

        def commit_publishing_schedule(plan: list[dict[str, Any]]) -> str:
            """Persist a previously-proposed publishing schedule to the calendar.

            Each plan item must have content_id, platform, scheduled_date (YYYY-MM-DD).
            Items with null scheduled_date are skipped. Returns a summary of what was saved.
            """
            saved: list[dict[str, Any]] = []
            skipped: list[dict[str, Any]] = []
            for item in plan or []:
                if not item.get("scheduled_date"):
                    skipped.append({"content_id": item.get("content_id"), "reason": "no scheduled_date"})
                    continue
                try:
                    when = datetime.strptime(item["scheduled_date"], "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    skipped.append({"content_id": item.get("content_id"), "reason": "bad date"})
                    continue
                content_id = int(item["content_id"])
                if self.store.get_content(content_id) is None:
                    skipped.append({"content_id": content_id, "reason": "content not found"})
                    continue
                event_id = self.store.save_calendar_event(content_id, item.get("platform") or "unknown", when)
                saved.append({
                    "event_id": event_id,
                    "content_id": content_id,
                    "platform": item.get("platform"),
                    "scheduled_date": item["scheduled_date"],
                })
            return json.dumps({"saved": saved, "skipped": skipped, "committed": True}, ensure_ascii=False)

        def memory_add(target: str, text: str) -> str:
            """Append a durable note to the file-based memory.

            target: 'agent' (writes to MEMORY.md — project conventions, tool
                    quirks, brand vocabulary) or 'user' (writes to USER.md —
                    name, language, style preferences).
            text:   the entry body, may be multiline.
            The entry takes effect in the NEXT session, not this one.
            """
            if not self.file_memory:
                return json.dumps({"saved": False, "reason": "memory disabled"}, ensure_ascii=False)
            try:
                self.file_memory.add(target, text)
            except (MemoryLimitExceeded, ValueError) as exc:
                return json.dumps({"saved": False, "reason": str(exc)}, ensure_ascii=False)
            stats = self.file_memory.stats(target)
            return json.dumps({
                "saved": True,
                "target": target,
                "char_count": stats["char_count"],
                "char_limit": stats["char_limit"],
            }, ensure_ascii=False)

        def memory_replace(target: str, old_text: str, new_text: str) -> str:
            """Replace one occurrence of old_text with new_text in the named file.

            target:   'agent' or 'user'.
            old_text: substring to find; MUST match exactly one place.
            new_text: replacement body.
            """
            if not self.file_memory:
                return json.dumps({"replaced": False, "reason": "memory disabled"}, ensure_ascii=False)
            try:
                self.file_memory.replace(target, old_text, new_text)
            except (MemoryNotFound, MemoryAmbiguous, MemoryLimitExceeded, ValueError) as exc:
                return json.dumps({"replaced": False, "reason": str(exc)}, ensure_ascii=False)
            stats = self.file_memory.stats(target)
            return json.dumps({
                "replaced": True,
                "target": target,
                "char_count": stats["char_count"],
                "char_limit": stats["char_limit"],
            }, ensure_ascii=False)

        def memory_remove(target: str, old_text: str) -> str:
            """Delete one occurrence of old_text from the named file.

            target:   'agent' or 'user'.
            old_text: substring to find; MUST match exactly one place.
            """
            if not self.file_memory:
                return json.dumps({"removed": False, "reason": "memory disabled"}, ensure_ascii=False)
            try:
                self.file_memory.remove(target, old_text)
            except (MemoryNotFound, MemoryAmbiguous, ValueError) as exc:
                return json.dumps({"removed": False, "reason": str(exc)}, ensure_ascii=False)
            stats = self.file_memory.stats(target)
            return json.dumps({
                "removed": True,
                "target": target,
                "char_count": stats["char_count"],
                "char_limit": stats["char_limit"],
            }, ensure_ascii=False)

        def session_search(query: str, limit: int = 5, thread_id: str | None = None) -> str:
            """Full-text search over all stored assistant↔user messages.

            Uses SQLite FTS5 with the trigram tokenizer, so Chinese substrings
            (≥ 3 chars) match. Shorter queries fall back to LIKE.
            Use to recall what was said in this or past conversation threads.
            """
            results = self.store.search_agent_messages(query, limit=limit, thread_id=thread_id)
            return json.dumps({"messages": results, "count": len(results)}, ensure_ascii=False)

        return [
            StructuredTool.from_function(coroutine=create_content, name="create_content"),
            StructuredTool.from_function(coroutine=refine_content, name="refine_content"),
            StructuredTool.from_function(coroutine=generate_title_options, name="generate_title_options"),
            StructuredTool.from_function(coroutine=optimize_seo, name="optimize_seo"),
            StructuredTool.from_function(func=view_content, name="view_content"),
            StructuredTool.from_function(func=list_recent_contents, name="list_recent_contents"),
            StructuredTool.from_function(func=add_to_calendar, name="add_to_calendar"),
            StructuredTool.from_function(func=view_calendar, name="view_calendar"),
            StructuredTool.from_function(func=get_content_stats, name="get_content_stats"),
            StructuredTool.from_function(coroutine=check_xiaohongshu_login, name="check_xiaohongshu_login"),
            StructuredTool.from_function(func=search_history, name="search_history"),
            StructuredTool.from_function(coroutine=web_search, name="web_search"),
            StructuredTool.from_function(func=analyze_content_performance, name="analyze_content_performance"),
            StructuredTool.from_function(func=find_optimization_candidates, name="find_optimization_candidates"),
            StructuredTool.from_function(func=propose_topics, name="propose_topics"),
            StructuredTool.from_function(func=propose_publishing_schedule, name="propose_publishing_schedule"),
            StructuredTool.from_function(func=commit_publishing_schedule, name="commit_publishing_schedule"),
            StructuredTool.from_function(func=memory_add, name="memory_add"),
            StructuredTool.from_function(func=memory_replace, name="memory_replace"),
            StructuredTool.from_function(func=memory_remove, name="memory_remove"),
            StructuredTool.from_function(func=session_search, name="session_search"),
        ]

    def _get_frozen_system_prompt(self, thread_id: str | None) -> str:
        """Return the cached system prompt for `thread_id`, building it once.

        The snapshot captures MEMORY.md + USER.md at first call for the thread,
        then never re-reads them — matching Hermes' "frozen for the session"
        semantics. Mutations made via memory_add/replace/remove only take
        effect when a new thread is started (or `invalidate_frozen` is called
        externally, e.g. by the /refresh-snapshot endpoint).
        """
        key = thread_id or "_anonymous"
        cached = _FROZEN_PROMPTS.get(key)
        if cached is not None:
            return cached
        snapshot = self.file_memory.snapshot() if self.file_memory else None
        prompt = _build_system_prompt(snapshot)
        _FROZEN_PROMPTS[key] = prompt
        return prompt

    @staticmethod
    def invalidate_frozen(thread_id: str | None = None) -> None:
        """Drop the cached system prompt for one thread or all threads."""
        if thread_id is None:
            _FROZEN_PROMPTS.clear()
        else:
            _FROZEN_PROMPTS.pop(thread_id, None)

    @staticmethod
    def _create_chat_model(provider: str, model: str, temperature: float, max_tokens: int):
        api_key = config.get_api_key(provider)
        if not api_key:
            raise ValueError(f"Missing API key for provider: {provider}")

        if provider == "claude":
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(
                api_key=api_key,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {
            "api_key": api_key,
            "base_url": config.get_provider_api_base(provider),
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        # DeepSeek V4 defaults to thinking mode and demands reasoning_content be passed
        # back across turns. LangChain doesn't preserve it, so disable explicitly.
        if provider == "deepseek":
            kwargs["model_kwargs"] = {"extra_body": {"thinking": {"type": "disabled"}}}
        return ChatOpenAI(**kwargs)

    @staticmethod
    def _history_to_messages(history: list[dict[str, Any]]) -> list[BaseMessage]:
        messages: list[BaseMessage] = []
        for item in history:
            if item["role"] == "user":
                messages.append(HumanMessage(content=item["content"]))
            elif item["role"] == "assistant" and item.get("status") == "completed":
                messages.append(AIMessage(content=item["content"]))
        return messages

    @staticmethod
    def _split_keywords(keywords: str | None) -> list[str] | None:
        if not keywords:
            return None
        return [keyword.strip() for keyword in keywords.split(",") if keyword.strip()]

    @staticmethod
    def _make_thread_title(content: str) -> str:
        title = " ".join(content.strip().split())
        return title[:40] or "Untitled thread"

    @staticmethod
    def _stringify_tool_output(output: Any) -> str:
        if isinstance(output, str):
            return output
        return json.dumps(output, ensure_ascii=False)

    @staticmethod
    def _message_content_to_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False)
