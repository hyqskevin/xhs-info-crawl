"""0029_unify_timestamps_to_cn: 全工程时间统一北京墙钟（东八区）。

两步：
1. 审计时间列：UTC 语义 → 北京墙钟 naive（naive +8h；带 offset/Z 的转 Asia/Shanghai 取 naive）
2. 业务列（notes.published_at / activities.start_time / end_time）：仅归一带 offset 的
   误存行（前端 toISOString 泄漏）→ 北京墙钟 naive；naive 视为已是北京墙钟，不动

安全网：执行前用 sqlite3 backup API 备份 DB 到同目录 backups/pre-0029-<ts>.db，
备份失败即中止迁移。downgrade 仅对称还原审计列（按北京墙钟 -8h 回 UTC 语义），
仅供误升级立即回退；业务列 offset 归一的行不可逆（backup 为最终兜底）。

注意：全新库（create_all 后表为空）迁移时无行可移，天然安全；
存量库的审计行均为旧 UTC 写侧产生，+8h 语义正确。

关联 spec: docs/superpowers/specs/2026-09-07-unify-beijing-timezone-design.md
"""
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

logger = logging.getLogger("migration.0029")

CN_TZ = ZoneInfo("Asia/Shanghai")

# (table, column) 审计列：UTC 语义 → 北京墙钟
_AUDIT_COLUMNS = [
    ("users", "created_at"), ("audit_logs", "created_at"),
    ("bloggers", "created_at"), ("cities", "created_at"),
    ("crawl_tasks", "created_at"), ("crawl_tasks", "started_at"), ("crawl_tasks", "finished_at"),
    ("task_logs", "created_at"),
    ("notes", "created_at"),
    ("activities", "created_at"), ("activities", "updated_at"), ("activities", "deleted_at"),
    ("duplicate_candidates", "created_at"), ("duplicate_candidates", "resolved_at"),
    ("note_duplicate_candidates", "created_at"), ("note_duplicate_candidates", "resolved_at"),
    ("xhs_accounts", "created_at"), ("xhs_accounts", "updated_at"),
    ("scheduled_crawls", "created_at"), ("scheduled_crawls", "updated_at"), ("scheduled_crawls", "cooldown_until"),
    ("search_usage", "updated_at"),
    ("weekly_reports", "created_at"), ("weekly_reports", "updated_at"),
    ("blogger_cities", "created_at"),
    ("blogger_groups", "created_at"), ("blogger_group_members", "created_at"),
    ("keyword_groups", "created_at"), ("keyword_group_cities", "created_at"), ("keyword_group_words", "created_at"),
    ("poster_templates", "created_at"), ("poster_templates", "updated_at"),
    ("poster_tasks", "created_at"), ("poster_tasks", "updated_at"),
    ("groups", "created_at"),
]

# 业务列：已是北京墙钟，只归一带 offset 的误存行
_BUSINESS_COLUMNS = [
    ("notes", "published_at"),
    ("activities", "start_time"), ("activities", "end_time"),
]


def _backup_database(bind) -> None:
    engine = bind.get_bind()
    db_path = Path(engine.url.database)
    if not db_path.is_file():
        raise RuntimeError(f"0029: DB 文件不存在 {db_path}，拒绝在无备份的情况下迁移")
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"pre-0029-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.db"
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(target))
    with dst:
        src.backup(dst)
    dst.close()
    src.close()
    logger.warning("0029: 已备份数据库到 %s", target)


def _parse(value: str):
    """解析存量时间字符串：naive 按 UTC +8h；带 offset/Z 转 Beijing naive；失败返回 None。"""
    text = value.strip()
    if not text:
        return None
    normalized = text.replace(" ", "T", 1)
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(CN_TZ).replace(tzinfo=None)
    return dt + timedelta(hours=8)


def _has_offset(raw: str) -> bool:
    return raw.endswith("Z") or raw.endswith("z") or "+" in raw or raw.rfind("-") > 9


def _shift_column(bind, table: str, column: str, skip_naive: bool = False) -> None:
    try:
        rows = bind.execute(
            sa.text(f"SELECT rowid, {column} FROM {table} WHERE {column} IS NOT NULL")
        ).fetchall()
    except sa.exc.OperationalError as exc:
        logger.warning("0029: 跳过 %s.%s（%s）", table, column, exc)
        return
    updated = 0
    for rowid, raw in rows:
        raw = str(raw)
        if skip_naive and not _has_offset(raw):
            continue
        converted = _parse(raw)
        if converted is None:
            logger.warning("0029: %s.%s rowid=%s 值 %r 无法解析，原样保留", table, column, rowid, raw)
            continue
        bind.execute(
            sa.text(f"UPDATE {table} SET {column} = :v WHERE rowid = :rid"),
            {"v": converted.isoformat(sep=" "), "rid": rowid},
        )
        updated += 1
    if updated:
        logger.warning("0029: %s.%s 已迁移 %d 行", table, column, updated)


def upgrade() -> None:
    bind = op.get_bind()
    _backup_database(bind)
    for table, column in _AUDIT_COLUMNS:
        _shift_column(bind, table, column)
    for table, column in _BUSINESS_COLUMNS:
        _shift_column(bind, table, column, skip_naive=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table, column in _AUDIT_COLUMNS:
        try:
            rows = bind.execute(
                sa.text(f"SELECT rowid, {column} FROM {table} WHERE {column} IS NOT NULL")
            ).fetchall()
        except sa.exc.OperationalError:
            continue
        for rowid, raw in rows:
            text = str(raw).strip().replace(" ", "T", 1)
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            try:
                dt = datetime.fromisoformat(text)
            except ValueError:
                continue
            # 升级后的审计列均为北京墙钟 naive → -8h 回 UTC 语义；
            # 仍带 offset 的行按真实 UTC 时刻取 naive（本就正确，仅去后缀）
            if dt.tzinfo is not None:
                restored = dt.astimezone(timezone.utc).replace(tzinfo=None)
            else:
                restored = dt - timedelta(hours=8)
            bind.execute(
                sa.text(f"UPDATE {table} SET {column} = :v WHERE rowid = :rid"),
                {"v": restored.isoformat(sep=" "), "rid": rowid},
            )
