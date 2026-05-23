"""Sub-agent pool used by the dynamic Studio pipeline.

Six pre-defined specialists. Strategy / Writer / Editor / Reviewer are pure LLM steps
(no tools). Researcher / FactChecker may invoke a whitelist of read-only tools that
are reused from chat_agent (search_history, view_content, list_recent_contents)
plus a public web search.

The runner returns a uniform tuple `(text, prompt_tokens, completion_tokens, duration_ms,
cost_estimate)` so DynamicPipeline can keep the per-step accounting in one place.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool

from src.api.schemas.agent import SubAgentId
from src.llm.litellm_client import LiteLLMClient
from src.storage import ContentStore
from src.tools.web_search import web_search as run_web_search
from src.utils import config


@dataclass(frozen=True)
class SubAgentSpec:
    id: SubAgentId
    name: str
    role: str
    system_prompt: str
    tools: tuple[str, ...] = ()
    temperature: float = 0.7
    max_tokens: int | None = None  # if set, overrides the request-level cap for this sub-agent


SUB_AGENTS: dict[SubAgentId, SubAgentSpec] = {
    "strategy": SubAgentSpec(
        id="strategy",
        name="Strategy Agent",
        role="内容策略",
        system_prompt=(
            "You are a senior content strategist. Create a concise strategy for the requested "
            "platform. Include audience, angle, structure, hook, and conversion intent. "
            "Write in the same language as the user's topic."
        ),
        temperature=0.5,
    ),
    "writer": SubAgentSpec(
        id="writer",
        name="Writer Agent",
        role="初稿写作",
        system_prompt=(
            "You are a platform-native content writer. Use the provided context to produce a "
            "complete first draft. Keep the output ready to edit and write in the same language "
            "as the user's topic."
        ),
        temperature=0.85,
    ),
    "editor": SubAgentSpec(
        id="editor",
        name="Editor Agent",
        role="润色编辑",
        system_prompt=(
            "You are a professional content editor. Improve clarity, rhythm, structure, "
            "platform fit, and persuasiveness. Return only the final polished content."
        ),
        temperature=0.5,
    ),
    "reviewer": SubAgentSpec(
        id="reviewer",
        name="Review Agent",
        role="质量审核",
        system_prompt=(
            "You are a content quality reviewer. Score the final content from 1 to 100 and list "
            "strengths, risks, and practical improvements. Begin your reply with `Score: <number>` "
            "on its own line so the score can be parsed."
        ),
        temperature=0.3,
        max_tokens=2048,  # reviewer needs more headroom: score + strengths + risks + suggestions
    ),
    "researcher": SubAgentSpec(
        id="researcher",
        name="Researcher Agent",
        role="研究员",
        system_prompt=(
            "You are a research specialist. You have these tools available:\n"
            "- search_history(query): search prior content saved in this workspace\n"
            "- list_recent_contents(): list latest items in the workspace\n"
            "- view_content(content_id): read a specific saved item\n"
            "- web_search(query): run a public web search (DuckDuckGo)\n\n"
            "When the topic could benefit from prior context or external facts, call the "
            "appropriate tool(s) before answering. If you are confident the topic is generic "
            "enough that you can answer from your own knowledge, you may skip tools — that "
            "decision is yours.\n\n"
            "After any tool calls (or directly if you skipped them), summarize the key findings "
            "the writer should know — keep it tight, prefer 5-8 bullet points."
        ),
        tools=("search_history", "view_content", "list_recent_contents", "web_search"),
        temperature=0.4,
    ),
    "fact_checker": SubAgentSpec(
        id="fact_checker",
        name="Fact Checker Agent",
        role="事实校验",
        system_prompt=(
            "You are a fact checker. Identify any concrete claims (numbers, dates, names, "
            "quotes) in the provided draft. For each claim that is non-obvious, call "
            "`search_history` or `web_search` to verify it. Skip claims that are clearly "
            "common knowledge — that judgment is yours.\n\n"
            "Return a list of `Claim → Verdict (verified | unverified | contradicted) → Source`."
        ),
        tools=("search_history", "view_content", "web_search"),
        temperature=0.3,
    ),
}


# Pricing per 1K tokens (USD). Rough; used for "演示成本" indicator only.
# Note: many SiliconFlow models are free or near-free; we under-estimate slightly which
# is the safer direction for a demo.
PRICE_PER_1K = {
    "claude-3-5-sonnet": (3.0, 15.0),
    "claude-3-5-haiku": (0.8, 4.0),
    "deepseek-v4-flash": (0.27, 1.10),
    "deepseek-v4-pro": (0.55, 2.19),
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
    "Qwen/Qwen2.5-7B-Instruct": (0.07, 0.07),
    "moonshot-v1-8k": (1.0, 1.0),
    "moonshot-v1-32k": (2.0, 2.0),
}


def estimate_cost(model: str | None, prompt_tokens: int, completion_tokens: int) -> float:
    if not model:
        return 0.0
    base = model.split("/")[-1]  # strip openai/ deepseek/ etc.
    p_rate, c_rate = PRICE_PER_1K.get(base, (0.5, 0.5))
    return round((prompt_tokens / 1000.0) * p_rate + (completion_tokens / 1000.0) * c_rate, 6)


# Token emit callback signature: async (delta_text) -> None
TokenSink = Callable[[str], Awaitable[None]]
ToolSink = Callable[[str, dict[str, Any]], Awaitable[None]]


class SubAgentRunner:
    """Executes a single sub-agent step.

    Responsibilities:
      - Build the LLM prompt from the sub-agent's system prompt + caller-supplied user prompt
      - Invoke the LLM (stream-aware when token_sink is provided)
      - For tool-using agents (researcher / fact_checker) wrap the call in a bounded
        bind_tools loop, restricted to the agent's tool whitelist
      - Emit (start, result) pairs via tool_sink so callers can show tool traces
      - Return (text, prompt_tokens, completion_tokens, duration_ms, cost)
    """

    MAX_TOOL_LOOPS = 4

    def __init__(self, store: ContentStore, llm: LiteLLMClient | None = None, model_factory: Callable | None = None):
        self.store = store
        self.llm = llm or LiteLLMClient()
        self.model_factory = model_factory or self._default_model_factory

    async def run(
        self,
        spec: SubAgentSpec,
        user_prompt: str,
        provider: str,
        model: str,
        max_tokens: int = 2048,
        token_sink: TokenSink | None = None,
        tool_sink: ToolSink | None = None,
    ) -> tuple[str, int, int, int, float]:
        effective_max_tokens = spec.max_tokens or max_tokens
        if spec.tools:
            text, p_tok, c_tok = await self._run_with_tools(
                spec, user_prompt, provider, model, effective_max_tokens, tool_sink
            )
        else:
            text, p_tok, c_tok = await self._run_plain(
                spec, user_prompt, provider, model, effective_max_tokens, token_sink
            )
        duration_ms = 0  # set by caller via time.perf_counter; we still return 0 here
        cost = estimate_cost(model, p_tok, c_tok)
        return text.strip(), p_tok, c_tok, duration_ms, cost

    # -- Plain (non-tool) path -------------------------------------------------

    async def _run_plain(
        self,
        spec: SubAgentSpec,
        user_prompt: str,
        provider: str,
        model: str,
        max_tokens: int,
        token_sink: TokenSink | None,
    ) -> tuple[str, int, int]:
        if token_sink is None:
            text = await self.llm.generate_from_prompts(
                provider=provider,
                model=model,
                system_prompt=spec.system_prompt,
                user_prompt=user_prompt,
                temperature=spec.temperature,
                max_tokens=max_tokens,
            )
            return text, 0, 0

        # Streaming path
        accumulated = ""
        prompt_tokens = 0
        completion_tokens = 0
        async for chunk in self.llm.generate_stream(
            provider=provider,
            model=model,
            system_prompt=spec.system_prompt,
            user_prompt=user_prompt,
            temperature=spec.temperature,
            max_tokens=max_tokens,
        ):
            if chunk.delta:
                accumulated += chunk.delta
                await token_sink(chunk.delta)
            if chunk.usage is not None:
                prompt_tokens, completion_tokens = chunk.usage
        return accumulated, prompt_tokens, completion_tokens

    # -- Tool-using path -------------------------------------------------------

    async def _run_with_tools(
        self,
        spec: SubAgentSpec,
        user_prompt: str,
        provider: str,
        model: str,
        max_tokens: int,
        tool_sink: ToolSink | None = None,
    ) -> tuple[str, int, int]:
        tools = self._build_whitelisted_tools(spec.tools)
        tools_by_name = {t.name: t for t in tools}
        chat_model = self.model_factory(provider, model, spec.temperature, max_tokens)
        if hasattr(chat_model, "bind_tools"):
            chat_model = chat_model.bind_tools(tools)

        messages: list[BaseMessage] = [
            SystemMessage(content=spec.system_prompt),
            HumanMessage(content=user_prompt),
        ]
        last_text = ""
        prompt_tokens = 0
        completion_tokens = 0
        for _ in range(self.MAX_TOOL_LOOPS):
            ai_message = await chat_model.ainvoke(messages)
            messages.append(ai_message)
            last_text = self._message_text(ai_message.content)
            usage = getattr(ai_message, "usage_metadata", None) or {}
            prompt_tokens += int(usage.get("input_tokens", 0) or 0)
            completion_tokens += int(usage.get("output_tokens", 0) or 0)
            tool_calls = getattr(ai_message, "tool_calls", None) or []
            if not tool_calls:
                break
            for call in tool_calls:
                name = call.get("name", "")
                args = call.get("args") or {}
                tool = tools_by_name.get(name)
                started = time.perf_counter()
                if tool_sink is not None:
                    try:
                        await tool_sink("tool_call_start", {"name": name, "args": args})
                    except Exception:
                        pass
                if not tool:
                    output = f"Tool `{name}` is not available to {spec.id}."
                    duration_ms = int((time.perf_counter() - started) * 1000)
                    if tool_sink is not None:
                        try:
                            await tool_sink("tool_call_result", {
                                "name": name, "args": args, "status": "failed",
                                "error": output, "preview": "", "duration_ms": duration_ms,
                            })
                        except Exception:
                            pass
                else:
                    try:
                        raw = await tool.ainvoke(args) if hasattr(tool, "ainvoke") else tool.invoke(args)
                        output = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
                        duration_ms = int((time.perf_counter() - started) * 1000)
                        if tool_sink is not None:
                            try:
                                await tool_sink("tool_call_result", {
                                    "name": name, "args": args, "status": "completed",
                                    "preview": output[:300], "duration_ms": duration_ms,
                                })
                            except Exception:
                                pass
                    except Exception as exc:
                        output = f"Tool failed: {exc}"
                        duration_ms = int((time.perf_counter() - started) * 1000)
                        if tool_sink is not None:
                            try:
                                await tool_sink("tool_call_result", {
                                    "name": name, "args": args, "status": "failed",
                                    "error": str(exc), "preview": "", "duration_ms": duration_ms,
                                })
                            except Exception:
                                pass
                messages.append(ToolMessage(content=output, tool_call_id=call.get("id") or name or "x"))
        return last_text or "(no output)", prompt_tokens, completion_tokens

    def _build_whitelisted_tools(self, allowed: tuple[str, ...]) -> list[StructuredTool]:
        from src.api.services import content_service  # noqa: F401  (kept for parity with chat_agent imports)

        def search_history(query: str, limit: int = 10) -> str:
            """Search saved content by keyword across title, body, and keywords."""
            return json.dumps(self.store.search_contents(query, limit), ensure_ascii=False)

        def view_content(content_id: int) -> str:
            """Read a saved content item by id."""
            row = self.store.get_content(content_id)
            return json.dumps(row, ensure_ascii=False) if row else f"Content {content_id} was not found."

        def list_recent_contents(limit: int = 10) -> str:
            """List recent saved content items."""
            return json.dumps(self.store.list_contents(limit=limit), ensure_ascii=False)

        async def web_search(query: str, limit: int = 5) -> str:
            """Run a public web search via DuckDuckGo and return top results as JSON."""
            results = await run_web_search(query, limit=limit)
            return json.dumps(results, ensure_ascii=False)

        catalog = {
            "search_history": StructuredTool.from_function(func=search_history, name="search_history"),
            "view_content": StructuredTool.from_function(func=view_content, name="view_content"),
            "list_recent_contents": StructuredTool.from_function(func=list_recent_contents, name="list_recent_contents"),
            "web_search": StructuredTool.from_function(coroutine=web_search, name="web_search"),
        }
        return [catalog[name] for name in allowed if name in catalog]

    @staticmethod
    def _default_model_factory(provider: str, model: str, temperature: float, max_tokens: int):
        api_key = config.get_api_key(provider)
        if not api_key:
            raise ValueError(f"Missing API key for provider: {provider}")
        if provider == "claude":
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(api_key=api_key, model=model, temperature=temperature, max_tokens=max_tokens)
        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {
            "api_key": api_key,
            "base_url": config.get_provider_api_base(provider),
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        # DeepSeek V4 defaults to thinking mode; in multi-turn tool loops it expects
        # `reasoning_content` to be echoed back, which LangChain ChatOpenAI does not
        # carry through. Disable thinking so each round is a clean chat completion.
        if provider == "deepseek":
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        return ChatOpenAI(**kwargs)

    @staticmethod
    def _message_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False)
