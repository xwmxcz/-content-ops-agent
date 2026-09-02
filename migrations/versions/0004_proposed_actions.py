"""Durable one-time write capabilities for confirmed Chat actions.

Phase 0 authorized writes from request-local evidence reconstructed out of the
previous assistant message, so a capability had no durable identity, no expiry,
and no record of having been used. This revision adds the table that makes a
confirmed action consumable exactly once across requests and processes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_proposed_actions"
down_revision: Union[str, None] = "0003_legacy_normalize"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "proposed_actions",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("thread_id", sa.String(80), nullable=False),
        sa.Column("requester", sa.String(120), nullable=True),
        sa.Column("tool_name", sa.String(80), nullable=False),
        sa.Column("args_json", sa.Text(), nullable=False),
        sa.Column("args_hash", sa.String(64), nullable=False),
        sa.Column("impact_summary", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="proposed"),
        sa.Column("proposing_message_id", sa.Integer(), nullable=True),
        sa.Column("consuming_message_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["thread_id"], ["agent_threads.id"]),
    )
    op.create_index(
        "ix_proposed_actions_thread_created",
        "proposed_actions",
        ["thread_id", "created_at"],
    )
    op.create_index(
        "ix_proposed_actions_status_expires",
        "proposed_actions",
        ["status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_proposed_actions_status_expires", table_name="proposed_actions")
    op.drop_index("ix_proposed_actions_thread_created", table_name="proposed_actions")
    op.drop_table("proposed_actions")
