"""Fence pipeline workers and make abandoned runs discoverable by the reaper."""

from alembic import op
import sqlalchemy as sa


revision = "0011_pipeline_run_leases"
down_revision = "0010_agent_run_request"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("worker_id", sa.String(200), nullable=True))
    op.add_column("agent_runs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_runs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_agent_runs_status_lease", "agent_runs", ["status", "lease_expires_at"])
    # Existing active runs get one deployment grace period. A lost pre-upgrade
    # worker must not leave a run outside the expiry scan forever.
    op.execute("UPDATE agent_runs SET lease_expires_at = CURRENT_TIMESTAMP + INTERVAL '5 minutes' WHERE status = 'running'")


def downgrade() -> None:
    op.drop_index("ix_agent_runs_status_lease", table_name="agent_runs")
    op.drop_column("agent_runs", "heartbeat_at")
    op.drop_column("agent_runs", "lease_expires_at")
    op.drop_column("agent_runs", "worker_id")
