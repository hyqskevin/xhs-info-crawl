"""把启动器自动生成的初始密码写到 data/run/INITIAL_ADMIN_PASSWORD.txt,供用户查阅。

关联 spec: docs/superpowers/specs/2026-08-16-launcher-password-visibility-design.md

为什么需要这个文件:
- v0.5.4 之前启动器在 INITIAL_ADMIN_PASSWORD 为空时自动生成 12 位随机密码
- 随机密码只写到了 .env,但用户在登录页看不到
- 现在额外写一份到 data/run/INITIAL_ADMIN_PASSWORD.txt,启动器 UI banner / Finder 双击都能找到
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


_PASSWORD_FILENAME = "INITIAL_ADMIN_PASSWORD.txt"


def record_initial_password(project_root: Path, password: str, auto_generated: bool) -> Path:
    """把密码写到 data/run/INITIAL_ADMIN_PASSWORD.txt,返回写入的文件路径。

    Args:
        project_root: 项目根目录(含 .env 和 data/)
        password: 要写入的密码
        auto_generated: 是否自动生成(True 时文件标记为「请登录后立即修改」)

    Returns:
        写入的文件绝对路径
    """
    run_dir = project_root / "data" / "run"
    run_dir.mkdir(parents=True, exist_ok=True)

    target = run_dir / _PASSWORD_FILENAME
    generated_at = datetime.now().isoformat(timespec="seconds")
    body = (
        f"# 小红书活动信息抓取系统 - 初始 admin 密码\n"
        f"# 生成时间: {generated_at}\n"
        f"# 类型: {'自动生成(请登录后立即修改)' if auto_generated else '用户配置'}\n"
        f"\n"
        f"username=admin\n"
        f"password={password}\n"
    )
    target.write_text(body, encoding="utf-8")
    logger.info(
        "已写入初始密码文件: %s%s",
        target,
        " (自动生成,登录后请修改)" if auto_generated else "",
    )
    return target