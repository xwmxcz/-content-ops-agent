"""Keep the request a pipeline run was started with.

A failed run can only be resumed if the run knows what it was asked to do. The
run row held the topic, platform and style, but not the length, keywords,
research sources or token limit, so a resume would have had to guess them.

The column is nullable: runs created before this revision have no stored
request and are simply not resumable.
"""
from alembic import op
import sqlalchemy as sa


revision = "0010_agent_run_request"
down_revision = "0009_user_workspaces"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("request_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runs", "request_json")
