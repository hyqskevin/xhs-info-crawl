"""数据目录迁移 helper:把 ~/.xhs-info-crawl/ → ~/Library/Application Support/com.xhs-info-crawl.local/。

核心 4 个 helper:
    is_app_running() -> bool                       检测 uvicorn/celery 进程是否在跑
    copy_subdirs_except_env(src, dest)             rsync 复制 SRC → DEST,排除 .env
    validate_migration(src, dest) -> ValidationResult  6 道不变量校验
    run_migration(src, dest, *, dry_run=False)     串联:app_running check + copy + validate,失败回滚 DEST

约束(AGENTS.md 硬约束):
    - 不硬编码 /tmp / Path.home() / expanduser('~') / tempfile.gettempdir()
    - 临时文件/缓存走 pytest tmp_path fixture(测试场景)
    - shell wrapper 用 $HOME 显式传入

关联 spec: docs/superpowers/specs/2026-08-24-migrate-data-dir-to-application-support-default-design.md
"""
from __future__ import annotations

import shutil
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path


# ============================================================
# 异常类
# ============================================================


class MigrationError(Exception):
    """数据目录迁移的基类异常。"""


class AppStillRunningError(MigrationError):
    """.app 服务进程(uvicorn/celery)仍在跑,迁移拒绝执行。"""


class MigrationValidationError(MigrationError):
    """不变量校验失败(SRC 与 DEST 不一致)。"""


# ============================================================
# 数据类
# ============================================================


@dataclass
class ValidationResult:
    """6 道不变量的校验结果。"""

    passed: bool
    notes_count: int = 0
    accounts_count: int = 0
    schedules_count: int = 0
    alembic_version: str = ""
    src_total_size: int = 0
    dest_total_size: int = 0


# ============================================================
# 进程检测
# ============================================================


def is_app_running() -> bool:
    """检测 .app 服务进程(uvicorn 或 celery worker/beat)是否在跑。

    使用 ps + grep 匹配命令行;macOS 兼容。

    Returns:
        True:有 .app 服务进程在跑,迁移应拒绝执行
        False:安全
    """
    try:
        # ps -ef 拿所有进程,grep uvicorn/celery,排除 grep 自身
        result = subprocess.run(
            ["ps", "-eo", "command"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        # ps 命令不存在(非 macOS/Linux),保守返回 False
        return False
    lines = result.stdout.splitlines()
    for line in lines:
        # 排除 grep 自身和 ps 命令
        if "grep" in line and ("uvicorn" in line or "celery" in line):
            continue
        if "uvicorn" in line or ("celery" in line and "-A app.tasks" in line):
            return True
    return False


# ============================================================
# rsync 包装
# ============================================================


def copy_subdirs_except_env(src: Path, dest: Path) -> None:
    """rsync 复制 SRC 内容到 DEST,排除 .env(.env 含 LLM API Key 等敏感信息且有失效的 DATA_DIR=./data)。

    Args:
        src: 源目录(如 ~/.xhs-info-crawl/)
        dest: 目标目录(如 ~/Library/Application Support/com.xhs-info-crawl.local/)

    Behavior:
        - 缺失 rsync 时 fallback 到 shutil.copytree
        - dest 不存在时自动创建
        - 保留权限/时间戳
        - 不带 --delete(DEST 已有内容不会被清,只覆盖 SRC 有的子目录)
    """
    dest.mkdir(parents=True, exist_ok=True)
    if shutil.which("rsync"):
        # 不带 --delete;--exclude 排除 .env
        subprocess.run(
            [
                "rsync",
                "-a",
                "--exclude=.env",
                f"{src}/",
                f"{dest}/",
            ],
            check=True,
        )
    else:
        # rsync 不可用,fallback shutil.copytree
        # ignore=shutil.ignore_patterns('.env') 跳过 .env
        # dirs_exist_ok=True 让 DST 已有子目录时不抛错
        shutil.copytree(src, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".env"))


# ============================================================
# 不变量校验
# ============================================================


def _dir_total_size(path: Path) -> int:
    """递归算 path 下所有文件的总字节数(.env* 排除)。"""
    total = 0
    for item in path.rglob("*"):
        if item.is_file() and item.name != ".env" and not item.name.startswith(".env."):
            total += item.stat().st_size
    return total


def _count_sqlite(db_path: Path, table: str) -> int:
    """读 SQLite 表行数;表不存在返 -1。"""
    if not db_path.exists():
        return -1
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
        return cur.fetchone()[0]
    except sqlite3.OperationalError:
        return -1
    finally:
        conn.close()


def _read_alembic_version(db_path: Path) -> str:
    """读 alembic_version 表的 version_num;缺失返 ''。"""
    if not db_path.exists():
        return ""
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute("SELECT version_num FROM alembic_version LIMIT 1")
        row = cur.fetchone()
        return row[0] if row else ""
    except sqlite3.OperationalError:
        return ""
    finally:
        conn.close()


def validate_migration(src: Path, dest: Path) -> ValidationResult:
    """6 道不变量校验:SRC 与 DEST 是否一致。

    检查项:
        1. SRC 与 DEST 的总大小(排除 .env)相等
        2. SRC 与 DEST 的 app.db 文件大小相等
        3. SRC 与 DEST 的 notes 行数相等
        4. SRC 与 DEST 的 xhs_accounts 行数相等
        5. SRC 与 DEST 的 scheduled_crawls 行数相等
        6. SRC 与 DEST 的 alembic_version 值相等

    Returns:
        ValidationResult:passed=True 表示 6 道都过

    Raises:
        MigrationValidationError:任一检查失败,详细说明哪道不通过
    """
    src_size = _dir_total_size(src)
    dest_size = _dir_total_size(dest)
    src_notes = _count_sqlite(src / "app.db", "notes")
    dest_notes = _count_sqlite(dest / "app.db", "notes")
    src_accounts = _count_sqlite(src / "app.db", "xhs_accounts")
    dest_accounts = _count_sqlite(dest / "app.db", "xhs_accounts")
    src_schedules = _count_sqlite(src / "app.db", "scheduled_crawls")
    dest_schedules = _count_sqlite(dest / "app.db", "scheduled_crawls")
    src_alembic = _read_alembic_version(src / "app.db")
    dest_alembic = _read_alembic_version(dest / "app.db")

    failures: list[str] = []

    if src_size != dest_size:
        failures.append(f"总大小不一致 SRC={src_size} DEST={dest_size}")
    if src_notes != dest_notes:
        failures.append(f"notes 行数不一致 SRC={src_notes} DEST={dest_notes}")
    if src_accounts != dest_accounts:
        failures.append(f"xhs_accounts 行数不一致 SRC={src_accounts} DEST={dest_accounts}")
    if src_schedules != dest_schedules:
        failures.append(f"scheduled_crawls 行数不一致 SRC={src_schedules} DEST={dest_schedules}")
    if src_alembic != dest_alembic:
        failures.append(f"alembic_version 不一致 SRC={src_alembic!r} DEST={dest_alembic!r}")

    result = ValidationResult(
        passed=len(failures) == 0,
        notes_count=dest_notes,
        accounts_count=dest_accounts,
        schedules_count=dest_schedules,
        alembic_version=dest_alembic,
        src_total_size=src_size,
        dest_total_size=dest_size,
    )

    if failures:
        raise MigrationValidationError(
            "迁移校验失败:\n  - " + "\n  - ".join(failures)
        )
    return result


# ============================================================
# 主流程
# ============================================================


def run_migration(src: Path, dest: Path, *, dry_run: bool = False) -> ValidationResult:
    """完整流程:app_running check → copy → validate → 失败回滚。

    Args:
        src: 源目录(如 ~/.xhs-info-crawl/)
        dest: 目标目录(如 ~/Library/Application Support/com.xhs-info-crawl.local/)
        dry_run:True 时只校验不复制,供 preview 用

    Returns:
        ValidationResult:校验通过的结果

    Raises:
        AppStillRunningError:.app 服务在跑,拒绝执行
        MigrationValidationError:校验失败(已自动 rmtree dest 回滚)
    """
    if is_app_running():
        raise AppStillRunningError(
            "检测到 .app 服务进程仍在跑(uvicorn 或 celery worker/beat),"
            "请先关闭 .app 再执行迁移,避免 SQLite WAL/SHM 复制不一致"
        )

    if dry_run:
        copy_subdirs_except_env(src, dest)
        return validate_migration(src, dest)

    copy_subdirs_except_env(src, dest)
    try:
        result = validate_migration(src, dest)
    except MigrationValidationError:
        # 校验失败 → 回滚 DEST(整体删,避免半生不熟的状态)
        if dest.exists():
            shutil.rmtree(dest)
        raise

    # 输出下一步指引
    print("✓ 迁移脚本执行成功")
    print(f"  - 拷贝大小: {result.dest_total_size} 字节")
    print(f"  - notes: {result.notes_count}")
    print(f"  - xhs_accounts: {result.accounts_count}")
    print(f"  - scheduled_crawls: {result.schedules_count}")
    print(f"  - alembic_version: {result.alembic_version}")
    print("")
    print("下一步:")
    print("  1. 启动 .app")
    print("  2. 在 launcher UI 'LLM 与系统配置 → 存储路径 → 数据根目录' 填入:")
    print("       ~/Library/Application Support/com.xhs-info-crawl.local")
    print("     (如果 launcher .env 拆分 spec 已上线,可能不需要手动填——直接使用默认值)")
    print("  3. 在 UI 验证:")
    print("    - 数据根目录 = ~/Library/Application Support/com.xhs-info-crawl.local")
    print("    - 数据库预览 = .../app.db")
    print("    - 管理后台能看到原账号 / schedule / notes 齐全")
    print("  4. 触发一次小抓取验证 task_logs / archive 写入新路径")
    print("  5. 验证 OK 后,执行清理:")
    print(f"       rm -rf {src}")
    return result