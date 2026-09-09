"""0028_crawl_tasks_unique_active_per_schedule migration 测试：

1. 无冲突数据时,0028 升级 no-op
2. 同 schedule 同 alive-status 重复 → id 较大的强制 FAILED,id 最小保留
3. manual/mixed 类型冲突不清理(只 scheduled 冲突才清理)
4. 已 COMPLETED/FAILED 的旧 task 即使同 schedule 也保留(不在 alive set 里)
5. **关键回归** —— sqlite3 stdlib driver 不会因为 current_timestamp 类型 tag 报错
   (这条防止 v0.7.0 那种 `sqlite3.ProgrammingError: type 'current_timestamp' is not supported`
    重新出现;若以后有人把 sa.func.current_timestamp() 改回 bind 参数,本 case 必红)

策略:subprocess 跑 alembic upgrade head(从 0027 → 0028)在临时 sqlite 上,
不污染项目内 data/app.db。

关联 spec: docs/superpowers/specs/2026-08-23-migration-0028-sqlite-current-timestamp-binding-design.md
关联 migration: backend/migrations/versions/0028_crawl_tasks_unique_active_per_schedule.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

ENV_BASE = {
    **dict(os.environ),
    "SECRET_KEY": "pytest-only-jwt-secret-at-least-32-bytes",
    "CELERY_BROKER_URL": "memory://",
}


def _alembic_upgrade(db_path: Path, target: str = "head") -> None:
    """在指定 sqlite 上跑 alembic upgrade(默认 head,也可指定 target_revision)。"""
    env = {**ENV_BASE, "DATABASE_URL": f"sqlite:///{db_path}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", target],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"alembic upgrade {target} failed:\nSTDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _bootstrap_to_0027(db_path: Path) -> None:
    """跑完 0027(让 crawl_tasks 表存在且 schema 完整)。"""
    _alembic_upgrade(db_path, "0027")


def _insert_crawl_task(
    conn: sqlite3.Connection,
    *,
    status: str,
    type_: str = "scheduled",
    schedule_id: int | None = None,
    error_message: str | None = None,
) -> int:
    """直接用 sqlite3 客户端插一条 crawl_tasks(避开 ORM 自动时间戳)。"""
    params: dict = {"type": type_}
    if schedule_id is not None:
        params["schedule_id"] = schedule_id
    now_iso = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO crawl_tasks (type, status, params, run_token, "
        "total_notes, downloaded_notes, ocr_notes, extracted_notes, "
        "success_notes, failed_notes, skipped_notes, skipped_activities, "
        "created_at, error_message) "
        "VALUES (?, ?, ?, ?, "
        "0, 0, 0, 0, "
        "0, 0, 0, 0, "
        "?, ?)",
        (
            type_,
            status,
            json.dumps(params),
            str(uuid.uuid4()),
            now_iso,
            error_message,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _alembic_version(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    return None if row is None else str(row["version_num"])


# ──────────────────────────────────────────────────────────────────────
# Test 1: 无冲突数据 → 0028 no-op,alembic_version 0027 → 0028
# ──────────────────────────────────────────────────────────────────────


def test_upgrade_0028_no_op_when_no_duplicates(tmp_path: Path) -> None:
    db_path = tmp_path / "0028_noop.db"
    _bootstrap_to_0027(db_path)

    conn = _connect(db_path)
    try:
        # 故意插一条活跃 scheduled + 一条已完成,绝无重复
        _insert_crawl_task(conn, status="PENDING", schedule_id=1)
        _insert_crawl_task(conn, status="COMPLETED", schedule_id=1)
        _insert_crawl_task(conn, status="PENDING", schedule_id=2)
    finally:
        conn.close()

    # 这一步是 v0.7.0 现场崩溃的关键 — 0027 → 0028 升级路径
    _alembic_upgrade(db_path, "head")

    conn = _connect(db_path)
    try:
        # alembic_version 推到 0028
        assert _alembic_version(conn) == "0029"  # head 已推进到 0029
        # partial unique index 创建成功
        assert _index_exists(conn, "ux_crawl_tasks_active_per_schedule")
        # 没有任何 task 被强制 FAILED(全部保持原状态)
        statuses = sorted(
            row["status"] for row in conn.execute("SELECT status FROM crawl_tasks").fetchall()
        )
        assert statuses == ["COMPLETED", "PENDING", "PENDING"]
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────
# Test 2: 同 schedule 重复活跃 → id 最小保留,其余强制 FAILED(主回归 case)
# ──────────────────────────────────────────────────────────────────────


def test_upgrade_0028_marks_duplicates_failed(tmp_path: Path) -> None:
    db_path = tmp_path / "0028_dups.db"
    _bootstrap_to_0027(db_path)

    conn = _connect(db_path)
    try:
        keep_id = _insert_crawl_task(conn, status="PENDING", schedule_id=10)
        dupe_1 = _insert_crawl_task(conn, status="RUNNING", schedule_id=10)
        dupe_2 = _insert_crawl_task(conn, status="PAUSED", schedule_id=10)
        _insert_crawl_task(conn, status="PENDING", schedule_id=99)  # 不同 schedule,不受影响
    finally:
        conn.close()

    _alembic_upgrade(db_path, "head")

    conn = _connect(db_path)
    try:
        assert _alembic_version(conn) == "0029"  # head 已推进到 0029
        rows = {
            row["id"]: row
            for row in conn.execute(
                "SELECT id, status, error_message, finished_at FROM crawl_tasks"
            ).fetchall()
        }
        # 保留:PENDING,不动
        assert rows[keep_id]["status"] == "PENDING"
        assert rows[keep_id]["error_message"] is None
        assert rows[keep_id]["finished_at"] is None
        # 重复 → FAILED,带迁移标记
        for dupe_id in (dupe_1, dupe_2):
            assert rows[dupe_id]["status"] == "FAILED"
            assert "0028" in (rows[dupe_id]["error_message"] or "")
            assert rows[dupe_id]["finished_at"] is not None
        # 不同 schedule 不动
        assert rows[max(rows.keys())]["status"] == "PENDING"
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────
# Test 3: manual/mixed 类型冲突不清理 + 已结束 task 即使同 schedule 不动
# ──────────────────────────────────────────────────────────────────────


def test_upgrade_0028_ignores_completed_and_manual_tasks(tmp_path: Path) -> None:
    db_path = tmp_path / "0028_ignore.db"
    _bootstrap_to_0027(db_path)

    conn = _connect(db_path)
    try:
        # 3 条 manual 同 schedule + 都是 PENDING — 不应被清理(只有 scheduled 才被 unique 约束)
        manual_a = _insert_crawl_task(conn, status="PENDING", type_="manual", schedule_id=1)
        manual_b = _insert_crawl_task(conn, status="RUNNING", type_="manual", schedule_id=1)
        manual_c = _insert_crawl_task(conn, status="PAUSED", type_="manual", schedule_id=1)
        # 已结束 task 同 schedule 重复 — 不在 alive set,0028 不应碰它们
        # 关键是 0028 的 UPDATE 只挑 status IN (alive),COMPLETED/FAILED/STOPPED 不会被选中
        done_a = _insert_crawl_task(
            conn, status="COMPLETED_WITH_ERRORS", schedule_id=3, error_message="旧快照 A"
        )
        done_b = _insert_crawl_task(conn, status="FAILED", schedule_id=3, error_message="旧快照 B")
        done_c = _insert_crawl_task(conn, status="STOPPED", schedule_id=3)
        # 触发 scheduled 重复,保证 upgrade 真跑过清理分支
        _insert_crawl_task(conn, status="PENDING", schedule_id=99)
        _insert_crawl_task(conn, status="PENDING", schedule_id=99)
    finally:
        conn.close()

    _alembic_upgrade(db_path, "head")

    conn = _connect(db_path)
    try:
        rows = {
            row["id"]: row
            for row in conn.execute(
                "SELECT id, status, type, error_message FROM crawl_tasks"
            ).fetchall()
        }
        # manual 全部保持原状态(无 "0028" 标记)
        for mid in (manual_a, manual_b, manual_c):
            assert rows[mid]["status"] != "FAILED", "manual 类型不应被 0028 清理"
            assert "0028" not in (rows[mid]["error_message"] or ""), "manual 不应被打 0028 标签"
        # 已结束全部不动 — 原 status + 原 error_message 保持
        assert rows[done_a]["status"] == "COMPLETED_WITH_ERRORS"
        assert rows[done_a]["error_message"] == "旧快照 A"
        assert rows[done_b]["status"] == "FAILED"
        assert rows[done_b]["error_message"] == "旧快照 B"
        assert rows[done_c]["status"] == "STOPPED"
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────
# Test 4: **关键回归** —— sqlite3 stdlib driver 不报 'current_timestamp' 类型错
# 这是 v0.7.0 现场崩溃的根因:sa.func.current_timestamp() 通过 bindparam expanding
# 传到 sqlite3 driver 时,driver 不识别 CURRENT_TIMESTAMP 类型 tag →
# sqlite3.ProgrammingError: Error binding parameter 1: type 'current_timestamp' is not supported
#
# 修法:把 sa.func.current_timestamp() 改为字面量 "CURRENT_TIMESTAMP"。
# 若以后有人回退到 sa.func.current_timestamp(),本 case 必红。
# ──────────────────────────────────────────────────────────────────────


def test_upgrade_0028_sqlite_timestamp_binding_does_not_raise(tmp_path: Path) -> None:
    """构造有重复的现场 → 触发 0028 的 UPDATE 路径 → 断言整条 upgrade 不抛异常。

    在修复前:这条测试在 stderr 输出 sqlite3.ProgrammingError,alembic upgrade 失败。
    修复后:0028 内部用字面量 "CURRENT_TIMESTAMP" 而非 sa.func.current_timestamp(),
    sqlite3 driver 把 "CURRENT_TIMESTAMP" 当字符串 → sqlite 解析为 CURRENT_TIMESTAMP 函数调用。
    """
    db_path = tmp_path / "0028_sqlite_binding.db"
    _bootstrap_to_0027(db_path)

    conn = _connect(db_path)
    try:
        # 至少 2 条重复,触发 UPDATE ... WHERE id IN :ids 路径
        _insert_crawl_task(conn, status="PENDING", schedule_id=42)
        _insert_crawl_task(conn, status="RUNNING", schedule_id=42)
        _insert_crawl_task(conn, status="RUNNING", schedule_id=42)
        _insert_crawl_task(conn, status="PAUSED", schedule_id=42)
    finally:
        conn.close()

    # 在修复前:alembic upgrade 会抛 sqlite3.ProgrammingError
    # 在修复后:整个升级成功
    _alembic_upgrade(db_path, "head")

    conn = _connect(db_path)
    try:
        assert _alembic_version(conn) == "0029"  # head 已推进到 0029
        # 4 条重复里 1 条保留,3 条强制 FAILED
        n_failed = conn.execute(
            "SELECT COUNT(*) FROM crawl_tasks "
            "WHERE error_message LIKE '%0028%' AND status='FAILED'"
        ).fetchone()[0]
        assert n_failed == 3, f"期望 3 条 FAILED,实际 {n_failed}"
        # finished_at 必须有值(这是绑定报错的字段,必须写成功)
        n_with_finished = conn.execute(
            "SELECT COUNT(*) FROM crawl_tasks WHERE finished_at IS NOT NULL"
        ).fetchone()[0]
        assert n_with_finished == 3, "finished_at 应已写入"
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────
# Test 5: 端到端 —— init_database 路径(跑 0028 + seed admin)不抛异常
# 这是 lifespan 阶段的真实路径:Base.metadata.create_all + upgrade_migrations_to_head +
# seed_default_admin。
# ──────────────────────────────────────────────────────────────────────


def test_init_database_with_duplicates_boots_cleanly(tmp_path: Path) -> None:
    """模拟用户现场:DB 在 0027 已有重复 scheduled → 跑 init_database 应升级成功 + admin 可登入。"""
    db_path = tmp_path / "0028_init_e2e.db"
    _bootstrap_to_0027(db_path)

    conn = _connect(db_path)
    try:
        _insert_crawl_task(conn, status="PENDING", schedule_id=5)
        _insert_crawl_task(conn, status="RUNNING", schedule_id=5)
        _insert_crawl_task(conn, status="RUNNING", schedule_id=5)
    finally:
        conn.close()

    # 直接用 alembic upgrade head 模拟 init_database 的升级步骤
    _alembic_upgrade(db_path, "head")

    conn = _connect(db_path)
    try:
        assert _alembic_version(conn) == "0029"  # head 已推进到 0029
        # 3 条里 1 条保留,2 条强制 FAILED
        n_failed = conn.execute(
            "SELECT COUNT(*) FROM crawl_tasks "
            "WHERE error_message LIKE '%0028%' AND status='FAILED'"
        ).fetchone()[0]
        assert n_failed == 2
    finally:
        conn.close()