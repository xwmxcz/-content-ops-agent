"""add job retry fields

Revision ID: 0006_job_retry_fields
Revises: 0005_idempotency_records
Create Date: 2025-01-03 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0006_job_retry_fields'
down_revision = '0005_idempotency_records'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('jobs', sa.Column('max_retries', sa.Integer(), nullable=False, server_default='5'))
    op.add_column('jobs', sa.Column('next_retry_at', sa.DateTime(), nullable=True))
    op.add_column('jobs', sa.Column('error_type', sa.String(20), nullable=True))


def downgrade():
    op.drop_column('jobs', 'error_type')
    op.drop_column('jobs', 'next_retry_at')
    op.drop_column('jobs', 'max_retries')
