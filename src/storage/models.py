"""ORM models for accounts, content, jobs, runs, and idempotency.

Separated from :mod:`src.storage.content_store` so that importing the models —
which Alembic, tests, and type checkers all do — does not pull in the store's
query surface. The store imports these; nothing here imports the store.

Nullability is load-bearing, and the annotation is what sets it. ``Mapped[X]``
maps to ``NOT NULL`` and ``Mapped[X | None]`` maps to nullable; ``nullable=`` is
passed only where a column is a deliberate exception (primary keys, and a few
columns whose SQLAlchemy default would otherwise disagree with the annotation).
Changing an annotation can therefore change the emitted DDL, which
``alembic check`` is what catches.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.storage.tenancy import OwnedMixin


class Base(DeclarativeBase):
    """Declarative base for every ORM model.

    The class form (SQLAlchemy 2.0 style) rather than ``declarative_base()``:
    the mypy plugin only injects attribute types for ``Mapped[]`` annotations
    when the base subclasses ``DeclarativeBase``. With the legacy factory,
    ``Mapped[int]`` is silently ignored and every model attribute keeps the
    ``Column`` type.
    """


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid4().hex)
    username: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid4().hex)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Content(OwnedMixin, Base):
    """内容记录表"""

    __tablename__ = "contents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    style: Mapped[str] = mapped_column(String(50), nullable=False)
    keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(20), default="draft")
    version: Mapped[int | None] = mapped_column(Integer, default=1)
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    token_usage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


Index("ix_contents_created_at", Content.created_at)
Index("ix_contents_status", Content.status)
Index("ix_contents_content_type", Content.content_type)


class CalendarEvent(OwnedMixin, Base):
    """内容日历表"""

    __tablename__ = "calendar_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_id: Mapped[int] = mapped_column(Integer, ForeignKey("contents.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str | None] = mapped_column(String(20), default="planned")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)


Index("ix_calendar_events_scheduled_date", CalendarEvent.scheduled_date)


class ContentMetrics(OwnedMixin, Base):
    """内容效果表"""

    __tablename__ = "content_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_id: Mapped[int] = mapped_column(Integer, ForeignKey("contents.id"), nullable=False)
    platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    views: Mapped[int | None] = mapped_column(Integer, default=0)
    likes: Mapped[int | None] = mapped_column(Integer, default=0)
    comments: Mapped[int | None] = mapped_column(Integer, default=0)
    shares: Mapped[int | None] = mapped_column(Integer, default=0)
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)


class MediaAsset(OwnedMixin, Base):
    """Persisted uploaded or generated media tied to content."""

    __tablename__ = "media_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_id: Mapped[int] = mapped_column(Integer, ForeignKey("contents.id"), nullable=False)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="upload")
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sort_order: Mapped[int | None] = mapped_column(Integer, default=0)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    generation_params: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)


Index("ix_media_assets_content_created", MediaAsset.content_id, MediaAsset.created_at)


class PlatformPublication(OwnedMixin, Base):
    """Persisted publication requests sent to an external platform."""

    __tablename__ = "platform_publications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_id: Mapped[int] = mapped_column(Integer, ForeignKey("contents.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    publish_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    external_post_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    request_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


Index("ix_platform_publications_content_status", PlatformPublication.content_id, PlatformPublication.status)
Index("ix_platform_publications_platform_created", PlatformPublication.platform, PlatformPublication.created_at)


class AgentThread(OwnedMixin, Base):
    """Persisted Agent chat thread."""

    __tablename__ = "agent_threads"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    title_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


Index("ix_agent_threads_updated_at", AgentThread.updated_at)
Index("ix_agent_threads_pinned_updated", AgentThread.pinned, AgentThread.updated_at)
Index("ix_agent_threads_archived", AgentThread.archived)


class AgentMessage(OwnedMixin, Base):
    """Persisted Agent chat message."""

    __tablename__ = "agent_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(80), ForeignKey("agent_threads.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    intent: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_events: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(20), default="completed")
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)


Index("ix_agent_messages_thread_created", AgentMessage.thread_id, AgentMessage.created_at)


class Job(OwnedMixin, Base):
    """Persisted background job state."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    job_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    progress: Mapped[int | None] = mapped_column(Integer, default=0)
    attempts: Mapped[int | None] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    # P1-04 lease: exactly one worker owns a running job. A SIGKILLed worker
    # never releases its lease, so recovery keys off an expired lease_expires_at
    # rather than any explicit signal from the dead process.
    worker_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    token_usage: Mapped[int | None] = mapped_column(Integer, default=0)
    cost_estimate: Mapped[float | None] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


Index("ix_jobs_status_created", Job.status, Job.created_at)
Index("ix_jobs_provider_status", Job.provider, Job.status)
Index("ix_jobs_lease_expires_at", Job.status, Job.lease_expires_at)


class RunStep(OwnedMixin, Base):
    """Durable per-step checkpoint so a retry resumes instead of restarting.

    Without this, a job that dies after step 3 of 5 replays steps 1-3 on retry
    and repeats whatever side effects those steps already committed.
    ``UNIQUE(run_id, step_index)`` makes the checkpoint write itself idempotent,
    so a crash between a step's own commit and its checkpoint write cannot
    produce two rows for the same step.
    """

    __tablename__ = "run_steps"
    __table_args__ = (UniqueConstraint("run_id", "step_index", name="uq_run_steps_run_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(80), nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    step_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    result_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


Index("ix_run_steps_run_status", RunStep.run_id, RunStep.status)


class AgentRun(OwnedMixin, Base):
    """Dynamic-pipeline run record."""

    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    thread_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    style: Mapped[str] = mapped_column(String(50), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    plan_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision_count: Mapped[int | None] = mapped_column(Integer, default=0)
    total_prompt_tokens: Mapped[int | None] = mapped_column(Integer, default=0)
    total_completion_tokens: Mapped[int | None] = mapped_column(Integer, default=0)
    total_cost: Mapped[float | None] = mapped_column(Float, default=0.0)
    saved_content_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(String(20), default="running")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_event_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


Index("ix_agent_runs_thread_created", AgentRun.thread_id, AgentRun.created_at)


class AgentRunEvent(OwnedMixin, Base):
    """Append-only event log for a pipeline run; SSE bridge reads this table."""

    __tablename__ = "agent_run_events"
    __table_args__ = (UniqueConstraint("run_id", "seq", name="uq_agent_run_events_run_seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(80), ForeignKey("agent_runs.id"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)


Index("ix_agent_run_events_run_seq", AgentRunEvent.run_id, AgentRunEvent.seq)


class ProposedAction(OwnedMixin, Base):
    """Durable one-time capability for a model-proposed write.

    A write tool is never authorized by model text. The executor persists the
    exact proposed call here, a later standalone user confirmation moves the row
    to ``confirmed``, and the executor atomically moves it to ``consumed`` before
    invoking the tool. ``args_hash`` makes the confirmed arguments tamper-evident
    across requests, and the status transition is the once-only guarantee.
    """

    __tablename__ = "proposed_actions"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(80), ForeignKey("agent_threads.id"), nullable=False)
    requester: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tool_name: Mapped[str] = mapped_column(String(80), nullable=False)
    args_json: Mapped[str] = mapped_column(Text, nullable=False)
    args_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    impact_summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="proposed")
    proposing_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    consuming_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


Index("ix_proposed_actions_thread_created", ProposedAction.thread_id, ProposedAction.created_at)
Index("ix_proposed_actions_status_expires", ProposedAction.status, ProposedAction.expires_at)


PROPOSED_ACTION_STATUSES = ("proposed", "confirmed", "consumed", "cancelled", "expired")


class IdempotencyRecord(OwnedMixin, Base):
    """Durable ledger making a keyed write replayable instead of repeatable.

    One logical request can span several statements and tables: a refine is an
    insert plus an update, a schedule commit is N calendar rows. Uniqueness
    therefore lives here rather than on the business columns of those tables. A
    unique constraint on, say, ``calendar_events(content_id, platform,
    scheduled_date)`` would reject legitimate repeats (an intentional same-day
    repost, a retry of a failed publish job) and turn recoverable errors into
    ``IntegrityError``.

    ``user_id`` and ``scope`` isolate keys between users and operations.
    ``result_json`` lets a retry return the same result rather than repeat work.
    """

    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("user_id", "scope", "idempotency_key", name="uq_idempotency_records_user_scope_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope: Mapped[str] = mapped_column(String(60), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    args_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress")
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_request_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


Index("ix_idempotency_records_scope_created", IdempotencyRecord.scope, IdempotencyRecord.created_at)


IDEMPOTENCY_RECORD_STATUSES = ("in_progress", "completed", "failed")
