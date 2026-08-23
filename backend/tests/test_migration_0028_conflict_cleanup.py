"""0028_crawl_tasks_unique_active_per_schedule migration 测试：

1. 无冲突数据时,0028 升级 no-op
2. 同 schedule 同 alive-status 重复 → id 较大的强制 FAILED,id 最小保留
3. manual/mixed 类型冲突不清理(只 scheduled 冲突才清理)
4. 已 COMPLETED/FAILED 的旧 task 即使同 schedule 也保留(不在 alive set 里)
5. **关键回归** —— sqlite3 stdlib driver 不会因为 current_timestamp 类型 tag 报错

策略:subprocess 跑 alembic upgrade head(从 0027 → 0028)在临时 sqlite 上,
不污染项目内 data/app/db。
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

ENV_BASE = {
    **dict(os.environ),
    "SECRET_KEY": "pytest-only-jwt-secret-at-least-32-bytes",
    "CELERY_BROKER_URL": "memory://",
}


def _alembic_upgrade(db_path: Path, target: str = "head") -> None:
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
    _alembic_upgrade(db_path, "0027")


def _insert_crawl_task(
    conn: sqlite3.Connection,
    *,
    status: str,
    type_: str = "scheduled",
    schedule_id: int | None = None,
    error_message: str | None = None,
) -> int:
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
# Test 1
# ──────────────────────────────────────────────────────────────────────


def test_upgrade_0028_no_op_when_no_duplicates(tmp_path: Path) -> None:
    db_path = tmp_path / "0028_noop.db"
    _bootstrap_to_0027(db_path)

    conn = _connect(db_path)
    try:
        _insert_crawl_task(conn, status="PENDING", schedule_id=1)
        _insert_crawl_task(conn, status="COMPLETED", schedule_id=1)
        _insert_crawl_task(conn, status="PENDING", schedule_id=2)
    finally:
        conn.close()

    _alembic_upgrade(db_path, "head")

    conn = _connect(db_path)
    try:
        assert _alembic_version(conn) == "0028"
        assert _index_exists(conn, "ux_crawl_tasks_active_per_schedule")
        statuses = sorted(
            row["status"] for row in conn.execute("SELECT status FROM crawl_tasks").fetchall()
        )
        assert statuses == ["COMPLETED", "PENDING", "PENDING"]
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────
# Test 2
# ──────────────────────────────────────────────────────────────────────


def test_upgrade_0028_marks_duplicates_failed(tmp_path: Path) -> None:
    db_path = tmp_path / "0028_dups.db"
    _bootstrap_to_0027(db_path)

    conn = _connect(db_path)
    try:
        keep_id = _insert_crawl_task(conn, status="PENDING", schedule_id=10)
        dupe_1 = _insert_crawl_task(conn, status="RUNNING", schedule_id=10)
        dupe_2 = _insert_crawl_task(conn, status="PAUSED", schedule_id=10)
        _insert_crawl_task(conn, status="PENDING", schedule_id=99)
    finally:
        conn.close()

    _alembic_upgrade(db_path, "head")

    conn = _connect(db_path)
    try:
        assert _alembic_version(conn) == "0028"
        rows = {
            row["id"]: row
            for row in conn.execute(
                "SELECT id, status, error_message, finished_at FROM crawl_tasks"
            ).fetchall()
        }
        assert rows[keep_id]["status"] == "PENDING"
        assert rows[keep_id]["error_message"] is None
        assert rows[keep_id]["finished_at"] is None
        for dupe_id in (dupe_1, dupe_2):
            assert rows[dupe_id]["status"] == "FAILED"
            assert "0028" in (rows[dupe_id]["error_message"] or "")
            assert rows[dupe_id]["finished_at"] is not None
        assert rows[max(rows.keys())]["status"] == "PENDING"
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────
# Test 3
# ──────────────────────────────────────────────────────────────────────


def test_upgrade_0028_ignores_completed_and_manual_tasks(tmp_path: Path) -> None:
    db_path = tmp_path / "0028_ignore.db"
    _bootstrap_to_0027(db_path)

    conn = _connect(db_path)
    try:
        manual_a = _insert_crawl_task(conn, status="PENDING", type_="manual", schedule_id=1)
        manual_b = _insert_crawl_task(conn, status="RUNNING", type_="manual", schedule_id=1)
        manual_c = _insert_crawl_task(conn, status="PAUSED", type_="manual", schedule_id=1)
        done_a = _insert_crawl_task(
            conn, status="COMPLETED_WITH_ERRORS", schedule_id=3, error_message="旧快照 A"
        )
        done_b = _insert_crawl_task(conn, status="FAILED", schedule_id=3, error_message="旧快照 B")
        done_c = _insert_crawl_task(conn, status="STOPPED", schedule_id=3)
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
        for mid in (manual_a, manual_b, manual_c):
            assert rows[mid]["status"] != "FAILED", "manual 类型不应被 0028 清理"
            assert "0028" not in (rows[mid]["error_message"] or ""), "manual 不应被打 0028 标签"
        assert rows[done_a]["status"] == "COMPLETED_WITH_ERRORS"
        assert rows[done_a]["error_message"] == "旧快照 A"
        assert rows[done_b]["status"] == "FAILED"
        assert rows[done_b]["error_message"] == "旧快照 B"
        assert rows[done_c]["status"] == "STOPPED"
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────
# Test 4 (关键回归)
# ──────────────────────────────────────────────────────────────────────


def test_upgrade_0028_sqlite_timestamp_binding_does_not_raise(tmp_path: Path) -> None:
    db_path = tmp_path / "0028_sqlite_binding.db"
    _bootstrap_to_0027(db_path)

    conn = _connect(db_path)
    try:
        _insert_crawl_task(conn, status="PENDING", schedule_id=42)
        _insert_crawl_task(conn, status="RUNNING", schedule_id=42)
        _insert_crawl_task(conn, status="RUNNING", schedule_id=42)
        _insert_crawl_task(conn, status="PAUSED", schedule_id=42)
    finally:
        conn.close()

    _alembic_upgrade(db_path, "head")

    conn = _connect(db_path)
    try:
        assert _alembic_version(conn) == "0028"
        n_failed = conn.execute(
            "SELECT COUNT(*) FROM crawl_tasks "
            "WHERE error_message LIKE '%0028%' AND status='FAILED'"
        ).fetchone()[0]
        assert n_failed == 3, f"期望 3 条 FAILED,实际 {n_failed}"
        n_with_finished = conn.execute(
            "SELECT COUNT(*) FROM crawl_tasks WHERE finished_at IS NOT NULL"
        ).fetchone()[0]
        assert n_with_finished == 3, "finished_at 应已写入"
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────
# Test 5
# ──────────────────────────────────────────────────────────────────────


def test_init_database_with_duplicates_boots_cleanly(tmp_path: Path) -> None:
    db_path = tmp_path / "0028_init_e2e.db"
    _bootstrap_to_0027(db_path)

    conn = _connect(db_path)
    try:
        _insert_crawl_task(conn, status="PENDING", schedule_id=5)
        _insert_crawl_task(conn, status="RUNNING", schedule_id=5)
        _insert_crawl_task(conn, status="RUNNING", schedule_id=5)
    finally:
        conn.close()

    _alembic_upgrade(db_path, "head")

    conn = _connect(db_path)
    try:
        assert _alembic_version(conn) == "0028"
        n_failed = conn.execute(
            "SELECT COUNT(*) FROM crawl_tasks "
            "WHERE error_message LIKE '%0028%' AND status='FAILED'"
        ).fetchone()[0]
        assert n_failed == 2
    finally:
        conn.close()