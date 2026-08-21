"""0027_groups_min_engagement: 博主组 / 关键词组加最低点赞收藏阈值列

- blogger_groups: 新增 min_likes (Integer, default 0) + min_favorites (Integer, default 0)
- keyword_groups: 同上两列
- 不可空 + 默认 0 = 不过滤（与 spec §2 一致）

关联 spec: docs/superpowers/specs/2026-08-21-groups-min-engagement-design.md
"""
import sqlalchemy as sa
from alembic import op


revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def _existing_columns(bind, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    for table in ("blogger_groups", "keyword_groups"):
        cols = _existing_columns(bind, table)
        if "min_likes" not in cols:
            op.add_column(
                table,
                sa.Column("min_likes", sa.Integer(), nullable=False, server_default="0"),
            )
        if "min_favorites" not in cols:
            op.add_column(
                table,
                sa.Column("min_favorites", sa.Integer(), nullable=False, server_default="0"),
            )


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("blogger_groups", "keyword_groups"):
        cols = _existing_columns(bind, table)
        for col in ("min_favorites", "min_likes"):
            if col in cols:
                op.drop_column(table, col)