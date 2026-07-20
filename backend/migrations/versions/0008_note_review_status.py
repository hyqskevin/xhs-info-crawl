"""add note review state and merge target"""

import sqlalchemy as sa
from alembic import op


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("notes", sa.Column("review_status", sa.String(length=32), nullable=False, server_default="PENDING"))
    op.add_column("notes", sa.Column("merged_into_note_id", sa.Integer(), nullable=True))
    op.create_index("ix_notes_review_status", "notes", ["review_status"], unique=False)
    op.execute("UPDATE notes SET review_status='APPROVED' WHERE id NOT IN (SELECT DISTINCT note_id FROM activities WHERE status IN ('RAW','NEEDS_REVIEW'))")


def downgrade():
    op.drop_index("ix_notes_review_status", table_name="notes")
    op.drop_column("notes", "merged_into_note_id")
    op.drop_column("notes", "review_status")
