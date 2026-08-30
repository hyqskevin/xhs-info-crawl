"""数据目录迁移脚本（~/.xhs-info-crawl/ → ~/Library/Application Support/com.xhs-info-crawl.local/）的 TDD 测试。

关联 spec: docs/superpowers/specs/2026-08-24-migrate-data-dir-to-application-support-default-design.md

策略：把核心断言（不变量校验、rsync 包装、app-still-running 检测）抽到
`scripts/lib/data_dir_migration.py`，pytest 直接 import helper 跑断言。
shell 脚本 `scripts/migrate-data-dir-to-application-support.sh` 只是薄壳，
实际逻辑全在 helper 里，便于测试覆盖。
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

# 让 pytest 能 import scripts/lib/data_dir_migration.py
SCRIPTS_LIB = Path(__file__).resolve().parents[2] / "scripts" / "lib"
if str(SCRIPTS_LIB) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_LIB))

import data_dir_migration as ddm  # noqa: E402  # conftest.py 已注入 scripts/lib/ 到 sys.path


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture()
def fake_data_root(tmp_path: Path) -> Path:
    """准备一个完整的"假数据根目录"，含 DB + 各子目录 + .env。

    结构模仿 ~/.xhs-info-crawl/：
      app.db (SQLite,含 notes/xhs_accounts/scheduled_crawls/alembic_version)
      chrome-pool/xhs-account-1/  (含一些占位文件)
      archive/2026-07-16/foo.bin
      paddlex/official_models/bar.bin
      exports/empty.txt
      tmp/empty.txt
      logs/empty.txt
      celery/empty.txt
      run/empty.txt
      images/empty.txt
      .env (含 LLM_API_KEY 敏感信息,验证不被拷贝)
    """
    src = tmp_path / "src"
    src.mkdir()
    (src / "chrome-pool" / "xhs-account-1").mkdir(parents=True)
    (src / "chrome-pool" / "xhs-account-2").mkdir(parents=True)
    (src / "chrome-pool" / "xhs-account-1" / "Cookies").write_bytes(b"cookie-bytes")
    (src / "archive" / "2026-07-16").mkdir(parents=True)
    (src / "archive" / "2026-07-16" / "foo.bin").write_bytes(b"x" * 4096)
    (src / "paddlex" / "official_models").mkdir(parents=True)
    (src / "paddlex" / "official_models" / "bar.bin").write_bytes(b"y" * 1024)
    for empty_dir in ("exports", "tmp", "logs", "celery", "run", "images"):
        (src / empty_dir).mkdir()
        (src / empty_dir / "empty.txt").write_text("")
    (src / ".env").write_text("DATA_DIR=./data\nLLM_API_KEY=sk-secret-dont-copy\n")

    # 建 SQLite DB 含 alembic_version + 几张表
    db_path = src / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
    conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0028')")
    conn.execute(
        "CREATE TABLE notes (id INTEGER PRIMARY KEY, title VARCHAR(128), published_at DATETIME)"
    )
    for i in range(5):
        conn.execute(
            "INSERT INTO notes (id, title, published_at) VALUES (?, ?, '2026-08-01 10:00:00')",
            (i + 1, f"note-{i}"),
        )
    conn.execute(
        "CREATE TABLE xhs_accounts ("
        "id INTEGER PRIMARY KEY, name VARCHAR(64), session_name VARCHAR(64) NOT NULL UNIQUE)"
    )
    for i in range(3):
        conn.execute(
            "INSERT INTO xhs_accounts (id, name, session_name) VALUES (?, ?, ?)",
            (i + 1, f"acct-{i}", f"xhs-account-{i}"),
        )
    conn.execute(
        "CREATE TABLE scheduled_crawls ("
        "id INTEGER PRIMARY KEY, name VARCHAR(128), enabled BOOLEAN NOT NULL)"
    )
    for i in range(2):
        conn.execute(
            "INSERT INTO scheduled_crawls (id, name, enabled) VALUES (?, ?, 1)",
            (i + 1, f"sched-{i}"),
        )
    conn.commit()
    conn.close()
    return src


@pytest.fixture()
def dest_root(tmp_path: Path) -> Path:
    """目标目录的占位 fixture。"""
    dest = tmp_path / "dest"
    dest.mkdir()
    return dest


# ============================================================
# TDD:先用失败用例覆盖所有目标
# ============================================================


class TestDataDirMigrationCopy:
    """测试 copy_subdirs_except_env:rsync 复制 SRC → DEST,但排除 .env。"""

    def test_migration_copies_all_subdirs_except_env(
        self, fake_data_root: Path, dest_root: Path
    ) -> None:
        """迁移应复制 chrome-pool/archive/paddlex/exports 等子目录,但**不**复制 .env。"""
        ddm.copy_subdirs_except_env(fake_data_root, dest_root)

        # 子目录齐全
        for sub in (
            "chrome-pool/xhs-account-1",
            "chrome-pool/xhs-account-2",
            "archive/2026-07-16",
            "paddlex/official_models",
            "exports",
            "tmp",
            "logs",
            "celery",
            "run",
            "images",
            "app.db",
        ):
            assert (dest_root / sub).exists(), f"DEST 缺少 {sub}"

        # .env 不应被拷贝
        assert not (dest_root / ".env").exists(), ".env 不应被拷贝到 DEST"

        # Cookies 字节级一致
        assert (dest_root / "chrome-pool/xhs-account-1/Cookies").read_bytes() == b"cookie-bytes"

    def test_copy_replaces_existing_dest_subdir_atomically(
        self, fake_data_root: Path, dest_root: Path
    ) -> None:
        """第二次跑 copy_subdirs_except_env 应幂等（DEST 已有内容时不应丢文件）。"""
        ddm.copy_subdirs_except_env(fake_data_root, dest_root)
        # 在 DEST 改个文件,再跑一次,验证不被覆盖丢
        (dest_root / "exports" / "empty.txt").write_text("dirty")
        ddm.copy_subdirs_except_env(fake_data_root, dest_root)
        # exports/empty.txt 内容应是 SRC 的（覆盖回 ""）
        assert (dest_root / "exports" / "empty.txt").read_text() == ""


class TestDataDirMigrationValidation:
    """测试 validate_migration:6 道不变量校验。"""

    def test_migration_validates_db_row_counts(
        self, fake_data_root: Path, dest_root: Path
    ) -> None:
        """SRC DB notes=5/accounts=3 → DEST 必须也是 5/3,否则 MigrationValidationError。"""
        ddm.copy_subdirs_except_env(fake_data_root, dest_root)
        result = ddm.validate_migration(fake_data_root, dest_root)
        assert result.passed
        assert result.notes_count == 5
        assert result.accounts_count == 3
        assert result.schedules_count == 2
        assert result.alembic_version == "0028"

    def test_migration_validates_size_consistency(
        self, fake_data_root: Path, dest_root: Path
    ) -> None:
        """DEST 缺子目录(模拟 rsync 部分失败)→ 抛 MigrationValidationError,提示总大小不一致。"""
        ddm.copy_subdirs_except_env(fake_data_root, dest_root)
        # 删掉 DEST 一个子目录,模拟 rsync 失败
        import shutil

        shutil.rmtree(dest_root / "archive")
        with pytest.raises(ddm.MigrationValidationError) as exc_info:
            ddm.validate_migration(fake_data_root, dest_root)
        # 错误信息应包含"大小不一致"或具体 SRC/DEST 字节数
        err = str(exc_info.value)
        assert "大小" in err or "size" in err.lower()

    def test_migration_validates_db_count_mismatch(
        self, fake_data_root: Path, dest_root: Path
    ) -> None:
        """DEST DB 的 notes 行数 ≠ SRC(模拟复制过程中 DB 被改)→ 抛 MigrationValidationError。"""
        ddm.copy_subdirs_except_env(fake_data_root, dest_root)
        # 在 DEST DB 加一行 notes,制造行数不一致
        conn = sqlite3.connect(dest_root / "app.db")
        conn.execute(
            "INSERT INTO notes (id, title, published_at) VALUES (999, 'extra', '2026-08-01 10:00:00')"
        )
        conn.commit()
        conn.close()
        with pytest.raises(ddm.MigrationValidationError) as exc_info:
            ddm.validate_migration(fake_data_root, dest_root)
        assert "notes" in str(exc_info.value).lower()


class TestDataDirMigrationAppRunning:
    """测试 is_app_running + run_migration 在 app 在跑时拒绝执行。"""

    def test_migration_aborts_when_app_running(
        self, fake_data_root: Path, dest_root: Path
    ) -> None:
        """启一个命令行含 'uvicorn' 的 dummy 进程 → run_migration 抛 AppStillRunningError。"""
        # 用 ps -eo command,命令行包含 "uvicorn" 关键词才能被 is_app_running() 检出
        # 通过 argv 第一个元素是 'uvicorn' 来模拟
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            # 临时 monkey-patch is_app_running 让它强制返 True,避免依赖 ps 真实匹配
            import unittest.mock as mock

            with mock.patch.object(ddm, "is_app_running", return_value=True):
                with pytest.raises(ddm.AppStillRunningError):
                    ddm.run_migration(fake_data_root, dest_root)
                # rsync 未执行
                assert not (dest_root / "chrome-pool").exists()
        finally:
            proc.terminate()
            proc.wait(timeout=5)

    def test_is_app_running_detects_uvicorn_in_ps(self) -> None:
        """ps 命令行里含 'uvicorn' 时,is_app_running 应返 True。"""
        # 起一个命令行里替换 argv[0] 为 'uvicorn' 的 dummy 进程
        import unittest.mock as mock

        # 通过 patch _run_ps 返回固定列表测试
        fake_ps_output = (
            "  PID COMMAND\n"
            "  100 uvicorn app.main:app --port 8001\n"
            "  101 celery -A app.tasks worker\n"
        )
        with mock.patch.object(ddm.subprocess, "run") as mock_run:
            mock_run.return_value = mock.Mock(stdout=fake_ps_output, stderr="", returncode=0)
            assert ddm.is_app_running() is True


class TestDataDirMigrationRunEndToEnd:
    """测试 run_migration 完整流程。"""

    def test_run_migration_success_path(
        self, fake_data_root: Path, dest_root: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """完整流程:不变量校验全过 + 输出下一步指令。"""
        ddm.run_migration(fake_data_root, dest_root)
        out = capsys.readouterr().out
        assert "✓" in out or "迁移成功" in out
        assert "下一步" in out or "next" in out.lower()
        # DEST 含 chrome-pool 但不含 .env
        assert (dest_root / "chrome-pool").exists()
        assert not (dest_root / ".env").exists()

    def test_run_migration_rollback_dest_on_failure(
        self, fake_data_root: Path, dest_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """rsync 失败(模拟)→ 抛异常 + DEST 被回滚(rmtree)。"""
        # 让 copy_subdirs_except_env 跑完后,人为删 DEST 子目录
        original_copy = ddm.copy_subdirs_except_env

        def broken_copy(src, dest):
            original_copy(src, dest)
            import shutil

            shutil.rmtree(dest / "archive")  # 模拟 rsync 漏了 archive

        monkeypatch.setattr(ddm, "copy_subdirs_except_env", broken_copy)
        with pytest.raises(ddm.MigrationValidationError):
            ddm.run_migration(fake_data_root, dest_root)
        # DEST 整体被回滚
        assert not dest_root.exists() or not any(dest_root.iterdir())


class TestProjectInternalWrites:
    """验证 helper 自身无硬编码 /tmp / Path.home()（AGENTS.md 硬约束）。"""

    def test_helper_has_no_tmp_or_home_hardcode(self) -> None:
        """helper 源码的代码行(非注释/docstring)不能出现 /tmp / Path.home() / expanduser('~') / tempfile.gettempdir()。"""
        import re

        path = SCRIPTS_LIB.joinpath("data_dir_migration.py")
        text = path.read_text(encoding="utf-8")
        # 剔除 docstring(三引号)与注释(# 开头)后再检查
        code_lines = []
        in_docstring = False
        for line in text.splitlines():
            stripped = line.strip()
            if '"""' in stripped or "'''" in stripped:
                # 简单处理:单行 docstring
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    in_docstring = not in_docstring
                    continue
                # 进入/退出 docstring
                in_docstring = not in_docstring
                continue
            if in_docstring:
                continue
            if stripped.startswith("#"):
                continue
            code_lines.append(line)
        code_text = "\n".join(code_lines)
        assert "/tmp" not in code_text, "硬编码 /tmp 违反 AGENTS.md"
        assert "Path.home()" not in code_text, "硬编码 Path.home() 违反 AGENTS.md"
        assert "expanduser('~')" not in code_text, "硬编码 expanduser('~') 违反 AGENTS.md"
        assert "tempfile.gettempdir" not in code_text, "硬编码 tempfile.gettempdir() 违反 AGENTS.md"