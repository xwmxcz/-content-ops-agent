"""Persist accounts and isolate all business records in user workspaces.

Existing rows are preserved in a disabled legacy account. Registration never
claims this workspace; an explicit operator command transfers it after login
credentials have been established.
"""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0009_user_workspaces"
down_revision = "0008_job_lease_and_checkpoints"
branch_labels = None
depends_on = None

LEGACY_USER_ID = "00000000000000000000000000000001"
OWNED_TABLES = (
    "contents", "calendar_events", "content_metrics", "media_assets",
    "platform_publications", "agent_threads", "agent_messages", "jobs",
    "run_steps", "agent_runs", "agent_run_events", "proposed_actions",
    "idempotency_records",
)


def upgrade():
    users = op.create_table(
        "users",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("username", sa.String(32), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_table(
        "auth_rate_limits",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
    )
    op.bulk_insert(users, [{
        "id": LEGACY_USER_ID,
        "username": "__legacy_workspace__",
        "password_hash": "!",
        "is_active": False,
        "created_at": datetime.now(timezone.utc),
    }])
    for name in OWNED_TABLES:
        op.add_column(name, sa.Column("user_id", sa.String(32), nullable=True))
        table = sa.table(name, sa.column("user_id", sa.String(32)))
        op.execute(table.update().values(user_id=LEGACY_USER_ID))
        op.alter_column(name, "user_id", existing_type=sa.String(32), nullable=False)
        op.create_foreign_key(f"fk_{name}_user_id", name, "users", ["user_id"], ["id"])
        op.create_index(f"ix_{name}_user_id", name, ["user_id"])
    op.drop_constraint("uq_idempotency_records_scope_key", "idempotency_records", type_="unique")
    op.create_unique_constraint(
        "uq_idempotency_records_user_scope_key", "idempotency_records",
        ["user_id", "scope", "idempotency_key"],
    )


def downgrade():
    # A shared-workspace downgrade could expose private records and collide on
    # identical per-user keys. Stop before changing anything once users exist.
    connection = op.get_bind()
    if connection.execute(sa.text(
        "SELECT 1 FROM users WHERE id != :legacy LIMIT 1"
    ), {"legacy": LEGACY_USER_ID}).first():
        raise RuntimeError("Workspace downgrade requires removing user accounts and their data first")
    op.drop_constraint("uq_idempotency_records_user_scope_key", "idempotency_records", type_="unique")
    op.create_unique_constraint(
        "uq_idempotency_records_scope_key", "idempotency_records", ["scope", "idempotency_key"],
    )
    for name in reversed(OWNED_TABLES):
        op.drop_index(f"ix_{name}_user_id", table_name=name)
        op.drop_constraint(f"fk_{name}_user_id", name, type_="foreignkey")
        op.drop_column(name, "user_id")
    op.drop_table("auth_rate_limits")
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("users")
