"""Baseline for the pre-Alembic Content Ops schema.

Existing installations must verify their schema and stamp this revision before
upgrading to later revisions. Fresh databases run this revision normally.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("style", sa.String(50), nullable=False),
        sa.Column("keywords", sa.Text(), nullable=True),
        sa.Column("tags", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("llm_provider", sa.String(50), nullable=True),
        sa.Column("model_name", sa.String(100), nullable=True),
        sa.Column("token_usage", sa.Integer(), nullable=True),
        sa.Column("cost_estimate", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_contents_created_at", "contents", ["created_at"])
    op.create_index("ix_contents_status", "contents", ["status"])
    op.create_index("ix_contents_content_type", "contents", ["content_type"])

    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content_id", sa.Integer(), sa.ForeignKey("contents.id"), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_calendar_events_scheduled_date", "calendar_events", ["scheduled_date"])

    op.create_table(
        "content_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content_id", sa.Integer(), sa.ForeignKey("contents.id"), nullable=False),
        sa.Column("platform", sa.String(50), nullable=True),
        sa.Column("views", sa.Integer(), nullable=True),
        sa.Column("likes", sa.Integer(), nullable=True),
        sa.Column("comments", sa.Integer(), nullable=True),
        sa.Column("shares", sa.Integer(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "media_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content_id", sa.Integer(), sa.ForeignKey("contents.id"), nullable=False),
        sa.Column("media_type", sa.String(20), nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(80), nullable=True),
        sa.Column("generation_params", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_media_assets_content_created", "media_assets", ["content_id", "created_at"])

    op.create_table(
        "platform_publications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content_id", sa.Integer(), sa.ForeignKey("contents.id"), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("publish_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("external_post_id", sa.String(120), nullable=True),
        sa.Column("request_payload", sa.Text(), nullable=True),
        sa.Column("response_payload", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_platform_publications_content_status", "platform_publications", ["content_id", "status"])
    op.create_index("ix_platform_publications_platform_created", "platform_publications", ["platform", "created_at"])

    op.create_table(
        "agent_threads",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("last_provider", sa.String(50), nullable=True),
        sa.Column("last_model", sa.String(200), nullable=True),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("title_pinned", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_agent_threads_updated_at", "agent_threads", ["updated_at"])
    op.create_index("ix_agent_threads_pinned_updated", "agent_threads", ["pinned", "updated_at"])
    op.create_index("ix_agent_threads_archived", "agent_threads", ["archived"])

    op.create_table(
        "agent_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("thread_id", sa.String(80), sa.ForeignKey("agent_threads.id"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("model", sa.String(200), nullable=True),
        sa.Column("intent", sa.Text(), nullable=True),
        sa.Column("tool_events", sa.Text(), nullable=True),
        sa.Column("plan", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_agent_messages_thread_created", "agent_messages", ["thread_id", "created_at"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("job_type", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("model", sa.String(200), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=True),
        sa.Column("token_usage", sa.Integer(), nullable=True),
        sa.Column("cost_estimate", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_jobs_status_created", "jobs", ["status", "created_at"])
    op.create_index("ix_jobs_provider_status", "jobs", ["provider", "status"])

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("thread_id", sa.String(80), nullable=True),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("style", sa.String(50), nullable=False),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("model", sa.String(200), nullable=True),
        sa.Column("plan_json", sa.Text(), nullable=True),
        sa.Column("revision_count", sa.Integer(), nullable=True),
        sa.Column("total_prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("total_completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_cost", sa.Float(), nullable=True),
        sa.Column("saved_content_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_agent_runs_thread_created", "agent_runs", ["thread_id", "created_at"])

    op.create_table(
        "agent_run_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(80), sa.ForeignKey("agent_runs.id"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_agent_run_events_run_seq", "agent_run_events", ["run_id", "seq"])


def downgrade() -> None:
    op.drop_index("ix_agent_run_events_run_seq", table_name="agent_run_events")
    op.drop_table("agent_run_events")
    op.drop_index("ix_agent_runs_thread_created", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index("ix_jobs_provider_status", table_name="jobs")
    op.drop_index("ix_jobs_status_created", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_agent_messages_thread_created", table_name="agent_messages")
    op.drop_table("agent_messages")
    op.drop_index("ix_agent_threads_archived", table_name="agent_threads")
    op.drop_index("ix_agent_threads_pinned_updated", table_name="agent_threads")
    op.drop_index("ix_agent_threads_updated_at", table_name="agent_threads")
    op.drop_table("agent_threads")
    op.drop_index("ix_platform_publications_platform_created", table_name="platform_publications")
    op.drop_index("ix_platform_publications_content_status", table_name="platform_publications")
    op.drop_table("platform_publications")
    op.drop_index("ix_media_assets_content_created", table_name="media_assets")
    op.drop_table("media_assets")
    op.drop_table("content_metrics")
    op.drop_index("ix_calendar_events_scheduled_date", table_name="calendar_events")
    op.drop_table("calendar_events")
    op.drop_index("ix_contents_content_type", table_name="contents")
    op.drop_index("ix_contents_status", table_name="contents")
    op.drop_index("ix_contents_created_at", table_name="contents")
    op.drop_table("contents")
