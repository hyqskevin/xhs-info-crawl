"""0026_schedule_circuit_breaker: 定时任务跨运行失败熔断字段

scheduled_crawls 增加连续失败熔断相关 4 列：
- consecutive_fail_limit    连续失败阈值（None=跟随全局 settings）
- retry_interval_minutes    熔断冷却后自动重启间隔分钟（None=跟随全局）
- consecutive_failures      当前连续失败次数
- cooldown_until            冷却截止时间(UTC)，到期后由 retry_failed_schedules 自动重启

关联 spec: docs/superpowers/specs/2026-08-19-schedule-circuit-breaker-retry-design.md
"""

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    col_names = {c["name"] for c in sa.inspect(bind).get_columns("scheduled_crawls")}
    if "consecutive_fail_limit" not in col_names:
        op.add_column("scheduled_crawls", sa.Column("consecutive_fail_limit", sa.Integer(), nullable=True))
    if "retry_interval_minutes" not in col_names:
        op.add_column("scheduled_crawls", sa.Column("retry_interval_minutes", sa.Integer(), nullable=True))
    if "consecutive_failures" not in col_names:
        op.add_column("scheduled_crawls", sa.Column("consecutive_failures", sa.Integer(), nullable=True))
    if "cooldown_until" not in col_names:
        op.add_column(
            "scheduled_crawls",
            sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    col_names = {c["name"] for c in sa.inspect(bind).get_columns("scheduled_crawls")}
    for col in ("cooldown_until", "consecutive_failures", "retry_interval_minutes", "consecutive_fail_limit"):
        if col in col_names:
            op.drop_column("scheduled_crawls", col)