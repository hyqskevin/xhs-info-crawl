"""launcher bootstrap_env 用户/系统 key 隔离测试(v0.7.0+9)。

背景:
- v0.7.0+6/+7 修复 DATA_DIR 路径,但引入新问题:launcher 把 .env.example
  整份复制到 .app/.env,含 SECRET_KEY / MINIMAX_API_KEY 等用户配置 key
- .app/.env 升级时被覆盖,用户对 .app/.env 的任何修改丢失
- 用户配置 key 应该走 DATA_DIR/.env(用户持久化主源),不写 .app/.env
- SECRET_KEY 由 launcher 显式生成,只写 DATA_DIR/.env

关联 spec: docs/superpowers/specs/2026-08-24-bootstrap-env-system-keys-only-design.md
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from launcher.env_bootstrap import (
    LAUNCHER_SYSTEM_KEYS,
    LAUNCHER_USER_KEYS,
    _read_env_value,
    ensure_data_dir_env,
    ensure_env_file,
    ensure_secret_key,
    update_env_value,
)


def _make_env_example(tmp_path: Path) -> Path:
    """构造一个含系统 + 用户两类 key 的 .env.example 用于测试。"""
    env_example = tmp_path / ".env.example"
    lines = [
        "# 系统级 key(应被复制到 .app/.env)",
        "API_HOST=127.0.0.1",
        "API_PORT=8000",
        "WEB_PORT=5173",
        "VITE_API_BASE_URL=/api/v1",
        "DATA_DIR=./data",
        "LOG_DIR=./logs",
        "# 用户配置 key(不应出现在 .app/.env)",
        "SECRET_KEY=replace-with-a-random-local-secret",
        "MINIMAX_API_KEY=sk-cp-example-llm-key",
        "OPENCLI_BIN=opencli",
        "INITIAL_ADMIN_PASSWORD=",
        "OCR_ENABLED=false",
    ]
    env_example.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return env_example


def test_first_copy_filters_to_system_keys_only(tmp_path: Path) -> None:
    """ensure_env_file 首次复制 .env.example 到 .app/.env 时,只复制白名单 key。

    修前: 整份复制,用户配置 key 全进 .app/.env
    修后: .app/.env 只含 LAUNCHER_SYSTEM_KEYS 内的 key
    """
    env_example = _make_env_example(tmp_path)
    env_path = tmp_path / ".app.env"  # 模拟 .app/.env

    ensure_env_file(env_path, env_example)

    content = env_path.read_text(encoding="utf-8")
    # 系统 key 应该在
    assert "API_PORT=8000" in content
    assert "VITE_API_BASE_URL=/api/v1" in content
    # 用户配置 key 不应该在
    assert "MINIMAX_API_KEY" not in content, ".app/.env 不应含 MINIMAX_API_KEY"
    assert "OPENCLI_BIN" not in content, ".app/.env 不应含 OPENCLI_BIN"
    assert "INITIAL_ADMIN_PASSWORD" not in content, ".app/.env 不应含 INITIAL_ADMIN_PASSWORD"
    assert "OCR_ENABLED" not in content, ".app/.env 不应含 OCR_ENABLED"
    # SECRET_KEY 也不应在(由 ensure_secret_key 单独写 DATA_DIR/.env)
    assert "SECRET_KEY" not in content, ".app/.env 不应含 SECRET_KEY"


def test_subsequent_bootstrap_does_not_write_user_keys(tmp_path: Path) -> None:
    """.app/.env 已存在且只含系统 key 时,ensure_env_file 不动它。

    修前: 不区分,任何路径都覆盖
    修后: 已存在 + 不含用户配置 key(新版本 launcher 生成的)→ 跳过
    """
    env_example = _make_env_example(tmp_path)
    env_path = tmp_path / ".app.env"
    # 模拟 v0.7.0+9 launcher 已经生成的 .app/.env:只含系统 key
    user_content = "# launcher 系统配置\nAPI_PORT=9999\nWEB_PORT=5173\n"
    env_path.write_text(user_content, encoding="utf-8")

    ensure_env_file(env_path, env_example)

    assert env_path.read_text(encoding="utf-8") == user_content, "已存在的纯系统 .app/.env 不应被覆盖"


def test_old_app_env_with_user_keys_is_backed_up_and_regenerated(tmp_path: Path) -> None:
    """老版本 .app/.env 含用户配置 key 时,launcher 备份后重生成。

    修前: .app/.env 不区分新老,升级 .app 后用户配置 key 继续污染
    修后: 检测到 SECRET_KEY / MINIMAX_API_KEY 等用户 key → 备份为 .env.v0.7.0.bak → 重生成
    """
    env_example = _make_env_example(tmp_path)
    env_path = tmp_path / ".app.env"
    # 模拟老版本 v0.7.0+8 的 .app/.env:含 SECRET_KEY / MINIMAX_API_KEY
    old_content = (
        "API_PORT=8000\n"
        "SECRET_KEY=old-leaked-secret\n"
        "MINIMAX_API_KEY=sk-cp-leaked\n"
        "DATA_DIR=./data\n"
    )
    env_path.write_text(old_content, encoding="utf-8")

    ensure_env_file(env_path, env_example)

    # 1. 备份文件存在
    backup = tmp_path / ".app.env.v0.7.0.bak"
    assert backup.exists(), "老 .app/.env 应备份为 .app.env.v0.7.0.bak"
    assert "SECRET_KEY=old-leaked-secret" in backup.read_text(encoding="utf-8")

    # 2. .app/.env 重生成,只含系统 key
    content = env_path.read_text(encoding="utf-8")
    assert "API_PORT=8000" in content, "系统 key 保留"
    assert "SECRET_KEY" not in content, "用户配置 SECRET_KEY 不应再出现"
    assert "MINIMAX_API_KEY" not in content, "用户配置 MINIMAX_API_KEY 不应再出现"


def test_secret_key_written_to_data_dir_env_only(tmp_path: Path) -> None:
    """launcher 生成的 SECRET_KEY 写到 DATA_DIR/.env,绝不进 .app/.env。

    修前: 写到 .app/.env,被 DataDir 源覆盖,Settings 拿占位值
    修后: 写 DATA_DIR/.env,DataDir 源胜出,Settings 拿真实密钥
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    data_dir_env = data_dir / ".env"
    data_dir_env.write_text("# 初次生成\n", encoding="utf-8")

    app_env = tmp_path / ".app.env"
    app_env.write_text("# 系统配置\nAPI_PORT=8001\n", encoding="utf-8")

    secret_key = ensure_secret_key(data_dir_env)

    # 1. 返回值是 64 字符 hex
    assert len(secret_key) == 64, f"SECRET_KEY 应是 64 字符 hex,实际 {len(secret_key)}"
    assert all(c in "0123456789abcdef" for c in secret_key), "SECRET_KEY 应是 hex 字符"

    # 2. DATA_DIR/.env 含真实密钥
    data_dir_value = _read_env_value(data_dir_env, "SECRET_KEY", "")
    assert data_dir_value == secret_key, "SECRET_KEY 应写进 DATA_DIR/.env"

    # 3. .app/.env 不含 SECRET_KEY
    app_content = app_env.read_text(encoding="utf-8")
    assert "SECRET_KEY" not in app_content, "SECRET_KEY 不应进 .app/.env"


def test_data_dir_env_copied_from_example(tmp_path: Path) -> None:
    """第一次启动时,ensure_data_dir_env 从 .env.example 复制用户配置 key 到 DATA_DIR/.env。

    修前: DATA_DIR/.env 从未由 launcher 创建,可能不存在或只有部分
    修后: launcher 首次启动自动从 .env.example 复制用户配置 key
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    data_dir_env = data_dir / ".env"
    # 关键:DATA_DIR/.env 还不存在
    assert not data_dir_env.exists()

    env_example = _make_env_example(tmp_path)

    ensure_data_dir_env(data_dir_env, env_example)

    assert data_dir_env.exists()
    content = data_dir_env.read_text(encoding="utf-8")
    # 用户配置 key 应该在
    assert "MINIMAX_API_KEY" in content
    assert "OPENCLI_BIN" in content
    # 系统 key 不应该在这里(launcher 在 .app/.env 写)
    assert "API_PORT" not in content, "DATA_DIR/.env 不应含 API_PORT"
    assert "WEB_PORT" not in content, "DATA_DIR/.env 不应含 WEB_PORT"


def test_data_dir_resolves_to_absolute_path_in_data_dir_env(tmp_path: Path) -> None:
    """DATA_DIR/.env 的 DATA_DIR 字段也被转绝对路径,避免 cwd 解析错误。

    修前: DATA_DIR=./data 在 .app/.env 写了绝对路径,但 DATA_DIR/.env 仍然是相对路径
    修后: launcher 显式把 DATA_DIR 写绝对路径到 DATA_DIR/.env
    """
    from launcher.env_bootstrap import _resolve_data_dir_in_data_dir_env

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    data_dir_env = data_dir / ".env"
    data_dir_env.write_text("DATA_DIR=./data\n", encoding="utf-8")

    # bootstrap_env 会调 _resolve_data_dir_in_data_dir_env
    _resolve_data_dir_in_data_dir_env(data_dir_env, project_root=tmp_path)

    value = _read_env_value(data_dir_env, "DATA_DIR", "")
    assert Path(value).is_absolute(), f"DATA_DIR 应是绝对路径,实际 {value}"
