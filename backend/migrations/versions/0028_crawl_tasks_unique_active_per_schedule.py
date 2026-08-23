"""0028_crawl_tasks_unique_active_per_schedule:

crawl_tasks 表新增 partial unique index:
- 同一 schedule 任意时刻最多挂 1 个 PENDING|RUNNING|STOP_REQUESTED|PAUSED 的 scheduled task
- manual / mixed 类型不受该索引约束(手动任务可并发)
- status NOT IN (活跃) 的旧任务不占用 unique(让已结束的 task 不冲突)

执行策略(SQLite partial unique index):
- 升级前先清理冲突的现场:同 schedule 已存在 ≥2 条 type='scheduled' AND status IN (alive) 的旧 task,
  把 id 较大的那批强制标记为 FAILED(保留 id 最小的那条继续)

关联 spec: docs/superpowers/specs/2026-08-22-schedule-unique-active-and-paused-restart-design.md §1
"""

from collections import defaultdict

import sqlalchemy as sa
from alembic import op


revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1. 清理冲突:同 schedule 同 alive-status 多于 1 条 → 把重复的强制标记 FAILED
    rows = bind.execute(
        sa.text(
            "SELECT id, json_extract(params, '$.schedule_id') AS sid, status "
            "FROM crawl_tasks "
            "WHERE json_extract(params, '$.type') = 'scheduled' "
            "AND status IN ('PENDING','RUNNING','STOP_REQUESTED','PAUSED') "
            "AND sid IS NOT NULL "
            "ORDER BY json_extract(params, '$.schedule_id'), id"
        )
    ).fetchall()

    seen: dict[int, int] = defaultdict(int)
    duplicate_ids: list[int] = []
    for row in rows:
        sid = int(row.sid)
        seen[sid] += 1
        if seen[sid] > 1:
            duplicate_ids.append(int(row.id))

    if duplicate_ids:
        bind.execute(
            sa.text(
                "UPDATE crawl_tasks SET status='FAILED', finished_at=:now, "
                "error_message='迁移 0028:旧现场同 schedule 重复活跃 task,强制 FAILED' "
                "WHERE id IN :ids"
            ).bindparams(sa.bindparam("ids", expanding=True)),
            {"now": sa.func.current_timestamp(), "ids": duplicate_ids},
        )

    # 2. 建 partial unique index
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_crawl_tasks_active_per_schedule "
        "ON crawl_tasks (json_extract(params, '$.schedule_id')) "
        "WHERE json_extract(params, '$.type') = 'scheduled' "
        "AND status IN ('PENDING','RUNNING','STOP_REQUESTED','PAUSED')"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_crawl_tasks_active_per_schedule")
