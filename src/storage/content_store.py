"""内容存储 - SQLAlchemy ORM + CRUD"""
import json
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, create_engine, func, inspect, or_, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker, Session


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
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


Index("ix_agent_threads_updated_at", AgentThread.updated_at)


class AgentMessage(Base):
    """Persisted Agent chat message."""

    __tablename__ = "agent_messages"

    id = Column(Integer, primary_key=True)
    thread_id = Column(String(80), ForeignKey("agent_threads.id"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    provider = Column(String(50), nullable=True)
    model = Column(String(200), nullable=True)
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
    created_at = Column(DateTime, default=datetime.now)
    completed_at = Column(DateTime, nullable=True)


Index("ix_agent_runs_thread_created", AgentRun.thread_id, AgentRun.created_at)


class AgentRunEvent(Base):
    """Append-only event log for a pipeline run; SSE bridge reads this table."""

    __tablename__ = "agent_run_events"

    id = Column(Integer, primary_key=True)
    run_id = Column(String(80), ForeignKey("agent_runs.id"), nullable=False)
    seq = Column(Integer, nullable=False)
    event_type = Column(String(40), nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.now)


Index("ix_agent_run_events_run_seq", AgentRunEvent.run_id, AgentRunEvent.seq)


class AgentMemory(Base):
    """Long-term semantic memory for the chat agent."""
    __tablename__ = "agent_memories"

    id = Column(String(80), primary_key=True)
    content = Column(Text, nullable=False)
    category = Column(String(50), nullable=False)
    importance = Column(Float, default=0.5)
    source_thread_id = Column(String(80), nullable=True)
    access_count = Column(Integer, default=0)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


Index("ix_agent_memories_category", AgentMemory.category)
Index("ix_agent_memories_importance", AgentMemory.importance)


class ContentStore:
    """内容存储管理类"""

    def __init__(self, db_path: str = "data/content_ops.db", database_url: str | None = None):
        if database_url is None:
            db_file = Path(db_path)
            db_file.parent.mkdir(parents=True, exist_ok=True)
            database_url = f"sqlite:///{db_file.as_posix()}"
            url = make_url(database_url)
        else:
            url = make_url(database_url)
            if url.drivername.startswith("sqlite") and url.database and url.database != ":memory:":
                Path(url.database).parent.mkdir(parents=True, exist_ok=True)

        if url.drivername.startswith("sqlite"):
            connect_args = {"check_same_thread": False, "timeout": 30}
            engine_kwargs = {"connect_args": connect_args}
        else:
            from src.utils import config

            engine_kwargs = {
                "pool_size": config.DB_POOL_SIZE,
                "max_overflow": config.DB_MAX_OVERFLOW,
                "pool_timeout": config.DB_POOL_TIMEOUT_SECONDS,
                "pool_pre_ping": True,
            }
        self.database_url = database_url
        self.engine = create_engine(database_url, echo=False, **engine_kwargs)
        if url.drivername.startswith("sqlite"):
            with self.engine.connect() as connection:
                connection.execute(text("PRAGMA journal_mode=WAL"))
                connection.execute(text("PRAGMA busy_timeout=30000"))
        Base.metadata.create_all(self.engine)
        self._ensure_legacy_columns()
        self.SessionLocal = sessionmaker(bind=self.engine)

    def _ensure_legacy_columns(self) -> None:
        existing = {col["name"] for col in inspect(self.engine).get_columns("agent_messages")}
        if "plan" not in existing:
            with self.engine.begin() as connection:
                connection.execute(text("ALTER TABLE agent_messages ADD COLUMN plan TEXT"))

        job_cols = {col["name"] for col in inspect(self.engine).get_columns("jobs")}
        with self.engine.begin() as connection:
            if "token_usage" not in job_cols:
                connection.execute(text("ALTER TABLE jobs ADD COLUMN token_usage INTEGER DEFAULT 0"))
            if "cost_estimate" not in job_cols:
                connection.execute(text("ALTER TABLE jobs ADD COLUMN cost_estimate FLOAT DEFAULT 0"))

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
                if status in {"completed", "failed"}:
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
                if title and not thread.title:
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

    def list_agent_threads(self, limit: int = 30) -> List[Dict[str, Any]]:
        session = self._get_session()
        try:
            threads = (
                session.query(AgentThread)
                .order_by(AgentThread.updated_at.desc())
                .limit(limit)
                .all()
            )
            return [self._agent_thread_to_dict(thread, session) for thread in threads]
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

    def save_agent_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        provider: str | None = None,
        model: str | None = None,
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
            elif role == "user" and not thread.title:
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

    def list_agent_messages(self, thread_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        session = self._get_session()
        try:
            messages = (
                session.query(AgentMessage)
                .filter(AgentMessage.thread_id == thread_id)
                .order_by(AgentMessage.created_at.desc())
                .limit(limit)
                .all()
            )
            return [self._agent_message_to_dict(message) for message in reversed(messages)]
        finally:
            session.close()

    def delete_agent_thread(self, thread_id: str) -> bool:
        session = self._get_session()
        try:
            thread = session.query(AgentThread).filter(AgentThread.id == thread_id).first()
            if not thread:
                return False
            session.query(AgentMessage).filter(AgentMessage.thread_id == thread_id).delete()
            session.delete(thread)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

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
            if fields.get("status") in {"completed", "failed"} or run.status in {"completed", "failed"}:
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

    def append_run_event(self, run_id: str, event_type: str, payload: dict[str, Any]) -> int:
        session = self._get_session()
        try:
            last_seq = (
                session.query(func.max(AgentRunEvent.seq))
                .filter(AgentRunEvent.run_id == run_id)
                .scalar()
            ) or 0
            event = AgentRunEvent(
                run_id=run_id,
                seq=last_seq + 1,
                event_type=event_type,
                payload=json.dumps(payload, ensure_ascii=False),
            )
            session.add(event)
            session.commit()
            return event.seq
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
            "tool_events": json.loads(message.tool_events) if message.tool_events else [],
            "plan": json.loads(message.plan) if message.plan else [],
            "status": message.status,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }

    @staticmethod
    def _agent_thread_to_dict(thread: AgentThread, session: Session) -> Dict[str, Any]:
        message_count = session.query(AgentMessage).filter(AgentMessage.thread_id == thread.id).count()
        return {
            "id": thread.id,
            "title": thread.title,
            "last_provider": thread.last_provider,
            "last_model": thread.last_model,
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
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }

    # ─── Memory CRUD ───────────────────────────────────────────────────────

    def save_memory(
        self,
        memory_id: str,
        content: str,
        category: str,
        importance: float = 0.5,
        source_thread_id: str | None = None,
    ) -> Dict[str, Any]:
        session = self._get_session()
        try:
            existing = session.query(AgentMemory).filter_by(id=memory_id).first()
            if existing:
                existing.content = content
                existing.category = category
                existing.importance = importance
                existing.updated_at = datetime.now()
            else:
                existing = AgentMemory(
                    id=memory_id,
                    content=content,
                    category=category,
                    importance=importance,
                    source_thread_id=source_thread_id,
                )
                session.add(existing)
            session.commit()
            return self._memory_to_dict(existing)
        except Exception:
            session.rollback()
            raise

    def get_memory(self, memory_id: str) -> Optional[Dict[str, Any]]:
        session = self._get_session()
        mem = session.query(AgentMemory).filter_by(id=memory_id).first()
        return self._memory_to_dict(mem) if mem else None

    def search_memories_text(self, query: str, category: str | None = None, limit: int = 10) -> List[Dict[str, Any]]:
        session = self._get_session()
        q = session.query(AgentMemory)
        if category:
            q = q.filter(AgentMemory.category == category)
        q = q.filter(AgentMemory.content.ilike(f"%{query}%"))
        q = q.order_by(AgentMemory.importance.desc(), AgentMemory.updated_at.desc())
        return [self._memory_to_dict(m) for m in q.limit(limit).all()]

    def touch_memory(self, memory_id: str) -> None:
        session = self._get_session()
        try:
            mem = session.query(AgentMemory).filter_by(id=memory_id).first()
            if mem:
                mem.access_count = (mem.access_count or 0) + 1
                mem.last_used_at = datetime.now()
                session.commit()
        except Exception:
            session.rollback()
            raise

    def delete_memory(self, memory_id: str) -> bool:
        session = self._get_session()
        try:
            mem = session.query(AgentMemory).filter_by(id=memory_id).first()
            if not mem:
                return False
            session.delete(mem)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise

    def count_memories(self) -> int:
        session = self._get_session()
        return session.query(AgentMemory).count()

    def evict_memories(self, keep_count: int) -> int:
        session = self._get_session()
        try:
            all_mems = session.query(AgentMemory).all()
            if len(all_mems) <= keep_count:
                return 0
            now = datetime.now()
            scored = []
            for m in all_mems:
                days_since_use = (now - (m.last_used_at or m.created_at)).days
                recency_score = max(0.0, 1.0 - days_since_use / 90.0)
                score = (m.importance or 0.5) * 0.7 + recency_score * 0.3
                scored.append((score, m))
            scored.sort(key=lambda x: x[0], reverse=True)
            to_delete = scored[keep_count:]
            for _, m in to_delete:
                session.delete(m)
            session.commit()
            return len(to_delete)
        except Exception:
            session.rollback()
            raise

    def list_memories(self, category: str | None = None, limit: int = 50) -> List[Dict[str, Any]]:
        session = self._get_session()
        q = session.query(AgentMemory)
        if category:
            q = q.filter(AgentMemory.category == category)
        q = q.order_by(AgentMemory.importance.desc(), AgentMemory.updated_at.desc())
        return [self._memory_to_dict(m) for m in q.limit(limit).all()]

    @staticmethod
    def _memory_to_dict(mem: AgentMemory) -> Dict[str, Any]:
        return {
            "id": mem.id,
            "content": mem.content,
            "category": mem.category,
            "importance": mem.importance,
            "source_thread_id": mem.source_thread_id,
            "access_count": mem.access_count or 0,
            "last_used_at": mem.last_used_at.isoformat() if mem.last_used_at else None,
            "created_at": mem.created_at.isoformat() if mem.created_at else None,
            "updated_at": mem.updated_at.isoformat() if mem.updated_at else None,
        }
