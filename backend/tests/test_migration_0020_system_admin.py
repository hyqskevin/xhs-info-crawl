"""0020_system_admin migration 测试：建表 + 扩列 + seed 幂等 + 数据回填。

使用 subprocess 调 alembic upgrade head 在临时 sqlite 上跑完所有迁移，
然后再用 sqlite3 客户端断言结果。这样：
- 不需要 monkeypatch alembic.op.get_bind（避免与 alembic 内部 proxy 状态冲突）
- 真实复现 alembic 生产路径
- 不污染项目内 data/app.db

参见 `test_config_migration_blindspots.py` 的 subprocess 模式。
"""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

ENV_BASE = {
    **dict(os.environ),
    "SECRET_KEY": "pytest-only-jwt-secret-at-least-32-bytes",
    "CELERY_BROKER_URL": "memory://",
}


def _alembic_upgrade_head(db_path: Path, target_revision: str | None = None) -> None:
    """在指定 sqlite 上跑 alembic upgrade（默认 head；可指定 target）。"""
    target = target_revision if target_revision else "head"
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


def _fresh_db_with_admin(tmp_path: Path) -> Path:
    """跑完所有 migrations（含 0020_system_admin）后，临时库已包含 admin 用户 + 新 schema。"""
    db_path = tmp_path / "system_admin.db"
    _alembic_upgrade_head(db_path)
    return db_path


# ----------------------------------------------------------------------
# Test 1: 5 张表创建 + Administrators/Viewers/9 条 permission 码 seed
# ----------------------------------------------------------------------


def test_upgrade_creates_tables_and_seeds(tmp_path: Path) -> None:
    db_path = _fresh_db_with_admin(tmp_path)
    conn = _connect(db_path)
    try:
        # 5 张新表存在
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"groups", "permissions", "group_permissions", "user_groups", "audit_logs"}.issubset(tables)

        # Administrators 组是内置
        row = conn.execute(
            "SELECT id, name, is_builtin FROM groups WHERE name = 'Administrators'"
        ).fetchone()
        assert row is not None
        assert row["is_builtin"] == 1

        # Viewers 组存在
        row = conn.execute(
            "SELECT id, name, is_builtin FROM groups WHERE name = 'Viewers'"
        ).fetchone()
        assert row is not None
        assert row["is_builtin"] == 1

        # 9 条权限码种子
        codes = {
            row[0] for row in conn.execute("SELECT code FROM permissions").fetchall()
        }
        expected = {
            "users:manage", "users:read", "settings:write", "tasks:crawl",
            "notes:review", "reports:generate", "notes:edit",
            "activities:edit", "duplicates:resolve", "notes:delete",
        }
        assert expected.issubset(codes)
    finally:
        conn.close()


# ----------------------------------------------------------------------
# Test 2: role=admin 用户自动入 Administrators 组
# ----------------------------------------------------------------------


def test_existing_admin_auto_joined_administrators(tmp_path: Path) -> None:
    db_path = _fresh_db_with_admin(tmp_path)
    conn = _connect(db_path)
    try:
        admin_user = conn.execute(
            "SELECT id, username, role FROM users WHERE username = 'admin'"
        ).fetchone()
        assert admin_user is not None
        assert admin_user["role"] == "admin"

        admin_gid = conn.execute(
            "SELECT id FROM groups WHERE name = 'Administrators'"
        ).fetchone()["id"]

        membership = conn.execute(
            "SELECT user_id, group_id FROM user_groups WHERE user_id = ? AND group_id = ?",
            (admin_user["id"], admin_gid),
        ).fetchone()
        assert membership is not None, "role=admin 用户未自动加入 Administrators 组"
    finally:
        conn.close()


# ----------------------------------------------------------------------
# Test 3: 跑两次 upgrade 不重复 seed
# ----------------------------------------------------------------------


def test_upgrade_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "system_admin_idempotent.db"
    # 连跑两次 head
    _alembic_upgrade_head(db_path)
    _alembic_upgrade_head(db_path)

    conn = _connect(db_path)
    try:
        # Administrators 组不重复
        n = conn.execute(
            "SELECT COUNT(*) FROM groups WHERE name = 'Administrators'"
        ).fetchone()[0]
        assert n == 1, "Administrators 组不应被重复 seed"

        # 同一权限码不重复
        n = conn.execute(
            "SELECT COUNT(*) FROM permissions WHERE code = 'users:manage'"
        ).fetchone()[0]
        assert n == 1

        # admin 在 Administrators 里只出现 1 次
        admin_uid = conn.execute(
            "SELECT id FROM users WHERE username = 'admin'"
        ).fetchone()["id"]
        admin_gid = conn.execute(
            "SELECT id FROM groups WHERE name = 'Administrators'"
        ).fetchone()["id"]
        n = conn.execute(
            "SELECT COUNT(*) FROM user_groups WHERE user_id = ? AND group_id = ?",
            (admin_uid, admin_gid),
        ).fetchone()[0]
        assert n == 1, "admin 用户组关系不应重复"
    finally:
        conn.close()


# ----------------------------------------------------------------------
# Test 4: display_name / enabled 回填
# ----------------------------------------------------------------------


def test_display_name_backfilled_for_existing_users(tmp_path: Path) -> None:
    db_path = _fresh_db_with_admin(tmp_path)
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT username, display_name, enabled FROM users WHERE username = 'admin'"
        ).fetchone()
        assert row is not None
        assert row["display_name"] == "admin"
        assert row["enabled"] == 1

        # users 表 schema 应包含 display_name + enabled 列
        cols = {
            row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        assert "display_name" in cols
        assert "enabled" in cols
    finally:
        conn.close()


# ----------------------------------------------------------------------
# Test 5: Administrators 组绑全部 9 条权限
# ----------------------------------------------------------------------


def test_administrators_group_has_all_9_permissions(tmp_path: Path) -> None:
    db_path = _fresh_db_with_admin(tmp_path)
    conn = _connect(db_path)
    try:
        admin_gid = conn.execute(
            "SELECT id FROM groups WHERE name = 'Administrators'"
        ).fetchone()["id"]

        bound_codes = {
            row[0]
            for row in conn.execute(
                "SELECT p.code FROM permissions p "
                "JOIN group_permissions gp ON gp.permission_id = p.id "
                "WHERE gp.group_id = ?",
                (admin_gid,),
            ).fetchall()
        }
        expected = {
            "users:manage", "users:read", "settings:write", "tasks:crawl",
            "notes:review", "reports:generate", "notes:edit",
            "activities:edit", "duplicates:resolve", "notes:delete",
        }
        assert expected.issubset(bound_codes)

        # Viewers 组只绑 users:read
        viewers_gid = conn.execute(
            "SELECT id FROM groups WHERE name = 'Viewers'"
        ).fetchone()["id"]
        viewer_codes = {
            row[0]
            for row in conn.execute(
                "SELECT p.code FROM permissions p "
                "JOIN group_permissions gp ON gp.permission_id = p.id "
                "WHERE gp.group_id = ?",
                (viewers_gid,),
            ).fetchall()
        }
        assert viewer_codes == {"users:read"}
    finally:
        conn.close()