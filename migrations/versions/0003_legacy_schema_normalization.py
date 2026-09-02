"""Normalize columns previously added by startup-time legacy DDL.

This revision is intentionally additive and idempotent so a verified legacy
schema stamped at 0001 receives every column expected by current ORM models.
Downgrade is a no-op because the migration cannot distinguish columns it added
from columns that already existed before Alembic adoption.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0003_legacy_normalize"
down_revision: Union[str, None] = "0002_atomic_run_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE agent_messages ADD COLUMN IF NOT EXISTS intent TEXT")
    op.execute("ALTER TABLE agent_messages ADD COLUMN IF NOT EXISTS plan TEXT")
    op.execute(
        "ALTER TABLE agent_threads ADD COLUMN IF NOT EXISTS "
        "pinned BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE agent_threads ADD COLUMN IF NOT EXISTS "
        "archived BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE agent_threads ADD COLUMN IF NOT EXISTS "
        "title_pinned BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS token_usage INTEGER DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS cost_estimate FLOAT DEFAULT 0"
    )

    # ``create_all()`` never added indexes to a table that already existed. A
    # pre-Alembic database could therefore have the legacy columns above but
    # still miss the indexes declared by the ORM. Keep adoption idempotent and
    # restore those read-path indexes after adding the columns.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_threads_updated_at "
        "ON agent_threads (updated_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_threads_pinned_updated "
        "ON agent_threads (pinned, updated_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_threads_archived "
        "ON agent_threads (archived)"
    )


def downgrade() -> None:
    # Additive legacy normalization is deliberately irreversible. Dropping a
    # pre-existing column would destroy data on databases that had it before
    # this revision.
    pass
