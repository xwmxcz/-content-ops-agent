"""Business idempotency ledger for keyed write operations.

P1-01 made a confirmed action consumable at most once, but a retry that reused
the same request identity had no way to return the original result: it either
wrote a second time or lost the outcome entirely. This revision adds the ledger
that makes a keyed write replayable.

Uniqueness is deliberately on ``(scope, idempotency_key)`` here and *not* on the
business columns of ``contents``, ``calendar_events``, or ``platform_publications``.
Every natural key on those tables falsely deduplicates a legitimate repeat:
regenerating the same topic, chained refinement with the default instruction, an
intentional same-day repost, and re-running a failed publish job are all normal.
``scope`` participates in the constraint so one key value reused across resource
families does not cross-deduplicate.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_idempotency_records"
down_revision: Union[str, None] = "0004_proposed_actions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope", sa.String(60), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("args_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="in_progress"),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("external_request_id", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("scope", "idempotency_key", name="uq_idempotency_records_scope_key"),
    )
    op.create_index(
        "ix_idempotency_records_scope_created",
        "idempotency_records",
        ["scope", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_idempotency_records_scope_created", table_name="idempotency_records")
    op.drop_table("idempotency_records")
