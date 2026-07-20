"""add per-execution crawl run token"""

import sqlalchemy as sa
from alembic import op


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("crawl_tasks", sa.Column("run_token", sa.String(length=36), nullable=True))
    op.create_index("ix_crawl_tasks_run_token", "crawl_tasks", ["run_token"], unique=False)


def downgrade():
    op.drop_index("ix_crawl_tasks_run_token", table_name="crawl_tasks")
    op.drop_column("crawl_tasks", "run_token")
