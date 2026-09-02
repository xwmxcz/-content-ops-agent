"""Intent recognition for the Chat Agent surface."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage

from src.api.schemas.agent import ChatIntent, ChatIntentName
from src.api.services.tool_policy import SIDE_EFFECT_TOOLS
from src.utils import config
from src.utils.canonical import args_hash
from src.utils.structured_logging import log_event


logger = logging.getLogger(__name__)

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
    "action_confirm": [],  # populated from the persisted proposed tool event
    "smalltalk": [],
    "clarify": [],
    "unknown": [],
}

PLAN_EXEMPT_INTENTS: set[ChatIntentName] = {"smalltalk", "clarify", "unknown", "schedule_commit", "action_confirm"}
SERVER_ONLY_CONFIRMATION_INTENTS: set[ChatIntentName] = {"schedule_commit", "action_confirm"}

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
- action_confirm
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
- action_confirm only when the user confirms the exact write action proposed in the immediately preceding assistant turn
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
# Confirmation is an authorization signal, so it must be the whole message —
# not a substring such as "don't do it", "not okay", or quoted/injected text.
# Multiple affirmative phrases remain natural ("yes, do it" / "好的，开始排吧").
_CONFIRM_TOKEN = r"(?:好的?|好呀|开始吧|开始排吧|排吧|可以|行|确认|ok(?:ay)?|yes|yep|sure|confirm|go\s+ahead|do\s+it)"
_CONFIRM_RE = re.compile(
    rf"^\s*{_CONFIRM_TOKEN}(?:[\s,，。.!！;；]+{_CONFIRM_TOKEN})*[\s。.!！]*$",
    re.IGNORECASE,
)
_RESEARCH_HEAVY_RE = re.compile(
    r"(横评|对比|盘点|评测|vs\b|compare|事实核查|fact[\s-]?check|最新|今年|趋势|数据|\b20\d{2}\b)",
    re.IGNORECASE,
)


class IntentRecognizer:
    def __init__(self, model_factory: ModelFactory, *, store: Any | None = None):
        # ``store`` is keyword-with-default so the recognizer stays constructible
        # in isolation. Without it there is no durable capability to confirm and
        # every write proposal fails closed at the executor.
        self.model_factory = model_factory
        self.store = store

    async def recognize(
        self,
        *,
        message: str,
        history: list[dict[str, Any]],
        provider: str,
        model: str,
        thread_id: str | None = None,
    ) -> ChatIntent:
        rule_intent = self._match_rule(message, history, thread_id=thread_id)
        if rule_intent is not None:
            return rule_intent

        llm_intent = await self._classify_with_llm(
            message=message,
            history=history,
            provider=provider,
            model=model,
            thread_id=thread_id,
        )
        return llm_intent

    async def _classify_with_llm(
        self,
        *,
        message: str,
        history: list[dict[str, Any]],
        provider: str,
        model: str,
        thread_id: str | None = None,
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
        # The classifier is model-controlled routing advice. Confirmation names
        # are exclusively produced by _match_rule() after the server validates
        # the raw current message and persisted preceding proposal.
        if name in SERVER_ONLY_CONFIRMATION_INTENTS:
            name = "unknown"
            slots = {}
        if confidence < INTENT_MIN_CONFIDENCE:
            return self._clarify_intent(message)
        return self._finalize_intent(
            ChatIntent(name=name, confidence=confidence, slots=slots, clarification=clarification),
            message=message,
            history=history,
            thread_id=thread_id,
        )

    def _match_rule(
        self,
        message: str,
        history: list[dict[str, Any]],
        *,
        thread_id: str | None = None,
    ) -> ChatIntent | None:
        text = (message or "").strip()
        lowered = text.lower()

        if not text:
            return self._clarify_intent(message)
        if self._matches_action_confirm(text, history, thread_id=thread_id):
            slots = self._extract_last_proposed_action(history, thread_id=thread_id)
            return self._finalize_intent(
                ChatIntent(name="action_confirm", confidence=0.99, slots=slots),
                message=message,
                history=history,
                thread_id=thread_id,
            )
        if self._matches_schedule_commit(text, history):
            slots = self._extract_last_schedule_plan(history)
            return self._finalize_intent(
                ChatIntent(name="schedule_commit", confidence=0.98, slots=slots),
                message=message,
                history=history,
                thread_id=thread_id,
            )
        if _AMBIGUOUS_RE.search(text):
            return self._clarify_intent(message)
        if _SMALLTALK_RE.search(text) or lowered in {"hi", "hello", "hey", "next"}:
            return self._finalize_intent(ChatIntent(name="smalltalk", confidence=0.9), message=message, history=history, thread_id=thread_id)
        if _MEMORY_RE.search(text):
            return self._finalize_intent(ChatIntent(name="memory_update", confidence=0.96), message=message, history=history, thread_id=thread_id)
        if _SEO_RE.search(text):
            return self._finalize_intent(ChatIntent(name="seo_optimize", confidence=0.96), message=message, history=history, thread_id=thread_id)
        if _TITLE_RE.search(text) and re.search(r"(生成|给|想|title|标题)", text, re.IGNORECASE):
            return self._finalize_intent(ChatIntent(name="title_generate", confidence=0.95), message=message, history=history, thread_id=thread_id)
        if _PERFORMANCE_RE.search(text):
            return self._finalize_intent(ChatIntent(name="performance_review", confidence=0.95), message=message, history=history, thread_id=thread_id)
        if _CALENDAR_VIEW_RE.search(text) and not _SCHEDULE_PROPOSE_RE.search(text):
            return self._finalize_intent(ChatIntent(name="calendar_view", confidence=0.94), message=message, history=history, thread_id=thread_id)
        if _SCHEDULE_PROPOSE_RE.search(text):
            return self._finalize_intent(ChatIntent(name="schedule_propose", confidence=0.94), message=message, history=history, thread_id=thread_id)
        if _TOPIC_RE.search(text):
            return self._finalize_intent(ChatIntent(name="topic_strategy", confidence=0.92), message=message, history=history, thread_id=thread_id)
        if _CONTENT_REFINE_RE.search(text):
            return self._finalize_intent(ChatIntent(name="content_refine", confidence=0.93), message=message, history=history, thread_id=thread_id)
        if _CONTENT_SEARCH_RE.search(text) or re.search(r"\bcontent\s+\d+\b", text, re.IGNORECASE):
            return self._finalize_intent(ChatIntent(name="content_search", confidence=0.9), message=message, history=history, thread_id=thread_id)
        if _CREATE_RE.search(text):
            return self._finalize_intent(ChatIntent(name="content_create", confidence=0.92), message=message, history=history, thread_id=thread_id)
        if len(text) <= 20 or len(text.split()) <= 4:
            return self._finalize_intent(ChatIntent(name="unknown", confidence=0.62), message=message, history=history, thread_id=thread_id)
        return None

    def _finalize_intent(
        self,
        intent: ChatIntent,
        *,
        message: str,
        history: list[dict[str, Any]],
        thread_id: str | None = None,
    ) -> ChatIntent:
        name = intent.name
        slots = dict(intent.slots or {})
        route_surface = intent.route_surface or "chat"
        route_reason = intent.route_reason
        confirmation_validated = bool(_CONFIRM_RE.fullmatch((message or "").strip()))

        # LLM classification is routing advice, never approval. Both rule and
        # model paths converge here, so a denial or an embedded/qualified phrase
        # cannot be converted into action_confirm/schedule_commit by the model.
        if name in {"action_confirm", "schedule_commit"} and not confirmation_validated:
            name = "unknown"
            slots = {}
            route_surface = "chat"
            route_reason = "confirmation rejected by server grammar"

        if name == "content_create" and self._is_research_heavy_request(message):
            route_surface = "studio"
            route_reason = "research-heavy content request"
            slots.setdefault("research_focus", self._infer_research_focus(message))

        if name == "schedule_commit":
            slots.update(self._extract_last_schedule_plan(history))
        if name == "action_confirm":
            slots.update(self._extract_last_proposed_action(history, thread_id=thread_id))

        requires_confirmation = self._should_require_confirmation(name, message)
        clarification = intent.clarification
        if name == "clarify" and not clarification:
            clarification = self._default_clarification(message)

        if route_surface == "studio":
            allowed_tools = []
        elif name == "action_confirm":
            approved_tool = slots.get("approved_tool_name")
            allowed_tools = [approved_tool] if approved_tool in SIDE_EFFECT_TOOLS else []
        else:
            allowed_tools = list(INTENT_ALLOWED_TOOLS.get(name, []))

        result = ChatIntent(
            name=name,
            confidence=intent.confidence,
            slots=slots,
            requires_confirmation=requires_confirmation,
            allowed_tools=allowed_tools,
            route_surface=route_surface,
            route_reason=route_reason,
            clarification=clarification,
        )
        if name in SERVER_ONLY_CONFIRMATION_INTENTS and confirmation_validated:
            # PrivateAttr is request-local and cannot be supplied by classifier
            # JSON, persisted slots, or a previous assistant message. Bind a
            # deep-copied exact call as the authorization evidence; public slots
            # remain display/routing data and are never trusted by the executor.
            #
            # The durable capability is claimed here: confirming moves exactly one
            # `proposed` row to `confirmed`. Two concurrent confirmations of the
            # same proposal mean only one request receives an action id, so the
            # other has argument evidence but nothing to consume.
            if name == "action_confirm":
                approved_tool = slots.get("approved_tool_name")
                approved_args = slots.get("approved_args")
                if approved_tool in SIDE_EFFECT_TOOLS and isinstance(approved_args, dict):
                    action_id = self._confirm_capability(
                        thread_id=thread_id,
                        tool_name=approved_tool,
                        args=approved_args,
                        pending_action_id=slots.get("action_id"),
                    )
                    result.bind_server_approval(approved_tool, approved_args, action_id)
            elif name == "schedule_commit":
                proposal_plan = slots.get("proposal_plan")
                if isinstance(proposal_plan, list) and proposal_plan:
                    commit_args = {"plan": proposal_plan}
                    action_id = self._confirm_schedule_capability(
                        thread_id=thread_id,
                        args=commit_args,
                    )
                    result.bind_server_approval(
                        "commit_publishing_schedule",
                        commit_args,
                        action_id,
                    )
        return result

    def _confirm_capability(
        self,
        *,
        thread_id: str | None,
        tool_name: str,
        args: dict[str, Any],
        pending_action_id: Any = None,
    ) -> str | None:
        """Confirm the durable proposal matching this exact call.

        Returns ``None`` when no unexpired matching proposal exists, which leaves
        the write unauthorized. The stored hash must match the arguments being
        confirmed, so a legacy transcript proposal with no durable row cannot be
        confirmed into a capability.
        """
        if self.store is None or not thread_id:
            return None
        expected_hash = args_hash(args)
        candidate = None
        if isinstance(pending_action_id, str) and pending_action_id:
            candidate = self.store.get_proposed_action(pending_action_id)
            if not candidate or candidate.get("thread_id") != thread_id:
                candidate = None
        if candidate is None:
            candidate = self.store.latest_pending_proposed_action(
                thread_id, tool_name=tool_name
            )
        if not candidate:
            return None
        if candidate.get("tool_name") != tool_name or candidate.get("args_hash") != expected_hash:
            return None
        confirmed = self.store.confirm_proposed_action(candidate["id"])
        if not confirmed:
            return None
        log_event(
            logger,
            "action_capability_confirmed",
            thread_id=thread_id,
            action_id=confirmed["id"],
            tool_name=tool_name,
            args_hash=expected_hash,
        )
        return confirmed["id"]

    def _confirm_schedule_capability(
        self,
        *,
        thread_id: str | None,
        args: dict[str, Any],
    ) -> str | None:
        """Issue a capability for a schedule commit bound to the proposed plan.

        Unlike other writes, the schedule proposal is a completed read-only tool
        result rather than a `proposed` write event, so no durable row exists yet.
        The plan itself is server-persisted evidence from the preceding turn, so
        the row is created and confirmed together here, still hash-bound to the
        exact plan and consumable only once.
        """
        if self.store is None or not thread_id:
            return None
        existing = self.store.latest_pending_proposed_action(
            thread_id, tool_name="commit_publishing_schedule"
        )
        expected_hash = args_hash(args)
        if existing and existing.get("args_hash") == expected_hash:
            action_id = existing["id"]
        else:
            created = self.store.create_proposed_action(
                thread_id=thread_id,
                tool_name="commit_publishing_schedule",
                args=args,
                impact_summary=(
                    f"Commit {len(args.get('plan') or [])} calendar entries from the "
                    "proposed publishing schedule"
                ),
                ttl_seconds=config.ACTION_CAPABILITY_TTL_SECONDS,
            )
            action_id = created["id"]
        confirmed = self.store.confirm_proposed_action(action_id)
        if not confirmed:
            return None
        log_event(
            logger,
            "action_capability_confirmed",
            thread_id=thread_id,
            action_id=confirmed["id"],
            tool_name="commit_publishing_schedule",
            args_hash=expected_hash,
        )
        return confirmed["id"]

    def _matches_action_confirm(
        self,
        message: str,
        history: list[dict[str, Any]],
        *,
        thread_id: str | None = None,
    ) -> bool:
        if not _CONFIRM_RE.search(message.strip()):
            return False
        return bool(self._extract_last_proposed_action(history, thread_id=thread_id))

    def _extract_last_proposed_action(
        self,
        history: list[dict[str, Any]],
        *,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        """Resolve which write the user is confirming.

        The durable ``proposed_actions`` row is authoritative when present: it
        carries an explicit action id, so a turn that proposed several writes no
        longer depends on transcript ordering to decide what a bare confirmation
        meant. Transcript scraping remains the display/naming fallback for
        threads whose proposals predate this table, but it yields no action id
        and therefore no capability.
        """
        durable = self._latest_durable_proposal(thread_id)
        if durable:
            return {
                "approved_tool_name": durable["tool_name"],
                "approved_args": durable["args"],
                "action_id": durable["id"],
            }
        last_assistant = self._last_assistant_message(history)
        if not last_assistant:
            return {}
        for event in reversed(last_assistant.get("tool_events") or []):
            name = event.get("name")
            args = event.get("args")
            if event.get("status") == "proposed" and name in SIDE_EFFECT_TOOLS and isinstance(args, dict):
                return {"approved_tool_name": name, "approved_args": args}
        return {}

    def _latest_durable_proposal(self, thread_id: str | None) -> dict[str, Any] | None:
        if self.store is None or not thread_id:
            return None
        try:
            return self.store.latest_pending_proposed_action(thread_id)
        except Exception:
            # A capability lookup failure must never widen authorization; falling
            # through leaves the confirmation without an action id.
            return None

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
        # Text such as "now" is intent, not an authorization capability. Every
        # model-generated write must first be persisted as an exact proposal and
        # confirmed in the following user turn.
        return name in {"content_create", "content_refine", "memory_update"}

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
