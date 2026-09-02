"""Make run event sequencing and terminal transitions database-safe."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_atomic_run_events"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("next_event_seq", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )

    # Old max(seq)+1 writers could create duplicate or gapped values. Normalize
    # deterministically before adding the database invariant. Existing SSE
    # clients should reconnect from zero during this maintenance migration.
    op.execute(
        """
        WITH ranked AS (
            SELECT id, row_number() OVER (PARTITION BY run_id ORDER BY seq, id) AS new_seq
            FROM agent_run_events
        )
        UPDATE agent_run_events AS event
        SET seq = ranked.new_seq::integer
        FROM ranked
        WHERE event.id = ranked.id
        """
    )
    op.execute(
        """
        UPDATE agent_runs AS run
        SET next_event_seq = COALESCE(events.max_seq, 0) + 1
        FROM (
            SELECT agent_runs.id AS run_id, MAX(agent_run_events.seq) AS max_seq
            FROM agent_runs
            LEFT JOIN agent_run_events ON agent_run_events.run_id = agent_runs.id
            GROUP BY agent_runs.id
        ) AS events
        WHERE run.id = events.run_id
        """
    )
    op.create_unique_constraint(
        "uq_agent_run_events_run_seq",
        "agent_run_events",
        ["run_id", "seq"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_agent_run_events_run_seq", "agent_run_events", type_="unique")
    op.drop_column("agent_runs", "next_event_seq")
