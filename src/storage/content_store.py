"""内容存储 - SQLAlchemy ORM + CRUD"""
import json
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pathlib import Path

from sqlalchemy import create_engine, Column, Integer, String, Text, Float, DateTime, Date, ForeignKey
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


class ContentStore:
    """内容存储管理类"""

    def __init__(self, db_path: str = "data/content_ops.db", database_url: str | None = None):
        if database_url is None:
            db_file = Path(db_path)
            db_file.parent.mkdir(parents=True, exist_ok=True)
            database_url = f"sqlite:///{db_file.as_posix()}"
        else:
            url = make_url(database_url)
            if url.drivername.startswith("sqlite") and url.database and url.database != ":memory:":
                Path(url.database).parent.mkdir(parents=True, exist_ok=True)

        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, echo=False, connect_args=connect_args)
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
            by_type = {}
            for ct in ["xiaohongshu", "weibo", "blog", "video_script", "twitter"]:
                count = session.query(Content).filter(Content.content_type == ct).count()
                if count > 0:
                    by_type[ct] = count
            by_status = {}
            for st in ["draft", "refined", "published", "archived"]:
                count = session.query(Content).filter(Content.status == st).count()
                if count > 0:
                    by_status[st] = count
            return {"total_contents": total, "by_type": by_type, "by_status": by_status}
        finally:
            session.close()
