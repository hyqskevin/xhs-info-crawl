"""add skipped crawl note progress"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("crawl_tasks", sa.Column("skipped_notes", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("crawl_tasks", "skipped_notes")
