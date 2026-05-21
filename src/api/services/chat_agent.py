"""Tool-capable persistent chat Agent service for the API layer."""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool

from src.api.schemas.agent import ChatRequest, ChatResponse, ChatToolEvent, PlanStep
from src.api.schemas.content import GenerateRequest, RefineRequest, SeoRequest, TitleRequest
from src.api.services.publish_service import create_publish_service
from src.api.services import content_service
from src.api.services.content_service import resolve_provider
from src.llm.litellm_client import LLMConfigurationError, LiteLLMClient
from src.models import ContentStyle, ContentType
from src.storage import ContentStore
from src.utils import config


MAX_LOOPS = 8
MAX_FAILURES_PER_TOOL = 2
WRITE_TOOLS = {"create_content", "refine_content", "add_to_calendar"}
PLANNER_TEMPERATURE = 0.3
PLANNER_MAX_TOKENS = 1024
AVAILABLE_TOOL_NAMES = [
    "create_content", "refine_content", "generate_title_options", "optimize_seo",
    "view_content", "list_recent_contents", "add_to_calendar", "view_calendar",
    "get_content_stats", "check_xiaohongshu_login", "search_history",
]
PLANNER_SYSTEM_PROMPT = (
    "You are a planner. Given the user's request and the available tools, "
    "output a JSON array of steps.\n"
    'Schema: [{"index": 1, "description": "...", "tool_hint": "tool_name_or_null"}].\n'
    "Rules: at most 5 steps; output JSON only, no prose, no markdown fence.\n"
    f"Available tools: {', '.join(AVAILABLE_TOOL_NAMES)}."
)


SYSTEM_PROMPT_TEMPLATE = """You are Content Ops Agent, a production assistant for content operations.
Today is {today} ({weekday}). When the user uses relative dates like "tomorrow", "next Monday", or "下周一",
resolve them to an absolute YYYY-MM-DD value before calling any tool.
Answer in the user's language. Use tools when the user asks to create content, refine stored content,
inspect recent content, manage the publishing calendar, or check content statistics.
Do not claim that content was saved or scheduled unless a tool result confirms it."""


_WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _build_system_prompt() -> str:
    today = datetime.now()
    return SYSTEM_PROMPT_TEMPLATE.format(
        today=today.strftime("%Y-%m-%d"),
        weekday=_WEEKDAY_CN[today.weekday()],
    )


ModelFactory = Callable[[str, str, float, int], Any]


class ChatAgentExecutionError(RuntimeError):
    """Raised when the chat Agent cannot complete a request."""


class ChatAgentService:
    def __init__(
        self,
        store: ContentStore,
        llm: LiteLLMClient | None = None,
        model_factory: ModelFactory | None = None,
    ):
        self.store = store
        self.llm = llm or LiteLLMClient()
        self.model_factory = model_factory or self._create_chat_model

    async def chat(self, request: ChatRequest) -> ChatResponse:
        provider = resolve_provider(request.provider)
        model = request.model or config.get_model(provider)
        thread_id = request.thread_id or f"chat_{uuid4().hex[:10]}"
        title = self._make_thread_title(request.message)

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
    ) -> tuple[str, list[ChatToolEvent], list[PlanStep]]:
        plan = plan or []
        tools = self._build_tools(provider, model, temperature, max_tokens)
        tools_by_name = {tool.name: tool for tool in tools}
        chat_model = self.model_factory(provider, model, temperature, max_tokens)
        if hasattr(chat_model, "bind_tools"):
            chat_model = chat_model.bind_tools(tools)

        system_prompt = _build_system_prompt()
        if plan:
            numbered = "\n".join(
                f"  {step.index}. {step.description}"
                + (f" [hint: {step.tool_hint}]" if step.tool_hint else "")
                for step in plan
            )
            system_prompt = (
                f"{system_prompt}\n\nHere is your plan for this request:\n{numbered}\n"
                "Mark progress by calling tools roughly in this order. "
                "If a step does not need a tool, you may skip it."
            )

        messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]
        messages.extend(self._history_to_messages(history))
        messages.append(HumanMessage(content=message))

        tool_events: list[ChatToolEvent] = []
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

            publish_date MUST be an absolute YYYY-MM-DD string. Convert relative phrases
            like "tomorrow", "next Monday", or "下周一" to YYYY-MM-DD before calling.
            """
            content = self.store.get_content(content_id)
            if not content:
                return f"Content {content_id} was not found."
            scheduled_date = datetime.strptime(publish_date, "%Y-%m-%d").date()
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
        ]

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

        return ChatOpenAI(
            api_key=api_key,
            base_url=config.get_provider_api_base(provider),
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

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
