"""Add archived_at field for job cleanup.

Revision ID: 0007
Revises: 0006
Create Date: 2025-01-15

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0007_job_archived_at'
down_revision = '0006_job_retry_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add archived_at column to jobs table for soft deletion."""
    op.add_column('jobs', sa.Column('archived_at', sa.TIMESTAMP(), nullable=True))
    op.create_index('ix_jobs_archived_at', 'jobs', ['archived_at'])


def downgrade() -> None:
    """Remove archived_at column."""
    op.drop_index('ix_jobs_archived_at', table_name='jobs')
    op.drop_column('jobs', 'archived_at')
