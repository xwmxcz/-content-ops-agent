"""Tool definitions exposed to the chat agent.

Extracted from ``ChatAgentService._build_tools``: the closures depend on four
things only (store, file_memory, llm, and keyword splitting), so they take those
as explicit arguments rather than closing over a service instance. That makes
the tool surface readable in one place, and makes each tool testable without
constructing a ChatAgentService.

Tool names here are the authorization vocabulary: `src/api/services/tool_policy`
maps a name to whether it needs user confirmation, and `validate_tool_policy_registry`
asserts at import time that every name defined here is classified there. Adding a
tool without classifying it is a startup failure, not a silent gap.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from langchain_core.tools import StructuredTool

from src.api.schemas.content import GenerateRequest, RefineRequest, SeoRequest, TitleRequest
from src.api.services import content_service
from src.api.services.publish_service import create_publish_service
from src.api.services.tool_policy import validate_tool_policy_registry
from src.llm.litellm_client import LiteLLMClient
from src.models import ContentStyle, ContentType
from src.storage import ContentStore
from src.storage.file_memory import FileMemory, MemoryAmbiguous, MemoryLimitExceeded, MemoryNotFound
from src.utils.idempotency import (
    SCOPE_CALENDAR_COMMIT,
    SCOPE_MEMORY_MUTATION,
    current_request_key,
    entry_key,
    idempotent_write,
)

logger = logging.getLogger(__name__)


def _split_keywords(keywords: str | None) -> list[str] | None:
    """Split a comma-separated keyword string from a tool call into a list."""
    if not keywords:
        return None
    return [keyword.strip() for keyword in keywords.split(",") if keyword.strip()]


def build_chat_tools(
    *,
    store: ContentStore,
    file_memory: FileMemory | None,
    llm: LiteLLMClient,
    provider: str,
    model: str,
    temperature: float,
    max_tokens: int,
    allowed_tools: list[str] | None = None,
) -> list[StructuredTool]:
    """Build the chat agent's tool set, filtered to ``allowed_tools`` when given."""

    async def create_content(
        topic: str,
        content_type: str,
        style: str = "casual",
        keywords: str | None = None,
        length: str = "medium",
    ) -> str:
        """Create and save a new content draft."""
        # `length` comes from a model-authored tool call, so it is untrusted
        # free text; GenerateRequest only accepts the three known sizes.
        if length not in ("short", "medium", "long"):
            length = "medium"
        request = GenerateRequest(
            topic=topic,
            content_type=ContentType(content_type),
            style=ContentStyle(style),
            keywords=_split_keywords(keywords),
            length=length,  # type: ignore[arg-type]
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content_id, generated, used_provider, used_model = await content_service.generate_content(
            request,
            llm,
            store,
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
            llm,
            store,
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
        return await content_service.generate_titles(request, llm, store)

    async def optimize_seo(content_id: int) -> str:
        """Analyze a saved content item and return SEO recommendations."""
        request = SeoRequest(content_id=content_id, provider=provider, model=model)
        return await content_service.analyze_seo(request, llm, store)

    def view_content(content_id: int) -> str:
        """Read a saved content item by id."""
        content = store.get_content(content_id)
        if not content:
            return f"Content {content_id} was not found."
        return json.dumps(content, ensure_ascii=False)

    def list_recent_contents(limit: int = 10) -> str:
        """List recent saved content items."""
        return json.dumps(store.list_contents(limit=limit), ensure_ascii=False)

    def add_to_calendar(content_id: int, publish_date: str, platform: str) -> str:
        """Schedule a saved content item on the publishing calendar.

        publish_date MUST be an absolute YYYY-MM-DD string ≥ today's date.
        Convert relative phrases like "tomorrow", "next Monday", or "下周一" to YYYY-MM-DD
        using the date anchors in the system prompt before calling.
        Never use dates from your training data or memory — always compute from today.
        """
        content = store.get_content(content_id)
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
        event_id = idempotent_write(
            store,
            scope=SCOPE_CALENDAR_COMMIT,
            key=current_request_key(),
            args={
                "content_id": content_id,
                "platform": platform,
                "scheduled_date": publish_date,
            },
            write=lambda: store.save_calendar_event(content_id, platform, scheduled_date),
        )
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
        return json.dumps(store.get_calendar_events(start_date, end_date), ensure_ascii=False)

    def get_content_stats() -> str:
        """Return content library statistics."""
        return json.dumps(store.get_content_stats(), ensure_ascii=False)

    async def check_xiaohongshu_login() -> str:
        """Check whether the Xiaohongshu MCP integration is currently logged in."""
        status_payload = await create_publish_service(store).get_login_status()
        return json.dumps(status_payload, ensure_ascii=False)

    def search_history(query: str, limit: int = 10) -> str:
        """Search saved content by keyword across title, body, and keywords.

        Use this to recall what the team has written before, e.g. "previous hiking posts"
        or to discover the right content_id when the user refers to past work by topic.
        """
        return json.dumps(store.search_contents(query, limit), ensure_ascii=False)

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
        return json.dumps(store.aggregate_performance(days), ensure_ascii=False)

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
        return json.dumps(store.list_optimization_candidates(criteria, limit), ensure_ascii=False)

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
        perf = store.aggregate_performance(days=30)
        recent = store.list_contents(limit=15)
        by_type = perf.get("by_type") or []
        winners = [t for t in by_type if t.get("with_metrics") and t.get("avg_engagement_rate", 0) >= 0.04]
        underrepresented = sorted(by_type, key=lambda t: t.get("count", 0))[:2]
        brief = {
            "requested_count": count,
            "user_hint": hint,
            "winning_content_types": [
                {
                    "content_type": t["content_type"],
                    "avg_engagement_rate": t["avg_engagement_rate"],
                    "avg_views": t["avg_views"],
                    "sample_size": t["with_metrics"],
                }
                for t in winners[:3]
            ],
            "underrepresented_content_types": [
                {"content_type": t["content_type"], "count": t["count"]} for t in underrepresented
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
            row = store.get_content(int(cid))
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

        existing = store.get_calendar_conflicts(start, end)
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
                plan.append(
                    {
                        "content_id": content["id"],
                        "title": content.get("title"),
                        "platform": platform,
                        "scheduled_date": None,
                        "warning": "no available date in range under given cadence",
                    }
                )
            else:
                plan.append(
                    {
                        "content_id": content["id"],
                        "title": content.get("title"),
                        "platform": platform,
                        "scheduled_date": slot.isoformat(),
                    }
                )

        return json.dumps(
            {
                "plan": plan,
                "cadence": cadence,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "committed": False,
                "reminder": "This is a PROPOSAL. Show it to the user as a markdown table and wait for confirmation before calling commit_publishing_schedule.",
            },
            ensure_ascii=False,
        )

    def commit_publishing_schedule(plan: list[dict[str, Any]]) -> str:
        """Persist a previously-proposed publishing schedule to the calendar.

        Each plan item must have content_id, platform, scheduled_date (YYYY-MM-DD).
        Items with null scheduled_date are skipped. Returns a summary of what was saved.
        """
        saved: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        batch_key = current_request_key()
        for index, item in enumerate(plan or []):
            if not item.get("scheduled_date"):
                skipped.append({"content_id": item.get("content_id"), "reason": "no scheduled_date"})
                continue
            try:
                when = datetime.strptime(item["scheduled_date"], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                skipped.append({"content_id": item.get("content_id"), "reason": "bad date"})
                continue
            content_id = int(item["content_id"])
            if store.get_content(content_id) is None:
                skipped.append({"content_id": content_id, "reason": "content not found"})
                continue
            platform = item.get("platform") or "unknown"
            # Per-entry keys, not one key for the batch: a plan may legitimately
            # repeat the same (content_id, platform, date), and a single key would
            # write fewer rows than the user approved. The index makes each
            # approved entry independently replayable, so a retry after a partial
            # commit fills only the entries that did not land.
            event_id = idempotent_write(
                store,
                scope=SCOPE_CALENDAR_COMMIT,
                key=entry_key(batch_key, index) if batch_key else None,
                args={
                    "content_id": content_id,
                    "platform": platform,
                    "scheduled_date": item["scheduled_date"],
                },
                write=lambda cid=content_id, plat=platform, day=when: store.save_calendar_event(cid, plat, day),
            )
            saved.append(
                {
                    "event_id": event_id,
                    "content_id": content_id,
                    "platform": item.get("platform"),
                    "scheduled_date": item["scheduled_date"],
                }
            )
        return json.dumps({"saved": saved, "skipped": skipped, "committed": True}, ensure_ascii=False)

    def _memory_mutation(operation: str, args: dict, apply) -> dict:
        """Apply one memory mutation at most once per consumed capability.

        ``FileMemory`` is a filesystem store with no transaction, so the
        durable ledger row is the only authority available: it is claimed
        before the file write and completed after. A retry that reuses the
        same capability id therefore replays the recorded stats instead of
        appending a second copy of the entry.

        Guarantee boundary: a hard crash (SIGKILL) between the claim and the
        file write leaves the row ``in_progress``, which fails closed — the
        mutation is lost and the key is not reusable. This is at-most-once,
        matching capability consumption in P1-01; it is not exactly-once,
        which a filesystem store cannot provide without a write-ahead log.
        """

        # All callers guard on file_memory, but the guard is lost across the
        # closure boundary; re-assert it so a disabled memory fails closed
        # with a clean reason instead of an AttributeError.
        # Bind to a local before the closure: mypy cannot narrow
        # `file_memory` inside `write()`.
        memory = file_memory
        if not memory:
            return {"saved": False, "reason": "memory disabled"}

        def write() -> dict:
            apply()
            stats = memory.stats(args["target"])
            return {
                "target": args["target"],
                "char_count": stats["char_count"],
                "char_limit": stats["char_limit"],
            }

        return idempotent_write(
            store,
            scope=SCOPE_MEMORY_MUTATION,
            key=current_request_key(),
            args={"operation": operation, **args},
            write=write,
        )

    def memory_add(target: str, text: str) -> str:
        """Append a durable note to the file-based memory.

        target: 'agent' (writes to MEMORY.md — project conventions, tool
                quirks, brand vocabulary) or 'user' (writes to USER.md —
                name, language, style preferences).
        text:   the entry body, may be multiline.
        The entry takes effect in the NEXT session, not this one.
        """
        if not file_memory:
            return json.dumps({"saved": False, "reason": "memory disabled"}, ensure_ascii=False)
        try:
            result = _memory_mutation(
                "add",
                {"target": target, "text": text},
                lambda: file_memory.add(target, text),
            )
        except (MemoryLimitExceeded, ValueError) as exc:
            return json.dumps({"saved": False, "reason": str(exc)}, ensure_ascii=False)
        return json.dumps({"saved": True, **result}, ensure_ascii=False)

    def memory_replace(target: str, old_text: str, new_text: str) -> str:
        """Replace one occurrence of old_text with new_text in the named file.

        target:   'agent' or 'user'.
        old_text: substring to find; MUST match exactly one place.
        new_text: replacement body.
        """
        if not file_memory:
            return json.dumps({"replaced": False, "reason": "memory disabled"}, ensure_ascii=False)
        try:
            result = _memory_mutation(
                "replace",
                {"target": target, "old_text": old_text, "new_text": new_text},
                lambda: file_memory.replace(target, old_text, new_text),
            )
        except (MemoryNotFound, MemoryAmbiguous, MemoryLimitExceeded, ValueError) as exc:
            return json.dumps({"replaced": False, "reason": str(exc)}, ensure_ascii=False)
        return json.dumps({"replaced": True, **result}, ensure_ascii=False)

    def memory_remove(target: str, old_text: str) -> str:
        """Delete one occurrence of old_text from the named file.

        target:   'agent' or 'user'.
        old_text: substring to find; MUST match exactly one place.
        """
        if not file_memory:
            return json.dumps({"removed": False, "reason": "memory disabled"}, ensure_ascii=False)
        try:
            result = _memory_mutation(
                "remove",
                {"target": target, "old_text": old_text},
                lambda: file_memory.remove(target, old_text),
            )
        except (MemoryNotFound, MemoryAmbiguous, ValueError) as exc:
            return json.dumps({"removed": False, "reason": str(exc)}, ensure_ascii=False)
        return json.dumps({"removed": True, **result}, ensure_ascii=False)

    def session_search(query: str, limit: int = 5, thread_id: str | None = None) -> str:
        """Substring search over all stored assistant↔user messages.

        Uses ILIKE, so Chinese substrings match without a CJK analyzer.
        Use to recall what was said in this or past conversation threads.
        """
        results = store.search_agent_messages(query, limit=limit, thread_id=thread_id)
        return json.dumps({"messages": results, "count": len(results)}, ensure_ascii=False)

    tools = [
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
    validate_tool_policy_registry([tool.name for tool in tools])
    if allowed_tools is None:
        return tools
    allowed = set(allowed_tools)
    return [tool for tool in tools if tool.name in allowed]
