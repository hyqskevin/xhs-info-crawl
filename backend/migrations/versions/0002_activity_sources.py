"""Add activity source note and image indexes."""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("activities") as batch:
        batch.add_column(sa.Column("note_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("source_image_indexes", sa.JSON(), nullable=False, server_default="[]"))
        batch.create_index("ix_activities_note_id", ["note_id"])


def downgrade():
    with op.batch_alter_table("activities") as batch:
        batch.drop_index("ix_activities_note_id")
        batch.drop_column("source_image_indexes")
        batch.drop_column("note_id")
