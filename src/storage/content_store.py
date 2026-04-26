"""内容存储 - SQLAlchemy ORM + CRUD"""
import json
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pathlib import Path

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, create_engine, func, text
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
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


Index("ix_jobs_status_created", Job.status, Job.created_at)
Index("ix_jobs_provider_status", Job.provider, Job.status)


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
        self.SessionLocal = sessionmaker(bind=self.engine)

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
