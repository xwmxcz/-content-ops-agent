"""add job lease fields and run_steps checkpoints

Revision ID: 0008_job_lease_and_checkpoints
Revises: 0007_job_archived_at
Create Date: 2025-01-13 12:00:00.000000

P1-04 durability pair:

* Lease columns on ``jobs`` let exactly one worker own a running job. A worker
  that is SIGKILLed cannot release its lease, so the row is only recoverable by
  observing an expired ``lease_expires_at`` — hence the index on it.
* ``run_steps`` persists per-step results so a retry resumes after the last
  completed step instead of re-running side effects that already committed.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0008_job_lease_and_checkpoints'
down_revision = '0007_job_archived_at'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('jobs', sa.Column('worker_id', sa.String(255), nullable=True))
    op.add_column('jobs', sa.Column('lease_expires_at', sa.DateTime(), nullable=True))
    op.add_column('jobs', sa.Column('heartbeat_at', sa.DateTime(), nullable=True))
    # The reaper sweeps by (status, lease_expires_at); without this index the
    # sweep degrades to a full scan and gets skipped under load.
    op.create_index('ix_jobs_lease_expires_at', 'jobs', ['status', 'lease_expires_at'])

    op.create_table(
        'run_steps',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('run_id', sa.String(80), nullable=False),
        sa.Column('step_index', sa.Integer(), nullable=False),
        sa.Column('step_name', sa.String(255), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('result_data', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('run_id', 'step_index', name='uq_run_steps_run_index'),
    )
    # Resume lookups filter by run_id + status, not by step_index, so the
    # unique constraint's own index does not serve them.
    op.create_index('ix_run_steps_run_status', 'run_steps', ['run_id', 'status'])


def downgrade():
    op.drop_index('ix_run_steps_run_status', table_name='run_steps')
    op.drop_table('run_steps')
    op.drop_index('ix_jobs_lease_expires_at', table_name='jobs')
    op.drop_column('jobs', 'heartbeat_at')
    op.drop_column('jobs', 'lease_expires_at')
    op.drop_column('jobs', 'worker_id')
