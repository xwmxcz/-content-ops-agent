"""Intent recognition for the Chat Agent surface."""
from __future__ import annotations

import json
import re
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage

from src.api.schemas.agent import ChatIntent, ChatIntentName


ModelFactory = Callable[[str, str, float, int], Any]

INTENT_TEMPERATURE = 0.1
INTENT_MAX_TOKENS = 512
INTENT_MIN_CONFIDENCE = 0.55

INTENT_ALLOWED_TOOLS: dict[ChatIntentName, list[str]] = {
    "content_create": ["create_content"],
    "content_refine": ["search_history", "view_content", "refine_content"],
    "title_generate": ["search_history", "view_content", "generate_title_options"],
    "seo_optimize": ["view_content", "optimize_seo"],
    "content_search": ["search_history", "view_content", "list_recent_contents", "session_search"],
    "topic_strategy": ["analyze_content_performance", "web_search", "propose_topics", "search_history"],
    "performance_review": ["find_optimization_candidates", "analyze_content_performance", "get_content_stats"],
    "calendar_view": ["view_calendar", "search_history", "view_content"],
    "schedule_propose": ["list_recent_contents", "search_history", "view_calendar", "propose_publishing_schedule"],
    "schedule_commit": ["commit_publishing_schedule"],
    "memory_update": ["memory_add", "memory_replace", "memory_remove"],
    "smalltalk": [],
    "clarify": [],
    "unknown": [],
}

PLAN_EXEMPT_INTENTS: set[ChatIntentName] = {"smalltalk", "clarify", "unknown", "schedule_commit"}

INTENT_SYSTEM_PROMPT = """You are an intent recognizer for a content operations assistant.

Choose exactly one intent from:
- content_create
- content_refine
- title_generate
- seo_optimize
- content_search
- topic_strategy
- performance_review
- calendar_view
- schedule_propose
- schedule_commit
- memory_update
- smalltalk
- clarify
- unknown

Use:
- content_create for writing or generating a new piece of content
- content_refine for rewriting, polishing, or improving an existing piece
- title_generate for asking for title options
- seo_optimize for SEO analysis or optimization
- content_search for looking up recent or previous content
- topic_strategy for topic ideas, weekly planning, content direction, or what to write next
- performance_review for asking what should be improved, optimized, or reviewed retrospectively
- calendar_view for viewing an existing publishing calendar
- schedule_propose for proposing a publishing plan without committing it
- schedule_commit only when the user is confirming a previously proposed schedule
- memory_update for durable preference or memory changes
- smalltalk for casual chat or greetings
- clarify when the request is ambiguous or is missing the target/action
- unknown when none clearly fit

Output JSON only:
{
  "name": "content_search",
  "confidence": 0.84,
  "slots": {},
  "clarification": null
}
"""

_CONTENT_SEARCH_RE = re.compile(
    r"(show|find|search|recent|previous|history|之前写过|最近内容|查一下|找一下|历史|回忆|show content|show recent|recent posts)",
    re.IGNORECASE,
)
_CONTENT_REFINE_RE = re.compile(
    r"(改写|润色|重写|优化这篇|优化一下这篇|rewrite|polish|refine|make it more practical)",
    re.IGNORECASE,
)
_TITLE_RE = re.compile(r"(标题|title)", re.IGNORECASE)
_SEO_RE = re.compile(r"(seo|搜索优化)", re.IGNORECASE)
_TOPIC_RE = re.compile(
    r"(选题|内容策略|写什么|what should we write|topic ideas|content strategy|plan a content week|内容周计划)",
    re.IGNORECASE,
)
_PERFORMANCE_RE = re.compile(
    r"(值得优化|值得改|哪些内容值得|复盘|哪些要优化|underperform|performance review|optimi[sz]e candidates)",
    re.IGNORECASE,
)
_CALENDAR_VIEW_RE = re.compile(r"(看.*日历|看.*排期|calendar|发布日历|本周排期|view calendar)", re.IGNORECASE)
_SCHEDULE_PROPOSE_RE = re.compile(
    r"(排.*发布计划|排期|发布计划|schedule|calendar week|publishing plan|安排发布)",
    re.IGNORECASE,
)
_MEMORY_RE = re.compile(r"(记住|记一下|更新偏好|remember this|remember that|save to memory)", re.IGNORECASE)
_CREATE_RE = re.compile(r"(写一篇|写个|生成一篇|生成个|create|write|draft|写作|起草)", re.IGNORECASE)
_SMALLTALK_RE = re.compile(r"^(hi|hello|hey|你好|您好|在吗|just chat with me)\b", re.IGNORECASE)
_AMBIGUOUS_RE = re.compile(r"(帮我处理一下|处理一下这篇|处理一下这个|帮我弄一下这篇|帮我处理这篇)", re.IGNORECASE)
_CONFIRM_RE = re.compile(
    r"(好的|好呀|好|开始吧|开始排吧|排吧|可以|行|ok|okay|yes|yep|sure|go ahead|do it)",
    re.IGNORECASE,
)
_RESEARCH_HEAVY_RE = re.compile(
    r"(横评|对比|盘点|评测|vs\b|compare|事实核查|fact[\s-]?check|最新|今年|趋势|数据|\b20\d{2}\b)",
    re.IGNORECASE,
)


class IntentRecognizer:
    def __init__(self, model_factory: ModelFactory):
        self.model_factory = model_factory

    async def recognize(
        self,
        *,
        message: str,
        history: list[dict[str, Any]],
        provider: str,
        model: str,
    ) -> ChatIntent:
        rule_intent = self._match_rule(message, history)
        if rule_intent is not None:
            return rule_intent

        llm_intent = await self._classify_with_llm(
            message=message,
            history=history,
            provider=provider,
            model=model,
        )
        return self._finalize_intent(llm_intent, message=message, history=history)

    async def _classify_with_llm(
        self,
        *,
        message: str,
        history: list[dict[str, Any]],
        provider: str,
        model: str,
    ) -> ChatIntent:
        chat_model = self.model_factory(provider, model, INTENT_TEMPERATURE, INTENT_MAX_TOKENS)
        messages = [SystemMessage(content=INTENT_SYSTEM_PROMPT)]
        last_messages = history[-6:]
        if last_messages:
            transcript = []
            for item in last_messages:
                role = item.get("role", "assistant")
                transcript.append(f"{role}: {item.get('content', '')}")
            messages.append(SystemMessage(content="Recent context:\n" + "\n".join(transcript)))
        messages.append(HumanMessage(content=message))
        try:
            ai_message = await chat_model.ainvoke(messages)
            raw = self._message_content_to_text(ai_message.content).strip()
            payload = json.loads(self._strip_fence(raw))
        except Exception:
            return self._clarify_intent(message)

        if not isinstance(payload, dict):
            return self._clarify_intent(message)

        name = str(payload.get("name") or "unknown").strip()
        confidence = self._safe_confidence(payload.get("confidence"))
        slots = payload.get("slots") if isinstance(payload.get("slots"), dict) else {}
        clarification = payload.get("clarification")
        if name not in INTENT_ALLOWED_TOOLS:
            name = "unknown"
        if confidence < INTENT_MIN_CONFIDENCE:
            return self._clarify_intent(message)
        return self._finalize_intent(
            ChatIntent(name=name, confidence=confidence, slots=slots, clarification=clarification),
            message=message,
            history=history,
        )

    def _match_rule(self, message: str, history: list[dict[str, Any]]) -> ChatIntent | None:
        text = (message or "").strip()
        lowered = text.lower()

        if not text:
            return self._clarify_intent(message)
        if self._matches_schedule_commit(text, history):
            slots = self._extract_last_schedule_plan(history)
            return self._finalize_intent(
                ChatIntent(name="schedule_commit", confidence=0.98, slots=slots),
                message=message,
                history=history,
            )
        if _AMBIGUOUS_RE.search(text):
            return self._clarify_intent(message)
        if _SMALLTALK_RE.search(text) or lowered in {"hi", "hello", "hey", "next"}:
            return self._finalize_intent(ChatIntent(name="smalltalk", confidence=0.9), message=message, history=history)
        if _MEMORY_RE.search(text):
            return self._finalize_intent(ChatIntent(name="memory_update", confidence=0.96), message=message, history=history)
        if _SEO_RE.search(text):
            return self._finalize_intent(ChatIntent(name="seo_optimize", confidence=0.96), message=message, history=history)
        if _TITLE_RE.search(text) and re.search(r"(生成|给|想|title|标题)", text, re.IGNORECASE):
            return self._finalize_intent(ChatIntent(name="title_generate", confidence=0.95), message=message, history=history)
        if _PERFORMANCE_RE.search(text):
            return self._finalize_intent(ChatIntent(name="performance_review", confidence=0.95), message=message, history=history)
        if _CALENDAR_VIEW_RE.search(text) and not _SCHEDULE_PROPOSE_RE.search(text):
            return self._finalize_intent(ChatIntent(name="calendar_view", confidence=0.94), message=message, history=history)
        if _SCHEDULE_PROPOSE_RE.search(text):
            return self._finalize_intent(ChatIntent(name="schedule_propose", confidence=0.94), message=message, history=history)
        if _TOPIC_RE.search(text):
            return self._finalize_intent(ChatIntent(name="topic_strategy", confidence=0.92), message=message, history=history)
        if _CONTENT_REFINE_RE.search(text):
            return self._finalize_intent(ChatIntent(name="content_refine", confidence=0.93), message=message, history=history)
        if _CONTENT_SEARCH_RE.search(text) or re.search(r"\bcontent\s+\d+\b", text, re.IGNORECASE):
            return self._finalize_intent(ChatIntent(name="content_search", confidence=0.9), message=message, history=history)
        if _CREATE_RE.search(text):
            return self._finalize_intent(ChatIntent(name="content_create", confidence=0.92), message=message, history=history)
        if len(text) <= 20 or len(text.split()) <= 4:
            return self._finalize_intent(ChatIntent(name="unknown", confidence=0.62), message=message, history=history)
        return None

    def _finalize_intent(
        self,
        intent: ChatIntent,
        *,
        message: str,
        history: list[dict[str, Any]],
    ) -> ChatIntent:
        name = intent.name
        slots = dict(intent.slots or {})
        route_surface = intent.route_surface or "chat"
        route_reason = intent.route_reason

        if name == "content_create" and self._is_research_heavy_request(message):
            route_surface = "studio"
            route_reason = "research-heavy content request"
            slots.setdefault("research_focus", self._infer_research_focus(message))

        if name == "schedule_commit":
            slots.update(self._extract_last_schedule_plan(history))

        requires_confirmation = self._should_require_confirmation(name, message)
        clarification = intent.clarification
        if name == "clarify" and not clarification:
            clarification = self._default_clarification(message)

        allowed_tools = [] if route_surface == "studio" else list(INTENT_ALLOWED_TOOLS.get(name, []))

        return ChatIntent(
            name=name,
            confidence=intent.confidence,
            slots=slots,
            requires_confirmation=requires_confirmation,
            allowed_tools=allowed_tools,
            route_surface=route_surface,
            route_reason=route_reason,
            clarification=clarification,
        )

    def _matches_schedule_commit(self, message: str, history: list[dict[str, Any]]) -> bool:
        if not _CONFIRM_RE.search(message.strip()):
            return False
        last_assistant = self._last_assistant_message(history)
        if not last_assistant:
            return False
        last_intent = last_assistant.get("intent") or {}
        if last_intent.get("name") != "schedule_propose":
            return False
        for event in last_assistant.get("tool_events") or []:
            if event.get("name") == "propose_publishing_schedule" and event.get("status") == "completed":
                return True
        content = (last_assistant.get("content") or "").lower()
        return "proposal" in content or "发布计划" in content or "排期" in content

    def _extract_last_schedule_plan(self, history: list[dict[str, Any]]) -> dict[str, Any]:
        last_assistant = self._last_assistant_message(history)
        if not last_assistant:
            return {}
        for event in reversed(last_assistant.get("tool_events") or []):
            if event.get("name") != "propose_publishing_schedule" or event.get("status") != "completed":
                continue
            output = event.get("output") or ""
            try:
                payload = json.loads(output)
            except Exception:
                continue
            if isinstance(payload, dict) and isinstance(payload.get("plan"), list):
                return {"proposal_plan": payload["plan"]}
        return {}

    @staticmethod
    def _last_assistant_message(history: list[dict[str, Any]]) -> dict[str, Any] | None:
        for item in reversed(history):
            if item.get("role") == "assistant":
                return item
        return None

    @staticmethod
    def _should_require_confirmation(name: ChatIntentName, message: str) -> bool:
        if name not in {"content_create", "content_refine", "memory_update"}:
            return False
        return not bool(re.search(r"(现在|立刻|马上|now|right away|please do)", message, re.IGNORECASE))

    @staticmethod
    def _is_research_heavy_request(message: str) -> bool:
        return bool(_RESEARCH_HEAVY_RE.search(message))

    @staticmethod
    def _infer_research_focus(message: str) -> str:
        lowered = message.lower()
        if "事实核查" in message or "fact check" in lowered:
            return "verify claims"
        if "横评" in message or "对比" in message or "vs" in lowered or "compare" in lowered:
            return "compare alternatives"
        return "recent developments"

    @staticmethod
    def _clarify_intent(message: str) -> ChatIntent:
        return ChatIntent(
            name="clarify",
            confidence=0.4,
            clarification=IntentRecognizer._default_clarification(message),
            allowed_tools=[],
            route_surface="chat",
        )

    @staticmethod
    def _default_clarification(message: str) -> str:
        if re.search(r"[\u4e00-\u9fff]", message or ""):
            return "我还不确定你是想让我改写内容、生成标题、做 SEO 优化，还是安排发布。请再具体一点。"
        return "I’m not sure whether you want a rewrite, title ideas, SEO help, or publishing support. Please be a bit more specific."

    @staticmethod
    def _safe_confidence(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, number))

    @staticmethod
    def _strip_fence(raw: str) -> str:
        return re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE | re.DOTALL).strip()

    @staticmethod
    def _message_content_to_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False)
