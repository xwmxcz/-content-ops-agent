"""内容存储 - SQLAlchemy ORM + CRUD"""
import json
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from uuid import uuid4

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, create_engine, func, inspect, or_, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker, Session


import logging

from src.utils import metrics
from src.utils.structured_logging import log_idempotency_event, log_capability_event

logger = logging.getLogger(__name__)

Base = declarative_base()


class Content(Base):
    """内容记录表"""
    __tablename__ = "contents"

    id = Column(Integer, primary_key=True)
    title = Column(Text, nullable=True)
    content = Column(Text, nullable=False)
    content_type = Column(String(50), nullable=False)
    style = Column(String(50), nullable=False)
    keywords = Column(Text, nullable=True)
    tags = Column(Text, nullable=True)
    status = Column(String(20), default="draft")
    version = Column(Integer, default=1)
    parent_id = Column(Integer, nullable=True)
    llm_provider = Column(String(50), nullable=True)
    model_name = Column(String(100), nullable=True)
    token_usage = Column(Integer, nullable=True)
    cost_estimate = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


Index("ix_contents_created_at", Content.created_at)
Index("ix_contents_status", Content.status)
Index("ix_contents_content_type", Content.content_type)


class CalendarEvent(Base):
    """内容日历表"""
    __tablename__ = "calendar_events"

    id = Column(Integer, primary_key=True)
    content_id = Column(Integer, ForeignKey("contents.id"), nullable=False)
    platform = Column(String(50), nullable=False)
    scheduled_date = Column(Date, nullable=False)
    status = Column(String(20), default="planned")
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)


Index("ix_calendar_events_scheduled_date", CalendarEvent.scheduled_date)


class ContentMetrics(Base):
    """内容效果表"""
    __tablename__ = "content_metrics"

    id = Column(Integer, primary_key=True)
    content_id = Column(Integer, ForeignKey("contents.id"), nullable=False)
    platform = Column(String(50), nullable=True)
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    recorded_at = Column(DateTime, default=datetime.now)


class MediaAsset(Base):
    """Persisted uploaded or generated media tied to content."""

    __tablename__ = "media_assets"

    id = Column(Integer, primary_key=True)
    content_id = Column(Integer, ForeignKey("contents.id"), nullable=False)
    media_type = Column(String(20), nullable=False)
    source_type = Column(String(20), nullable=False, default="upload")
    file_name = Column(Text, nullable=False)
    file_path = Column(Text, nullable=False)
    mime_type = Column(String(120), nullable=True)
    sort_order = Column(Integer, default=0)
    provider = Column(String(80), nullable=True)
    generation_params = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)


Index("ix_media_assets_content_created", MediaAsset.content_id, MediaAsset.created_at)


class PlatformPublication(Base):
    """Persisted publication requests sent to an external platform."""

    __tablename__ = "platform_publications"

    id = Column(Integer, primary_key=True)
    content_id = Column(Integer, ForeignKey("contents.id"), nullable=False)
    platform = Column(String(50), nullable=False)
    publish_type = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False, default="draft")
    title = Column(Text, nullable=True)
    body = Column(Text, nullable=False)
    scheduled_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)
    external_post_id = Column(String(120), nullable=True)
    request_payload = Column(Text, nullable=True)
    response_payload = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


Index("ix_platform_publications_content_status", PlatformPublication.content_id, PlatformPublication.status)
Index("ix_platform_publications_platform_created", PlatformPublication.platform, PlatformPublication.created_at)


class AgentThread(Base):
    """Persisted Agent chat thread."""

    __tablename__ = "agent_threads"

    id = Column(String(80), primary_key=True)
    title = Column(Text, nullable=True)
    last_provider = Column(String(50), nullable=True)
    last_model = Column(String(200), nullable=True)
    pinned = Column(Boolean, default=False, nullable=False)
    archived = Column(Boolean, default=False, nullable=False)
    title_pinned = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


Index("ix_agent_threads_updated_at", AgentThread.updated_at)
Index("ix_agent_threads_pinned_updated", AgentThread.pinned, AgentThread.updated_at)
Index("ix_agent_threads_archived", AgentThread.archived)


class AgentMessage(Base):
    """Persisted Agent chat message."""

    __tablename__ = "agent_messages"

    id = Column(Integer, primary_key=True)
    thread_id = Column(String(80), ForeignKey("agent_threads.id"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    provider = Column(String(50), nullable=True)
    model = Column(String(200), nullable=True)
    intent = Column(Text, nullable=True)
    tool_events = Column(Text, nullable=True)
    plan = Column(Text, nullable=True)
    status = Column(String(20), default="completed")
    created_at = Column(DateTime, default=datetime.now)


Index("ix_agent_messages_thread_created", AgentMessage.thread_id, AgentMessage.created_at)


class Job(Base):
    """Persisted background job state."""

    __tablename__ = "jobs"

    id = Column(String(80), primary_key=True)
    job_type = Column(String(80), nullable=False)
    status = Column(String(20), nullable=False, default="queued")
    payload = Column(Text, nullable=False)
    result = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    provider = Column(String(50), nullable=True)
    model = Column(String(200), nullable=True)
    progress = Column(Integer, default=0)
    attempts = Column(Integer, default=0)
    max_retries = Column(Integer, default=5, nullable=False)
    next_retry_at = Column(DateTime, nullable=True)
    error_type = Column(String(20), nullable=True)
    archived_at = Column(DateTime, nullable=True, index=True)
    token_usage = Column(Integer, default=0)
    cost_estimate = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


Index("ix_jobs_status_created", Job.status, Job.created_at)
Index("ix_jobs_provider_status", Job.provider, Job.status)


class AgentRun(Base):
    """Dynamic-pipeline run record."""

    __tablename__ = "agent_runs"

    id = Column(String(80), primary_key=True)
    thread_id = Column(String(80), nullable=True)
    topic = Column(Text, nullable=False)
    content_type = Column(String(50), nullable=False)
    style = Column(String(50), nullable=False)
    provider = Column(String(50), nullable=True)
    model = Column(String(200), nullable=True)
    plan_json = Column(Text, nullable=True)
    revision_count = Column(Integer, default=0)
    total_prompt_tokens = Column(Integer, default=0)
    total_completion_tokens = Column(Integer, default=0)
    total_cost = Column(Float, default=0.0)
    saved_content_id = Column(Integer, nullable=True)
    status = Column(String(20), default="running")
    error = Column(Text, nullable=True)
    next_event_seq = Column(Integer, nullable=False, default=1, server_default=text("1"))
    created_at = Column(DateTime, default=datetime.now)
    completed_at = Column(DateTime, nullable=True)


Index("ix_agent_runs_thread_created", AgentRun.thread_id, AgentRun.created_at)


class AgentRunEvent(Base):
    """Append-only event log for a pipeline run; SSE bridge reads this table."""

    __tablename__ = "agent_run_events"
    __table_args__ = (
        UniqueConstraint("run_id", "seq", name="uq_agent_run_events_run_seq"),
    )

    id = Column(Integer, primary_key=True)
    run_id = Column(String(80), ForeignKey("agent_runs.id"), nullable=False)
    seq = Column(Integer, nullable=False)
    event_type = Column(String(40), nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.now)


Index("ix_agent_run_events_run_seq", AgentRunEvent.run_id, AgentRunEvent.seq)


class ProposedAction(Base):
    """Durable one-time capability for a model-proposed write.

    A write tool is never authorized by model text. The executor persists the
    exact proposed call here, a later standalone user confirmation moves the row
    to ``confirmed``, and the executor atomically moves it to ``consumed`` before
    invoking the tool. ``args_hash`` makes the confirmed arguments tamper-evident
    across requests, and the status transition is the once-only guarantee.
    """

    __tablename__ = "proposed_actions"

    id = Column(String(80), primary_key=True)
    thread_id = Column(String(80), ForeignKey("agent_threads.id"), nullable=False)
    requester = Column(String(120), nullable=True)
    tool_name = Column(String(80), nullable=False)
    args_json = Column(Text, nullable=False)
    args_hash = Column(String(64), nullable=False)
    impact_summary = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="proposed")
    proposing_message_id = Column(Integer, nullable=True)
    consuming_message_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    confirmed_at = Column(DateTime, nullable=True)
    consumed_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)


Index("ix_proposed_actions_thread_created", ProposedAction.thread_id, ProposedAction.created_at)
Index("ix_proposed_actions_status_expires", ProposedAction.status, ProposedAction.expires_at)


PROPOSED_ACTION_STATUSES = ("proposed", "confirmed", "consumed", "cancelled", "expired")


class IdempotencyRecord(Base):
    """Durable ledger making a keyed write replayable instead of repeatable.

    One logical request can span several statements and tables: a refine is an
    insert plus an update, a schedule commit is N calendar rows. Uniqueness
    therefore lives here rather than on the business columns of those tables. A
    unique constraint on, say, ``calendar_events(content_id, platform,
    scheduled_date)`` would reject legitimate repeats (an intentional same-day
    repost, a retry of a failed publish job) and turn recoverable errors into
    ``IntegrityError``.

    ``scope`` is part of the unique key so the same key value used for a content
    create and a calendar commit does not collide. ``result_json`` is what lets a
    retry return the *same* result rather than doing the work again.
    """

    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("scope", "idempotency_key", name="uq_idempotency_records_scope_key"),
    )

    id = Column(Integer, primary_key=True)
    scope = Column(String(60), nullable=False)
    idempotency_key = Column(String(160), nullable=False)
    args_hash = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, default="in_progress")
    result_json = Column(Text, nullable=True)
    external_request_id = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    completed_at = Column(DateTime, nullable=True)


Index("ix_idempotency_records_scope_created", IdempotencyRecord.scope, IdempotencyRecord.created_at)


IDEMPOTENCY_RECORD_STATUSES = ("in_progress", "completed", "failed")


class ContentStore:
    """内容存储管理类"""

    def __init__(
        self,
        database_url: str | None = None,
        initialize_schema: bool = True,
    ):
        # `initialize_schema=False` skips create_all + legacy-column ALTERs. Job
        # runners and pipeline workers spin up a fresh ContentStore per task
        # (fork-safe), so re-running DDL every time was pure overhead and, with
        # multiple workers, a concurrent-DDL race. The schema is built once per
        # process at startup instead (see main.py lifespan and worker.py).
        # Defaults to True so tests and first-run setups still work.
        from src.utils import config

        if database_url is None:
            database_url = config.DATABASE_URL

        url = make_url(database_url)
        if url.get_backend_name() == "sqlite":
            raise ValueError(
                "SQLite is not supported. Set DATABASE_URL to a PostgreSQL DSN, "
                "e.g. postgresql+psycopg://user:password@host:5432/dbname"
            )

        self.database_url = database_url
        self.engine = create_engine(
            database_url,
            echo=False,
            pool_size=config.DB_POOL_SIZE,
            max_overflow=config.DB_MAX_OVERFLOW,
            pool_timeout=config.DB_POOL_TIMEOUT_SECONDS,
            pool_pre_ping=True,
        )
        if initialize_schema:
            Base.metadata.create_all(self.engine)
            self._ensure_legacy_columns()
        self.SessionLocal = sessionmaker(bind=self.engine)

    def _ensure_legacy_columns(self) -> None:
        # Additive migrations for databases created before these columns existed.
        # On a fresh DB `create_all` already builds every column, so the inspect
        # check inside _safe_add_columns short-circuits and nothing runs here.
        self._safe_add_columns("agent_messages", [
            ("intent", "ALTER TABLE agent_messages ADD COLUMN intent TEXT"),
            ("plan", "ALTER TABLE agent_messages ADD COLUMN plan TEXT"),
        ])
        self._safe_add_columns("agent_threads", [
            ("pinned", "ALTER TABLE agent_threads ADD COLUMN pinned BOOLEAN NOT NULL DEFAULT false"),
            ("archived", "ALTER TABLE agent_threads ADD COLUMN archived BOOLEAN NOT NULL DEFAULT false"),
            ("title_pinned", "ALTER TABLE agent_threads ADD COLUMN title_pinned BOOLEAN NOT NULL DEFAULT false"),
        ])
        self._safe_add_columns("jobs", [
            ("token_usage", "ALTER TABLE jobs ADD COLUMN token_usage INTEGER DEFAULT 0"),
            ("cost_estimate", "ALTER TABLE jobs ADD COLUMN cost_estimate FLOAT DEFAULT 0"),
        ])

    def _safe_add_columns(self, table: str, columns: list[tuple[str, str]]) -> None:
        existing = {col["name"] for col in inspect(self.engine).get_columns(table)}
        for name, ddl in columns:
            if name in existing:
                continue
            try:
                with self.engine.begin() as connection:
                    connection.execute(text(ddl))
            except SQLAlchemyError as exc:
                # Multiple processes (e.g. several gunicorn workers all running
                # the startup schema build at once) can race here: each inspects
                # the pre-migration table and each issues the ALTER. The losers
                # get a "duplicate column" / "already exists" error, which is safe
                # to swallow since the column now exists. Anything else is a real
                # failure and re-raises.
                message = str(exc).lower()
                if "duplicate column" in message or "already exists" in message:
                    continue
                raise

    def _get_session(self) -> Session:
        return self.SessionLocal()

    def save_content(
        self,
        generated_content,
        llm_provider=None,
        model_name=None,
        parent_id=None,
        style: str = "casual",
        keywords: list[str] | None = None,
        token_usage: int | None = None,
        cost_estimate: float | None = None,
    ) -> int:
        session = self._get_session()
        try:
            if keywords is None and generated_content.metadata:
                keywords = generated_content.metadata.get("keywords", [])
            content = Content(
                title=generated_content.title,
                content=generated_content.content,
                content_type=generated_content.content_type.value if generated_content.content_type else "unknown",
                style=style,
                keywords=json.dumps(keywords or [], ensure_ascii=False),
                tags=json.dumps(generated_content.tags or []),
                status="draft",
                parent_id=parent_id,
                llm_provider=llm_provider,
                model_name=model_name,
                token_usage=token_usage,
                cost_estimate=cost_estimate,
            )
            session.add(content)
            session.commit()
            return content.id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_content(self, content_id: int) -> Optional[Dict[str, Any]]:
        session = self._get_session()
        try:
            content = session.query(Content).filter(Content.id == content_id).first()
            if not content:
                return None
            return self._content_to_dict(content)
        finally:
            session.close()

    def update_content(self, content_id: int, **fields) -> bool:
        session = self._get_session()
        try:
            content = session.query(Content).filter(Content.id == content_id).first()
            if not content:
                return False
            for key, value in fields.items():
                if hasattr(content, key):
                    setattr(content, key, value)
            content.updated_at = datetime.now()
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_contents(self, status=None, content_type=None, limit=50, offset=0) -> List[Dict[str, Any]]:
        session = self._get_session()
        try:
            query = session.query(Content)
            if status:
                query = query.filter(Content.status == status)
            if content_type:
                query = query.filter(Content.content_type == content_type)
            query = query.order_by(Content.created_at.desc()).limit(limit).offset(offset)
            contents = query.all()
            return [
                {
                    "id": c.id,
                    "title": c.title,
                    "content": c.content[:100] + "..." if len(c.content) > 100 else c.content,
                    "content_type": c.content_type,
                    "style": c.style,
                    "status": c.status,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
                for c in contents
            ]
        finally:
            session.close()

    def search_contents(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        if not query or not query.strip():
            return []
        pattern = f"%{query.strip()}%"
        session = self._get_session()
        try:
            rows = (
                session.query(Content)
                .filter(
                    or_(
                        Content.title.ilike(pattern),
                        Content.content.ilike(pattern),
                        Content.keywords.ilike(pattern),
                    )
                )
                .order_by(Content.created_at.desc())
                .limit(limit)
                .all()
            )
            return [self._content_to_dict(c) for c in rows]
        finally:
            session.close()

    def save_calendar_event(self, content_id: int, platform: str, scheduled_date: date) -> int:
        session = self._get_session()
        try:
            event = CalendarEvent(
                content_id=content_id,
                platform=platform,
                scheduled_date=scheduled_date,
                status="planned"
            )
            session.add(event)
            session.commit()
            return event.id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_calendar_events(self, start_date=None, end_date=None) -> List[Dict[str, Any]]:
        session = self._get_session()
        try:
            query = session.query(CalendarEvent, Content).join(
                Content, CalendarEvent.content_id == Content.id
            )
            if start_date:
                query = query.filter(CalendarEvent.scheduled_date >= start_date)
            if end_date:
                query = query.filter(CalendarEvent.scheduled_date <= end_date)
            query = query.order_by(CalendarEvent.scheduled_date)
            results = query.all()
            return [
                {
                    "event_id": event.id,
                    "content_id": event.content_id,
                    "platform": event.platform,
                    "scheduled_date": event.scheduled_date.isoformat(),
                    "status": event.status,
                    "content_title": content.title,
                    "content_type": content.content_type,
                }
                for event, content in results
            ]
        finally:
            session.close()

    def get_content_stats(self) -> Dict[str, Any]:
        session = self._get_session()
        try:
            total = session.query(Content).count()
            by_type = {
                content_type: count
                for content_type, count in (
                    session.query(Content.content_type, func.count(Content.id))
                    .group_by(Content.content_type)
                    .all()
                )
                if content_type
            }
            by_status = {
                status: count
                for status, count in (
                    session.query(Content.status, func.count(Content.id))
                    .group_by(Content.status)
                    .all()
                )
                if status
            }
            return {"total_contents": total, "by_type": by_type, "by_status": by_status}
        finally:
            session.close()

    def aggregate_performance(self, days: int = 30) -> Dict[str, Any]:
        """Group contents from the last `days` days by content_type + style and aggregate
        engagement metrics. Used by the chat Agent's analyze_content_performance tool.

        Returns a compact structure suitable for feeding into an LLM context (typically
        well under 2KB):

            {
              "window_days": 30,
              "total_contents": 47,
              "total_with_metrics": 23,
              "by_type": [{"content_type": "xiaohongshu", "count": 18, "avg_views": 4200,
                           "avg_likes": 210, "avg_engagement_rate": 0.052}, ...],
              "by_style": [...],
              "top_performers": [{"id": 12, "title": "...", "content_type": "xiaohongshu",
                                  "views": 18400, "likes": 1240, "engagement_rate": 0.067}, ...]
            }
        """
        cutoff = datetime.now() - timedelta(days=max(1, days))
        session = self._get_session()
        try:
            contents = session.query(Content).filter(Content.created_at >= cutoff).all()
            if not contents:
                return {
                    "window_days": days, "total_contents": 0, "total_with_metrics": 0,
                    "by_type": [], "by_style": [], "top_performers": [],
                }
            content_ids = [c.id for c in contents]
            metrics_rows = (
                session.query(ContentMetrics)
                .filter(ContentMetrics.content_id.in_(content_ids))
                .all()
            )
            metrics_by_content: dict[int, ContentMetrics] = {}
            for m in metrics_rows:
                # If multiple metric rows exist per content, keep the one with highest views.
                existing = metrics_by_content.get(m.content_id)
                if existing is None or (m.views or 0) > (existing.views or 0):
                    metrics_by_content[m.content_id] = m

            def _engagement_rate(m: ContentMetrics | None) -> float:
                if m is None or not m.views:
                    return 0.0
                return round(((m.likes or 0) + (m.comments or 0) + (m.shares or 0)) / m.views, 4)

            type_buckets: dict[str, dict[str, Any]] = {}
            style_buckets: dict[str, dict[str, Any]] = {}
            for content in contents:
                m = metrics_by_content.get(content.id)
                for bucket_key, store_dict in (
                    (content.content_type or "unknown", type_buckets),
                    (content.style or "unknown", style_buckets),
                ):
                    bucket = store_dict.setdefault(
                        bucket_key,
                        {"count": 0, "with_metrics": 0, "views": 0, "likes": 0,
                         "comments": 0, "shares": 0, "engagement_rates": []},
                    )
                    bucket["count"] += 1
                    if m is not None:
                        bucket["with_metrics"] += 1
                        bucket["views"] += m.views or 0
                        bucket["likes"] += m.likes or 0
                        bucket["comments"] += m.comments or 0
                        bucket["shares"] += m.shares or 0
                        bucket["engagement_rates"].append(_engagement_rate(m))

            def _summarize(buckets: dict[str, dict[str, Any]], key_name: str) -> list[dict[str, Any]]:
                out = []
                for k, b in buckets.items():
                    n = max(1, b["with_metrics"])
                    out.append({
                        key_name: k,
                        "count": b["count"],
                        "with_metrics": b["with_metrics"],
                        "avg_views": round(b["views"] / n) if b["with_metrics"] else 0,
                        "avg_likes": round(b["likes"] / n) if b["with_metrics"] else 0,
                        "avg_comments": round(b["comments"] / n) if b["with_metrics"] else 0,
                        "avg_engagement_rate": (
                            round(sum(b["engagement_rates"]) / len(b["engagement_rates"]), 4)
                            if b["engagement_rates"] else 0.0
                        ),
                    })
                out.sort(key=lambda r: (r["with_metrics"] > 0, r["avg_engagement_rate"]), reverse=True)
                return out

            scored: list[tuple[float, Content, ContentMetrics]] = []
            for c in contents:
                m = metrics_by_content.get(c.id)
                if m is None:
                    continue
                scored.append((_engagement_rate(m), c, m))
            scored.sort(key=lambda x: (x[0], x[2].views or 0), reverse=True)
            top_performers = [
                {
                    "id": c.id,
                    "title": c.title,
                    "content_type": c.content_type,
                    "style": c.style,
                    "views": m.views or 0,
                    "likes": m.likes or 0,
                    "comments": m.comments or 0,
                    "engagement_rate": rate,
                }
                for rate, c, m in scored[:5]
            ]

            return {
                "window_days": days,
                "total_contents": len(contents),
                "total_with_metrics": len(metrics_by_content),
                "by_type": _summarize(type_buckets, "content_type"),
                "by_style": _summarize(style_buckets, "style"),
                "top_performers": top_performers,
            }
        finally:
            session.close()

    def get_calendar_conflicts(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """Return calendar events between [start_date, end_date], minimal shape used
        by the schedule planner to avoid double-booking a date+platform pair."""
        session = self._get_session()
        try:
            rows = (
                session.query(CalendarEvent)
                .filter(
                    CalendarEvent.scheduled_date >= start_date,
                    CalendarEvent.scheduled_date <= end_date,
                )
                .all()
            )
            return [
                {
                    "scheduled_date": r.scheduled_date.isoformat(),
                    "platform": r.platform,
                    "content_id": r.content_id,
                    "status": r.status,
                }
                for r in rows
            ]
        finally:
            session.close()

    def list_optimization_candidates(self, criteria: str = "underperforming", limit: int = 5) -> List[Dict[str, Any]]:
        """Find contents that may benefit from refinement. Used by the chat Agent's
        find_optimization_candidates tool.

        criteria options:
          - 'underperforming': has metrics, engagement_rate below the global avg
          - 'recent_drafts':   draft / refined status, created in last 7 days
          - 'old_drafts':      draft status, created > 14 days ago, never finalized
        """
        session = self._get_session()
        try:
            criteria = (criteria or "underperforming").lower()
            now = datetime.now()
            results: List[Dict[str, Any]] = []

            if criteria == "underperforming":
                contents = session.query(Content).all()
                metric_rows = session.query(ContentMetrics).all()
                metrics_by_content: dict[int, ContentMetrics] = {}
                for m in metric_rows:
                    existing = metrics_by_content.get(m.content_id)
                    if existing is None or (m.views or 0) > (existing.views or 0):
                        metrics_by_content[m.content_id] = m
                if not metrics_by_content:
                    return []
                rates: list[tuple[Content, ContentMetrics, float]] = []
                for c in contents:
                    m = metrics_by_content.get(c.id)
                    if m is None or not m.views:
                        continue
                    rate = ((m.likes or 0) + (m.comments or 0) + (m.shares or 0)) / m.views
                    rates.append((c, m, rate))
                if not rates:
                    return []
                avg_rate = sum(r for _, _, r in rates) / len(rates)
                weak = [(c, m, r) for c, m, r in rates if r < avg_rate]
                weak.sort(key=lambda x: x[2])
                for c, m, r in weak[:limit]:
                    results.append({
                        "id": c.id,
                        "title": c.title,
                        "content_type": c.content_type,
                        "style": c.style,
                        "status": c.status,
                        "views": m.views or 0,
                        "engagement_rate": round(r, 4),
                        "global_avg_rate": round(avg_rate, 4),
                        "reason": f"engagement {round(r,4)} < cohort avg {round(avg_rate,4)}",
                    })
            elif criteria == "recent_drafts":
                cutoff = now - timedelta(days=7)
                rows = (
                    session.query(Content)
                    .filter(
                        Content.status.in_(["draft", "refined"]),
                        Content.created_at >= cutoff,
                    )
                    .order_by(Content.created_at.desc())
                    .limit(limit)
                    .all()
                )
                for c in rows:
                    age_days = max(0, (now - c.created_at).days) if c.created_at else 0
                    results.append({
                        "id": c.id,
                        "title": c.title,
                        "content_type": c.content_type,
                        "style": c.style,
                        "status": c.status,
                        "age_days": age_days,
                        "reason": f"recent {c.status}, {age_days}d old, not yet finalized",
                    })
            elif criteria == "old_drafts":
                cutoff = now - timedelta(days=14)
                rows = (
                    session.query(Content)
                    .filter(Content.status == "draft", Content.created_at <= cutoff)
                    .order_by(Content.created_at)
                    .limit(limit)
                    .all()
                )
                for c in rows:
                    age_days = max(0, (now - c.created_at).days) if c.created_at else 0
                    results.append({
                        "id": c.id,
                        "title": c.title,
                        "content_type": c.content_type,
                        "style": c.style,
                        "status": c.status,
                        "age_days": age_days,
                        "reason": f"draft sitting {age_days}d, may need a decision",
                    })
            return results
        finally:
            session.close()

    def archive_content(self, content_id: int) -> bool:
        session = self._get_session()
        try:
            content = session.query(Content).filter(Content.id == content_id).first()
            if not content:
                return False
            content.status = "archived"
            content.updated_at = datetime.now()
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete_content(self, content_id: int) -> Optional[Dict[str, Any]]:
        session = self._get_session()
        try:
            content = session.query(Content).filter(Content.id == content_id).first()
            if not content:
                return None

            media_assets = (
                session.query(MediaAsset)
                .filter(MediaAsset.content_id == content_id)
                .order_by(MediaAsset.created_at)
                .all()
            )
            deleted = {
                "content": self._content_to_dict(content),
                "media_assets": [self._media_asset_to_dict(asset) for asset in media_assets],
            }

            session.query(Content).filter(Content.parent_id == content_id).update(
                {Content.parent_id: None},
                synchronize_session=False,
            )
            session.query(CalendarEvent).filter(CalendarEvent.content_id == content_id).delete(synchronize_session=False)
            session.query(ContentMetrics).filter(ContentMetrics.content_id == content_id).delete(synchronize_session=False)
            session.query(MediaAsset).filter(MediaAsset.content_id == content_id).delete(synchronize_session=False)
            session.query(PlatformPublication).filter(
                PlatformPublication.content_id == content_id
            ).delete(synchronize_session=False)
            session.delete(content)
            session.commit()
            return deleted
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def save_media_asset(
        self,
        content_id: int,
        media_type: str,
        source_type: str,
        file_name: str,
        file_path: str,
        mime_type: str | None = None,
        provider: str | None = None,
        generation_params: dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        session = self._get_session()
        try:
            current_order = (
                session.query(func.max(MediaAsset.sort_order))
                .filter(MediaAsset.content_id == content_id, MediaAsset.media_type == media_type)
                .scalar()
            )
            asset = MediaAsset(
                content_id=content_id,
                media_type=media_type,
                source_type=source_type,
                file_name=file_name,
                file_path=file_path,
                mime_type=mime_type,
                sort_order=(current_order or 0) + 1,
                provider=provider,
                generation_params=json.dumps(generation_params, ensure_ascii=False) if generation_params else None,
            )
            session.add(asset)
            session.commit()
            session.refresh(asset)
            return self._media_asset_to_dict(asset)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_media_asset(self, media_id: int) -> Optional[Dict[str, Any]]:
        session = self._get_session()
        try:
            asset = session.query(MediaAsset).filter(MediaAsset.id == media_id).first()
            if not asset:
                return None
            return self._media_asset_to_dict(asset)
        finally:
            session.close()

    def list_media_assets(self, content_id: int, media_type: str | None = None) -> List[Dict[str, Any]]:
        session = self._get_session()
        try:
            query = session.query(MediaAsset).filter(MediaAsset.content_id == content_id)
            if media_type:
                query = query.filter(MediaAsset.media_type == media_type)
            assets = query.order_by(MediaAsset.media_type, MediaAsset.sort_order, MediaAsset.created_at).all()
            return [self._media_asset_to_dict(asset) for asset in assets]
        finally:
            session.close()

    def delete_media_asset(self, media_id: int) -> Optional[Dict[str, Any]]:
        session = self._get_session()
        try:
            asset = session.query(MediaAsset).filter(MediaAsset.id == media_id).first()
            if not asset:
                return None
            data = self._media_asset_to_dict(asset)
            session.delete(asset)
            session.commit()
            return data
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_publication(
        self,
        content_id: int,
        platform: str,
        publish_type: str,
        status: str,
        title: str | None,
        body: str,
        scheduled_at: datetime | None = None,
        request_payload: dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        session = self._get_session()
        try:
            publication = PlatformPublication(
                content_id=content_id,
                platform=platform,
                publish_type=publish_type,
                status=status,
                title=title,
                body=body,
                scheduled_at=scheduled_at,
                request_payload=json.dumps(request_payload, ensure_ascii=False) if request_payload else None,
            )
            session.add(publication)
            session.commit()
            session.refresh(publication)
            return self._publication_to_dict(publication)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_publication(self, publication_id: int) -> Optional[Dict[str, Any]]:
        session = self._get_session()
        try:
            publication = session.query(PlatformPublication).filter(PlatformPublication.id == publication_id).first()
            if not publication:
                return None
            return self._publication_to_dict(publication)
        finally:
            session.close()

    def list_publications(self, content_id: int) -> List[Dict[str, Any]]:
        session = self._get_session()
        try:
            publications = (
                session.query(PlatformPublication)
                .filter(PlatformPublication.content_id == content_id)
                .order_by(PlatformPublication.created_at.desc())
                .all()
            )
            return [self._publication_to_dict(publication) for publication in publications]
        finally:
            session.close()

    def update_publication(self, publication_id: int, **fields) -> Optional[Dict[str, Any]]:
        session = self._get_session()
        try:
            publication = session.query(PlatformPublication).filter(PlatformPublication.id == publication_id).first()
            if not publication:
                return None

            for key in ("request_payload", "response_payload"):
                if key in fields and fields[key] is not None:
                    fields[key] = json.dumps(fields[key], ensure_ascii=False)

            for key, value in fields.items():
                if hasattr(publication, key):
                    setattr(publication, key, value)
            publication.updated_at = datetime.now()
            session.commit()
            session.refresh(publication)
            return self._publication_to_dict(publication)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_job(
        self,
        job_id: str,
        job_type: str,
        payload: dict,
        provider: str | None = None,
        model: str | None = None,
    ) -> Dict[str, Any]:
        session = self._get_session()
        try:
            now = datetime.now()
            job = Job(
                id=job_id,
                job_type=job_type,
                status="queued",
                payload=json.dumps(payload, ensure_ascii=False),
                provider=provider,
                model=model,
                progress=0,
                attempts=0,
                created_at=now,
                updated_at=now,
            )
            session.add(job)
            session.commit()
            return self._job_to_dict(job)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        session = self._get_session()
        try:
            job = session.query(Job).filter(Job.id == job_id).first()
            if not job:
                return None
            return self._job_to_dict(job)
        finally:
            session.close()

    def update_job(self, job_id: str, **fields) -> Optional[Dict[str, Any]]:
        session = self._get_session()
        try:
            job = session.query(Job).filter(Job.id == job_id).first()
            if not job:
                return None

            now = datetime.now()
            status = fields.pop("status", None)
            if status:
                job.status = status
                if status == "running" and not job.started_at:
                    job.started_at = now
                if status in {"completed", "failed", "cancelled"}:
                    job.completed_at = now

            if "payload" in fields:
                job.payload = json.dumps(fields.pop("payload"), ensure_ascii=False)
            if "result" in fields:
                result = fields.pop("result")
                job.result = json.dumps(result, ensure_ascii=False) if result is not None else None
            if "error" in fields:
                job.error = fields.pop("error")

            for key, value in fields.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            job.updated_at = now
            session.commit()
            return self._job_to_dict(job)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def start_job(self, job_id: str, attempts: int, progress: int = 5) -> Optional[Dict[str, Any]]:
        """Mark a queued/failed job as running without reviving a cancelled job."""
        session = self._get_session()
        try:
            job = (
                session.query(Job)
                .filter(Job.id == job_id, Job.status.in_(["queued", "failed"]))
                .first()
            )
            if not job:
                return None
            now = datetime.now()
            job.status = "running"
            job.progress = progress
            job.attempts = attempts
            job.started_at = job.started_at or now
            job.completed_at = None
            job.updated_at = now
            session.commit()
            return self._job_to_dict(job)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def count_inflight_jobs(self, provider: str | None = None) -> int:
        session = self._get_session()
        try:
            query = session.query(Job).filter(Job.status.in_(["queued", "running"]))
            if provider:
                query = query.filter(Job.provider == provider)
            return query.count()
        finally:
            session.close()

    def upsert_agent_thread(
        self,
        thread_id: str,
        title: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> Dict[str, Any]:
        """Create or touch a thread row.

        Auto-title path: `title` is only written when the thread is brand-new
        OR the existing thread has neither a title nor a manual lock. Once
        `title_pinned=1` (set via `update_agent_thread`), title is never
        overwritten here. Provider/model always refresh to reflect the latest
        turn.
        """
        session = self._get_session()
        try:
            thread = session.query(AgentThread).filter(AgentThread.id == thread_id).first()
            now = datetime.now()
            if not thread:
                thread = AgentThread(
                    id=thread_id,
                    title=title,
                    last_provider=provider,
                    last_model=model,
                    created_at=now,
                    updated_at=now,
                )
                session.add(thread)
            else:
                if title and not thread.title and not thread.title_pinned:
                    thread.title = title
                thread.last_provider = provider or thread.last_provider
                thread.last_model = model or thread.last_model
                thread.updated_at = now
            session.commit()
            return self._agent_thread_to_dict(thread, session)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_agent_threads(
        self,
        limit: int = 30,
        offset: int = 0,
        include_archived: bool = False,
        q: str | None = None,
    ) -> List[Dict[str, Any]]:
        """List threads with pin-first ordering, optional archived filter, optional title/id search.

        Uses a single LEFT JOIN + GROUP BY to fetch message_count, replacing the
        previous N+1 (one COUNT per thread) pattern.
        """
        session = self._get_session()
        try:
            query = session.query(
                AgentThread,
                func.count(AgentMessage.id).label("message_count"),
            ).outerjoin(AgentMessage, AgentMessage.thread_id == AgentThread.id)

            if not include_archived:
                query = query.filter(AgentThread.archived.is_(False))
            if q and q.strip():
                pattern = f"%{q.strip()}%"
                query = query.filter(
                    or_(AgentThread.title.ilike(pattern), AgentThread.id.ilike(pattern))
                )

            query = (
                query.group_by(AgentThread.id)
                .order_by(AgentThread.pinned.desc(), AgentThread.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
            rows = query.all()
            return [
                self._agent_thread_to_dict(thread, session, message_count=message_count)
                for thread, message_count in rows
            ]
        finally:
            session.close()

    def get_agent_thread(self, thread_id: str) -> Optional[Dict[str, Any]]:
        session = self._get_session()
        try:
            thread = session.query(AgentThread).filter(AgentThread.id == thread_id).first()
            if not thread:
                return None
            return self._agent_thread_to_dict(thread, session)
        finally:
            session.close()

    def update_agent_thread(
        self,
        thread_id: str,
        *,
        title: str | None = None,
        pinned: bool | None = None,
        archived: bool | None = None,
    ) -> Optional[Dict[str, Any]]:
        """Manual edits to a thread row.

        - Passing `title` writes it and sets `title_pinned=True`, which locks
          out the auto-title path in `upsert_agent_thread` / `save_agent_message`.
        - All three fields are independently optional; pass only what changes.
        - Returns the refreshed dict, or None if the thread doesn't exist.
        """
        if title is None and pinned is None and archived is None:
            raise ValueError("update_agent_thread requires at least one field")
        session = self._get_session()
        try:
            thread = session.query(AgentThread).filter(AgentThread.id == thread_id).first()
            if not thread:
                return None
            if title is not None:
                thread.title = title.strip() or None
                thread.title_pinned = True
            if pinned is not None:
                thread.pinned = bool(pinned)
            if archived is not None:
                thread.archived = bool(archived)
            thread.updated_at = datetime.now()
            session.commit()
            return self._agent_thread_to_dict(thread, session)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def save_agent_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        provider: str | None = None,
        model: str | None = None,
        intent: dict | None = None,
        tool_events: list[dict] | None = None,
        plan: list[dict] | None = None,
        status: str = "completed",
    ) -> int:
        session = self._get_session()
        try:
            thread = session.query(AgentThread).filter(AgentThread.id == thread_id).first()
            if not thread:
                thread = AgentThread(
                    id=thread_id,
                    title=self._make_thread_title(content) if role == "user" else None,
                    last_provider=provider,
                    last_model=model,
                )
                session.add(thread)
            elif role == "user" and not thread.title and not thread.title_pinned:
                thread.title = self._make_thread_title(content)

            thread.last_provider = provider or thread.last_provider
            thread.last_model = model or thread.last_model
            thread.updated_at = datetime.now()

            message = AgentMessage(
                thread_id=thread_id,
                role=role,
                content=content,
                provider=provider,
                model=model,
                intent=json.dumps(intent, ensure_ascii=False) if intent else None,
                tool_events=json.dumps(tool_events or [], ensure_ascii=False),
                plan=json.dumps(plan, ensure_ascii=False) if plan else None,
                status=status,
            )
            session.add(message)
            session.commit()
            return message.id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_agent_messages(
        self,
        thread_id: str,
        limit: int = 50,
        before_id: int | None = None,
    ) -> List[Dict[str, Any]]:
        """List messages oldest-first.

        Without `before_id`, returns the most recent `limit` messages.
        With `before_id`, returns the `limit` messages with id < before_id
        (cursor-style "load older history"), still oldest-first within the slice.
        """
        session = self._get_session()
        try:
            query = session.query(AgentMessage).filter(AgentMessage.thread_id == thread_id)
            if before_id is not None:
                query = query.filter(AgentMessage.id < before_id)
            messages = query.order_by(AgentMessage.created_at.desc()).limit(limit).all()
            return [self._agent_message_to_dict(message) for message in reversed(messages)]
        finally:
            session.close()

    def search_agent_messages(
        self,
        query: str,
        limit: int = 10,
        thread_id: str | None = None,
    ) -> List[Dict[str, Any]]:
        """Substring search over agent_messages content using ILIKE."""
        query = (query or "").strip()
        if not query:
            return []
        session = self._get_session()
        try:
            q = session.query(AgentMessage).filter(AgentMessage.content.ilike(f"%{query}%"))
            if thread_id:
                q = q.filter(AgentMessage.thread_id == thread_id)
            messages = q.order_by(AgentMessage.created_at.desc()).limit(limit).all()
            return [self._agent_message_to_dict(m) for m in messages]
        finally:
            session.close()

    def delete_agent_thread(self, thread_id: str) -> bool:
        session = self._get_session()
        try:
            thread = session.query(AgentThread).filter(AgentThread.id == thread_id).first()
            if not thread:
                return False
            session.query(AgentMessage).filter(AgentMessage.thread_id == thread_id).delete()
            # proposed_actions.thread_id is a NO ACTION foreign key, so its rows must
            # be cleared here or deleting a thread that ever proposed a write fails.
            session.query(ProposedAction).filter(ProposedAction.thread_id == thread_id).delete()
            session.delete(thread)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # --- Proposed actions (one-time write capabilities) --------------------

    def create_proposed_action(
        self,
        *,
        thread_id: str,
        tool_name: str,
        args: dict[str, Any],
        impact_summary: str,
        ttl_seconds: int,
        requester: str | None = None,
        proposing_message_id: int | None = None,
        action_id: str | None = None,
    ) -> Dict[str, Any]:
        """Persist an unconfirmed proposal and return its durable action id."""
        from src.utils.canonical import args_hash, canonical_json

        session = self._get_session()
        try:
            now = datetime.now()
            action = ProposedAction(
                id=action_id or f"act_{uuid4().hex[:20]}",
                thread_id=thread_id,
                requester=requester,
                tool_name=tool_name,
                args_json=canonical_json(args),
                args_hash=args_hash(args),
                impact_summary=impact_summary,
                status="proposed",
                proposing_message_id=proposing_message_id,
                created_at=now,
                expires_at=now + timedelta(seconds=max(1, int(ttl_seconds))),
            )
            session.add(action)
            session.commit()
            # P2-01: Track proposed capabilities
            metrics.capability_proposals_total.labels(tool=tool_name).inc()
            log_capability_event(
                logger, "proposed", action.id, tool_name,
                thread_id=thread_id
            )
            return self._proposed_action_to_dict(action)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_proposed_action(self, action_id: str) -> Optional[Dict[str, Any]]:
        session = self._get_session()
        try:
            action = (
                session.query(ProposedAction)
                .filter(ProposedAction.id == action_id)
                .first()
            )
            return self._proposed_action_to_dict(action) if action else None
        finally:
            session.close()

    def list_proposed_actions(
        self,
        thread_id: str,
        *,
        statuses: tuple[str, ...] | set[str] | None = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        session = self._get_session()
        try:
            query = session.query(ProposedAction).filter(ProposedAction.thread_id == thread_id)
            if statuses:
                query = query.filter(ProposedAction.status.in_(tuple(statuses)))
            rows = (
                query.order_by(ProposedAction.created_at.desc(), ProposedAction.id.desc())
                .limit(limit)
                .all()
            )
            return [self._proposed_action_to_dict(row) for row in rows]
        finally:
            session.close()

    def latest_pending_proposed_action(
        self,
        thread_id: str,
        *,
        tool_name: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        """Most recent unexpired ``proposed`` row for a thread.

        Expiry is evaluated against the stored ``expires_at`` using the same
        application clock that wrote it, not against the recognized transcript,
        so an idle thread resumed after the TTL has no capability to confirm and
        fails closed.
        """
        session = self._get_session()
        try:
            query = (
                session.query(ProposedAction)
                .filter(
                    ProposedAction.thread_id == thread_id,
                    ProposedAction.status == "proposed",
                    ProposedAction.expires_at > datetime.now(),
                )
            )
            if tool_name:
                query = query.filter(ProposedAction.tool_name == tool_name)
            action = query.order_by(
                ProposedAction.created_at.desc(), ProposedAction.id.desc()
            ).first()
            return self._proposed_action_to_dict(action) if action else None
        finally:
            session.close()

    def confirm_proposed_action(self, action_id: str) -> Optional[Dict[str, Any]]:
        """Move exactly one ``proposed`` row to ``confirmed``.

        Two concurrent confirmations of the same proposal serialize on the row
        lock; the loser observes a non-``proposed`` status and returns ``None``,
        so a double-clicked confirm issues one capability, not two.
        """
        session = self._get_session()
        try:
            action = (
                session.query(ProposedAction)
                .filter(ProposedAction.id == action_id, ProposedAction.status == "proposed")
                .with_for_update()
                .first()
            )
            if not action:
                return None
            now = datetime.now()
            if action.expires_at <= now:
                action.status = "expired"
                session.commit()
                return None
            action.status = "confirmed"
            action.confirmed_at = now
            session.commit()
            return self._proposed_action_to_dict(action)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def consume_proposed_action(
        self,
        action_id: str,
        *,
        tool_name: str,
        args: dict[str, Any],
        consuming_message_id: int | None = None,
    ) -> Optional[Dict[str, Any]]:
        """Atomically claim a confirmed capability for one tool invocation.

        The row lock plus the ``status == 'confirmed'`` predicate make this the
        once-only gate: replay, a second executor loop iteration, and two racing
        requests all lose the race and receive ``None``. The stored hash is
        re-checked here so arguments tampered with after confirmation cannot be
        executed even though the capability itself is valid.
        """
        from src.utils.canonical import args_hash

        session = self._get_session()
        try:
            action = (
                session.query(ProposedAction)
                .filter(ProposedAction.id == action_id, ProposedAction.status == "confirmed")
                .with_for_update()
                .first()
            )
            if not action:
                return None
            now = datetime.now()
            if action.expires_at <= now:
                action.status = "expired"
                session.commit()
                # P2-01: Track expired capabilities
                metrics.capability_expired_total.inc()
                log_capability_event(
                    logger, "expired", action_id, tool_name,
                    expired=True
                )
                return None
            if action.tool_name != tool_name or action.args_hash != args_hash(args):
                # Leave the capability unconsumed: the mismatch is the model
                # substituting a different call, not the user's approved action.
                session.rollback()
                return None
            action.status = "consumed"
            action.consumed_at = now
            action.consuming_message_id = consuming_message_id
            session.commit()
            # P2-01: Track consumed capabilities
            metrics.capability_consumed_total.labels(tool=tool_name).inc()
            log_capability_event(
                logger, "consumed", action_id, tool_name,
                consumed=True
            )
            return self._proposed_action_to_dict(action)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def cancel_proposed_action(self, action_id: str) -> Optional[Dict[str, Any]]:
        """Cancel a proposal or an unused confirmation; consumed rows are final."""
        session = self._get_session()
        try:
            action = (
                session.query(ProposedAction)
                .filter(
                    ProposedAction.id == action_id,
                    ProposedAction.status.in_(("proposed", "confirmed")),
                )
                .with_for_update()
                .first()
            )
            if not action:
                return None
            action.status = "cancelled"
            action.cancelled_at = datetime.now()
            session.commit()
            return self._proposed_action_to_dict(action)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def expire_proposed_actions(self, *, thread_id: str | None = None) -> int:
        """Mark overdue pending rows expired. Returns the number updated."""
        session = self._get_session()
        try:
            query = session.query(ProposedAction).filter(
                ProposedAction.status.in_(("proposed", "confirmed")),
                ProposedAction.expires_at <= datetime.now(),
            )
            if thread_id:
                query = query.filter(ProposedAction.thread_id == thread_id)
            updated = query.update(
                {ProposedAction.status: "expired"}, synchronize_session=False
            )
            session.commit()
            return int(updated or 0)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _proposed_action_to_dict(action: ProposedAction) -> Dict[str, Any]:
        try:
            args = json.loads(action.args_json)
        except (TypeError, ValueError):
            args = {}
        return {
            "id": action.id,
            "thread_id": action.thread_id,
            "requester": action.requester,
            "tool_name": action.tool_name,
            "args": args if isinstance(args, dict) else {},
            "args_hash": action.args_hash,
            "impact_summary": action.impact_summary,
            "status": action.status,
            "proposing_message_id": action.proposing_message_id,
            "consuming_message_id": action.consuming_message_id,
            "created_at": action.created_at.isoformat() if action.created_at else None,
            "expires_at": action.expires_at.isoformat() if action.expires_at else None,
            "confirmed_at": action.confirmed_at.isoformat() if action.confirmed_at else None,
            "consumed_at": action.consumed_at.isoformat() if action.consumed_at else None,
            "cancelled_at": action.cancelled_at.isoformat() if action.cancelled_at else None,
        }

    # --- Idempotency ledger (P1-02) ---------------------------------------

    def claim_idempotency_key(
        self,
        *,
        scope: str,
        key: str,
        args: Dict[str, Any],
        external_request_id: str | None = None,
    ) -> Dict[str, Any]:
        """Claim ``(scope, key)`` for one attempt, or report the prior outcome.

        The claim is an INSERT guarded by the unique constraint, so two racing
        requests cannot both win: PostgreSQL rejects the loser, which then reads
        the existing row and reacts to its status. An application-level
        "SELECT then INSERT if absent" would leave a window where both callers see
        no row and both write.

        Returns a dict with ``outcome``:

        - ``claimed``: caller owns this attempt and must do the work, then call
          :meth:`complete_idempotency_key`.
        - ``replay``: the work already completed; ``result`` holds the original
          result and the caller must not write again.

        Raises :class:`DuplicateRequestInFlight` when another attempt holds the
        key, and :class:`IdempotencyKeyConflict` when the key is reused with
        different arguments.
        """
        from sqlalchemy.exc import IntegrityError

        from src.utils.canonical import args_hash
        from src.utils.idempotency import DuplicateRequestInFlight, IdempotencyKeyConflict

        digest = args_hash(args)
        session = self._get_session()
        try:
            record = IdempotencyRecord(
                scope=scope,
                idempotency_key=key,
                args_hash=digest,
                status="in_progress",
                external_request_id=external_request_id,
                created_at=datetime.now(),
            )
            session.add(record)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
            else:
                # P2-01: Metrics and logging
                metrics.idempotency_requests_total.labels(scope=scope, outcome="claimed").inc()
                log_idempotency_event(
                    logger, "claimed", scope, key,
                    record_id=record.id, args_hash=digest
                )
                return {
                    "outcome": "claimed",
                    "record_id": record.id,
                    "scope": scope,
                    "key": key,
                    "external_request_id": record.external_request_id,
                }

            # Lost the insert race, or this is a retry. Lock the surviving row so
            # a concurrent completion cannot change status under this read.
            existing = (
                session.query(IdempotencyRecord)
                .filter(
                    IdempotencyRecord.scope == scope,
                    IdempotencyRecord.idempotency_key == key,
                )
                .with_for_update()
                .first()
            )
            if existing is None:
                # The row was deleted between the failed insert and this read.
                raise DuplicateRequestInFlight(
                    f"Idempotency key for {scope} could not be claimed; retry the request"
                )
            # Check args compatibility based on current status:
            # - failed: retryable with any args (previous attempt didn't succeed)
            # - completed/in_progress: args must match (can't change a success or in-flight request)
            if existing.status != "failed" and existing.args_hash != digest:
                # P2-01: Metrics and logging
                metrics.idempotency_conflicts_total.labels(scope=scope).inc()
                metrics.idempotency_requests_total.labels(scope=scope, outcome="conflict").inc()
                log_idempotency_event(
                    logger, "conflict", scope, key,
                    record_id=existing.id, args_hash=digest, conflict=True
                )
                raise IdempotencyKeyConflict(
                    f"Idempotency key was already used for {scope} with different arguments"
                )
            if existing.status == "completed":
                # P2-01: Metrics and logging
                metrics.idempotency_requests_total.labels(scope=scope, outcome="replay").inc()
                metrics.idempotency_replay_rate.labels(scope=scope).inc()
                log_idempotency_event(
                    logger, "replay", scope, key,
                    record_id=existing.id, args_hash=existing.args_hash
                )
                return {
                    "outcome": "replay",
                    "record_id": existing.id,
                    "scope": scope,
                    "key": key,
                    "result": self._idempotency_result(existing),
                    "external_request_id": existing.external_request_id,
                }
            if existing.status == "failed":
                # A failed attempt is retryable: reclaim the same row rather than
                # inserting a second one, which the unique constraint forbids.
                # Update args_hash to reflect the new attempt's arguments.
                existing.status = "in_progress"
                existing.args_hash = digest
                existing.result_json = None
                existing.completed_at = None
                if external_request_id is not None:
                    existing.external_request_id = external_request_id
                session.commit()
                return {
                    "outcome": "claimed",
                    "record_id": existing.id,
                    "scope": scope,
                    "key": key,
                    "external_request_id": existing.external_request_id,
                }
            raise DuplicateRequestInFlight(
                f"Another request is already processing this {scope} key"
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def complete_idempotency_key(
        self,
        record_id: int,
        *,
        result: Any,
    ) -> bool:
        """Record the result of a claimed attempt so retries can replay it."""
        session = self._get_session()
        try:
            record = (
                session.query(IdempotencyRecord)
                .filter(
                    IdempotencyRecord.id == record_id,
                    IdempotencyRecord.status == "in_progress",
                )
                .with_for_update()
                .first()
            )
            if not record:
                return False
            record.status = "completed"
            record.result_json = json.dumps(result, ensure_ascii=False, default=str)
            record.completed_at = datetime.now()
            session.commit()
            # P2-01: Log completion
            log_idempotency_event(
                logger, "completed", record.scope, record.idempotency_key,
                record_id=record.id
            )
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def fail_idempotency_key(self, record_id: int) -> bool:
        """Release a claimed attempt that raised, leaving the key retryable.

        Without this a transient provider error would burn the key permanently and
        the user could never retry that request.
        """
        session = self._get_session()
        try:
            record = (
                session.query(IdempotencyRecord)
                .filter(
                    IdempotencyRecord.id == record_id,
                    IdempotencyRecord.status == "in_progress",
                )
                .with_for_update()
                .first()
            )
            if not record:
                return False
            record.status = "failed"
            record.completed_at = datetime.now()
            session.commit()
            # P2-01: Log failure
            log_idempotency_event(
                logger, "failed", record.scope, record.idempotency_key,
                record_id=record.id
            )
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_idempotency_record(self, *, scope: str, key: str) -> Optional[Dict[str, Any]]:
        session = self._get_session()
        try:
            record = (
                session.query(IdempotencyRecord)
                .filter(
                    IdempotencyRecord.scope == scope,
                    IdempotencyRecord.idempotency_key == key,
                )
                .first()
            )
            if not record:
                return None
            return {
                "id": record.id,
                "scope": record.scope,
                "key": record.idempotency_key,
                "args_hash": record.args_hash,
                "status": record.status,
                "result": self._idempotency_result(record),
                "external_request_id": record.external_request_id,
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "completed_at": record.completed_at.isoformat() if record.completed_at else None,
            }
        finally:
            session.close()

    @staticmethod
    def _idempotency_result(record: IdempotencyRecord) -> Any:
        if record.result_json is None:
            return None
        try:
            return json.loads(record.result_json)
        except (TypeError, ValueError):
            return None

    # --- Pipeline run records ---------------------------------------------

    def create_run(
        self,
        run_id: str,
        topic: str,
        content_type: str,
        style: str,
        provider: str | None = None,
        model: str | None = None,
        thread_id: str | None = None,
    ) -> Dict[str, Any]:
        session = self._get_session()
        try:
            run = AgentRun(
                id=run_id,
                thread_id=thread_id,
                topic=topic,
                content_type=content_type,
                style=style,
                provider=provider,
                model=model,
                status="running",
            )
            session.add(run)
            session.commit()
            return self._agent_run_to_dict(run)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_run(self, run_id: str, **fields) -> Optional[Dict[str, Any]]:
        if fields.get("status") in {"completed", "failed", "cancelled"}:
            raise ValueError(
                "Terminal run states must use transition_run_and_append_event()"
            )
        session = self._get_session()
        try:
            run = session.query(AgentRun).filter(AgentRun.id == run_id).first()
            if not run:
                return None
            if "plan" in fields:
                run.plan_json = json.dumps(fields.pop("plan"), ensure_ascii=False)
            for key, value in fields.items():
                if hasattr(run, key):
                    setattr(run, key, value)
            if fields.get("status") in {"completed", "failed", "cancelled"} or run.status in {"completed", "failed", "cancelled"}:
                run.completed_at = run.completed_at or datetime.now()
            session.commit()
            return self._agent_run_to_dict(run)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        session = self._get_session()
        try:
            run = session.query(AgentRun).filter(AgentRun.id == run_id).first()
            return self._agent_run_to_dict(run) if run else None
        finally:
            session.close()

    def list_runs(self, thread_id: str | None = None, limit: int = 30) -> List[Dict[str, Any]]:
        session = self._get_session()
        try:
            query = session.query(AgentRun)
            if thread_id:
                query = query.filter(AgentRun.thread_id == thread_id)
            runs = query.order_by(AgentRun.created_at.desc()).limit(limit).all()
            return [self._agent_run_to_dict(run) for run in runs]
        finally:
            session.close()

    def append_run_event(self, run_id: str, event_type: str, payload: dict[str, Any]) -> Optional[int]:
        """Append a non-terminal event while the run is still active.

        The run-row lock serializes this check with terminal CAS transitions. If
        cancellation/completion/failure already won, the event is discarded so
        the terminal event remains the durable end of the stream.
        """
        session = self._get_session()
        try:
            run = (
                session.query(AgentRun)
                .filter(AgentRun.id == run_id)
                .with_for_update()
                .first()
            )
            if not run:
                raise LookupError(f"Run {run_id} was not found")
            if run.status != "running":
                session.rollback()
                return None
            seq = int(run.next_event_seq or 1)
            run.next_event_seq = seq + 1
            session.add(AgentRunEvent(
                run_id=run_id,
                seq=seq,
                event_type=event_type,
                payload=json.dumps(payload, ensure_ascii=False),
            ))
            session.commit()
            return seq
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def complete_run_with_content(
        self,
        run_id: str,
        *,
        payload: dict[str, Any],
        content_fields: dict[str, Any] | None,
        plan: list[dict[str, Any]],
        revision_count: int,
        total_prompt_tokens: int,
        total_completion_tokens: int,
        total_cost: float,
    ) -> Optional[Dict[str, Any]]:
        """Atomically persist final content, complete the run, and append its event.

        Cancellation and completion serialize on the run row. If cancellation
        already won, no ``agent_final`` content row is inserted.
        """
        session = self._get_session()
        try:
            run = (
                session.query(AgentRun)
                .filter(AgentRun.id == run_id, AgentRun.status == "running")
                .with_for_update()
                .first()
            )
            if not run:
                return None

            saved_content_id: int | None = None
            if content_fields:
                content = Content(**content_fields)
                session.add(content)
                session.flush()
                saved_content_id = content.id

            event_payload = json.loads(json.dumps(payload, ensure_ascii=False))
            event_payload["saved_content_id"] = saved_content_id
            run.plan_json = json.dumps(plan, ensure_ascii=False)
            run.revision_count = revision_count
            run.total_prompt_tokens = total_prompt_tokens
            run.total_completion_tokens = total_completion_tokens
            run.total_cost = total_cost
            run.saved_content_id = saved_content_id
            run.status = "completed"
            run.completed_at = run.completed_at or datetime.now()
            seq = int(run.next_event_seq or 1)
            run.next_event_seq = seq + 1
            session.add(AgentRunEvent(
                run_id=run_id,
                seq=seq,
                event_type="run_complete",
                payload=json.dumps(event_payload, ensure_ascii=False),
            ))
            session.commit()
            result = self._agent_run_to_dict(run)
            result["event_seq"] = seq
            return result
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def transition_run_and_append_event(
        self,
        run_id: str,
        *,
        expected_statuses: set[str] | tuple[str, ...],
        new_status: str,
        event_type: str,
        payload: dict[str, Any],
        **fields: Any,
    ) -> Optional[Dict[str, Any]]:
        """Compare-and-set a run state and append its event in one transaction.

        Returns ``None`` when another actor already moved the run out of an
        expected state. This is the only supported path for terminal run state
        changes, preventing duplicate terminal events during cancel/fail races.
        """
        session = self._get_session()
        try:
            run = (
                session.query(AgentRun)
                .filter(AgentRun.id == run_id, AgentRun.status.in_(tuple(expected_statuses)))
                .with_for_update()
                .first()
            )
            if not run:
                return None
            if "plan" in fields:
                run.plan_json = json.dumps(fields.pop("plan"), ensure_ascii=False)
            for key, value in fields.items():
                if hasattr(run, key):
                    setattr(run, key, value)
            run.status = new_status
            if new_status in {"completed", "failed", "cancelled"}:
                run.completed_at = run.completed_at or datetime.now()
            seq = int(run.next_event_seq or 1)
            run.next_event_seq = seq + 1
            session.add(AgentRunEvent(
                run_id=run_id,
                seq=seq,
                event_type=event_type,
                payload=json.dumps(payload, ensure_ascii=False),
            ))
            session.commit()
            result = self._agent_run_to_dict(run)
            result["event_seq"] = seq
            return result
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_run_events(
        self,
        run_id: str,
        after_seq: int = 0,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        session = self._get_session()
        try:
            events = (
                session.query(AgentRunEvent)
                .filter(AgentRunEvent.run_id == run_id, AgentRunEvent.seq > after_seq)
                .order_by(AgentRunEvent.seq)
                .limit(limit)
                .all()
            )
            return [
                {
                    "seq": e.seq,
                    "event_type": e.event_type,
                    "payload": e.payload,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in events
            ]
        finally:
            session.close()

    @staticmethod
    def _agent_run_to_dict(run: AgentRun) -> Dict[str, Any]:
        return {
            "id": run.id,
            "thread_id": run.thread_id,
            "topic": run.topic,
            "content_type": run.content_type,
            "style": run.style,
            "provider": run.provider,
            "model": run.model,
            "plan": json.loads(run.plan_json) if run.plan_json else [],
            "revision_count": run.revision_count or 0,
            "total_prompt_tokens": run.total_prompt_tokens or 0,
            "total_completion_tokens": run.total_completion_tokens or 0,
            "total_cost": run.total_cost or 0.0,
            "saved_content_id": run.saved_content_id,
            "status": run.status,
            "error": run.error,
            "next_event_seq": run.next_event_seq or 1,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }

    @staticmethod
    def _make_thread_title(content: str) -> str:
        title = " ".join(content.strip().split())
        return title[:40] or "Untitled thread"

    @staticmethod
    def _agent_message_to_dict(message: AgentMessage) -> Dict[str, Any]:
        return {
            "id": message.id,
            "thread_id": message.thread_id,
            "role": message.role,
            "content": message.content,
            "provider": message.provider,
            "model": message.model,
            "intent": json.loads(message.intent) if message.intent else None,
            "tool_events": json.loads(message.tool_events) if message.tool_events else [],
            "plan": json.loads(message.plan) if message.plan else [],
            "status": message.status,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }

    @staticmethod
    def _agent_thread_to_dict(
        thread: AgentThread,
        session: Session,
        message_count: int | None = None,
    ) -> Dict[str, Any]:
        if message_count is None:
            message_count = (
                session.query(AgentMessage).filter(AgentMessage.thread_id == thread.id).count()
            )
        return {
            "id": thread.id,
            "title": thread.title,
            "last_provider": thread.last_provider,
            "last_model": thread.last_model,
            "pinned": bool(thread.pinned),
            "archived": bool(thread.archived),
            "title_pinned": bool(thread.title_pinned),
            "message_count": message_count,
            "created_at": thread.created_at.isoformat() if thread.created_at else None,
            "updated_at": thread.updated_at.isoformat() if thread.updated_at else None,
        }

    @staticmethod
    def _content_to_dict(content: Content) -> Dict[str, Any]:
        return {
            "id": content.id,
            "title": content.title,
            "content": content.content,
            "content_type": content.content_type,
            "style": content.style,
            "keywords": json.loads(content.keywords) if content.keywords else [],
            "tags": json.loads(content.tags) if content.tags else [],
            "status": content.status,
            "version": content.version,
            "parent_id": content.parent_id,
            "created_at": content.created_at.isoformat() if content.created_at else None,
            "updated_at": content.updated_at.isoformat() if content.updated_at else None,
        }

    @staticmethod
    def _media_asset_to_dict(asset: MediaAsset) -> Dict[str, Any]:
        return {
            "id": asset.id,
            "content_id": asset.content_id,
            "media_type": asset.media_type,
            "source_type": asset.source_type,
            "file_name": asset.file_name,
            "file_path": asset.file_path,
            "mime_type": asset.mime_type,
            "sort_order": asset.sort_order or 0,
            "provider": asset.provider,
            "generation_params": json.loads(asset.generation_params) if asset.generation_params else None,
            "created_at": asset.created_at.isoformat() if asset.created_at else None,
        }

    @staticmethod
    def _publication_to_dict(publication: PlatformPublication) -> Dict[str, Any]:
        return {
            "id": publication.id,
            "content_id": publication.content_id,
            "platform": publication.platform,
            "publish_type": publication.publish_type,
            "status": publication.status,
            "title": publication.title,
            "body": publication.body,
            "scheduled_at": publication.scheduled_at.isoformat() if publication.scheduled_at else None,
            "published_at": publication.published_at.isoformat() if publication.published_at else None,
            "external_post_id": publication.external_post_id,
            "request_payload": json.loads(publication.request_payload) if publication.request_payload else None,
            "response_payload": json.loads(publication.response_payload) if publication.response_payload else None,
            "error_message": publication.error_message,
            "created_at": publication.created_at.isoformat() if publication.created_at else None,
            "updated_at": publication.updated_at.isoformat() if publication.updated_at else None,
        }

    @staticmethod
    def _job_to_dict(job: Job) -> Dict[str, Any]:
        return {
            "id": job.id,
            "job_type": job.job_type,
            "status": job.status,
            "payload": json.loads(job.payload) if job.payload else {},
            "result": json.loads(job.result) if job.result else None,
            "error": job.error,
            "provider": job.provider,
            "model": job.model,
            "progress": job.progress or 0,
            "attempts": job.attempts or 0,
            "max_retries": job.max_retries or 5,
            "next_retry_at": job.next_retry_at.isoformat() if job.next_retry_at else None,
            "error_type": job.error_type,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }
