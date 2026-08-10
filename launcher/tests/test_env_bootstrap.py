"""env_bootstrap 测试:.env 初始化/敏感配置生成/缓存环境变量设置。"""
import os
from pathlib import Path

import pytest

from launcher.env_bootstrap import (
    generate_secret_key,
    generate_admin_password,
    ensure_env_file,
    force_local_host,
    set_cache_env_vars,
    update_env_value,
)


def test_generate_secret_key_returns_32_byte_hex():
    """SECRET_KEY 是 32 字节随机十六进制字符串(64 字符)。"""
    key = generate_secret_key()
    assert len(key) == 64
    assert all(c in "0123456789abcdef" for c in key)
    assert generate_secret_key() != key


def test_generate_admin_password_returns_12_chars():
    """INITIAL_ADMIN_PASSWORD 是 12 位随机密码。"""
    pwd = generate_admin_password()
    assert len(pwd) == 12
    assert generate_admin_password() != pwd


def test_ensure_env_file_creates_from_example(tmp_path: Path):
    """.env 不存在时从 .env.example 复制。"""
    env_example = tmp_path / ".env.example"
    env_example.write_text("FOO=bar\nBAZ=qux\n")
    env_path = tmp_path / ".env"

    ensure_env_file(env_path, env_example)

    assert env_path.exists()
    assert "FOO=bar" in env_path.read_text()
    assert "BAZ=qux" in env_path.read_text()


def test_ensure_env_file_preserves_existing(tmp_path: Path):
    """.env 已存在时不覆盖。"""
    env_example = tmp_path / ".env.example"
    env_example.write_text("FOO=bar\n")
    env_path = tmp_path / ".env"
    env_path.write_text("EXISTING=value\n")

    ensure_env_file(env_path, env_example)

    assert env_path.read_text() == "EXISTING=value\n"


def test_ensure_env_file_generates_secret_key_if_placeholder(tmp_path: Path):
    """SECRET_KEY 是占位值时自动生成真随机密钥。"""
    env_example = tmp_path / ".env.example"
    env_example.write_text("SECRET_KEY=replace-with-a-random-local-secret\n")
    env_path = tmp_path / ".env"

    ensure_env_file(env_path, env_example)

    content = env_path.read_text()
    assert "replace-with-a-random-local-secret" not in content
    for line in content.splitlines():
        if line.startswith("SECRET_KEY="):
            key = line.split("=", 1)[1].strip()
            assert len(key) == 64


def test_ensure_env_file_generates_admin_password_if_empty(tmp_path: Path):
    """INITIAL_ADMIN_PASSWORD 为空时自动生成。"""
    env_example = tmp_path / ".env.example"
    env_example.write_text("INITIAL_ADMIN_PASSWORD=\n")
    env_path = tmp_path / ".env"

    ensure_env_file(env_path, env_example)

    content = env_path.read_text()
    for line in content.splitlines():
        if line.startswith("INITIAL_ADMIN_PASSWORD="):
            pwd = line.split("=", 1)[1].strip()
            assert len(pwd) == 12


def test_force_local_host_resets_non_localhost(tmp_path: Path):
    """API_HOST 非 127.0.0.1 时强制改回。"""
    env_path = tmp_path / ".env"
    env_path.write_text("API_HOST=0.0.0.0\nAPI_PORT=8000\n")

    force_local_host(env_path)

    content = env_path.read_text()
    assert "API_HOST=127.0.0.1" in content
    assert "0.0.0.0" not in content


def test_force_local_host_keeps_localhost(tmp_path: Path):
    """API_HOST 已是 127.0.0.1 时不改。"""
    env_path = tmp_path / ".env"
    env_path.write_text("API_HOST=127.0.0.1\n")

    force_local_host(env_path)

    assert env_path.read_text() == "API_HOST=127.0.0.1\n"


def test_set_cache_env_vars_sets_paddle_pdx_cache_home(tmp_path: Path, monkeypatch):
    """set_cache_env_vars 设置 PADDLE_PDX_CACHE_HOME 环境变量。"""
    monkeypatch.delenv("PADDLE_PDX_CACHE_HOME", raising=False)
    monkeypatch.delenv("HF_HOME", raising=False)

    set_cache_env_vars(project_root=tmp_path)

    assert os.environ["PADDLE_PDX_CACHE_HOME"] == str(tmp_path / "data" / "paddlex")
    assert os.environ["HF_HOME"] == str(tmp_path / "data" / "huggingface")


def test_set_cache_env_vars_creates_directories(tmp_path: Path, monkeypatch):
    """set_cache_env_vars 创建缓存目录。"""
    monkeypatch.delenv("PADDLE_PDX_CACHE_HOME", raising=False)
    monkeypatch.delenv("HF_HOME", raising=False)

    set_cache_env_vars(project_root=tmp_path)

    assert (tmp_path / "data" / "paddlex").is_dir()
    assert (tmp_path / "data" / "huggingface").is_dir()


def test_set_cache_env_vars_does_not_override_existing(tmp_path: Path, monkeypatch):
    """set_cache_env_vars 用 setdefault,不覆盖已存在值。"""
    pre_existing = "/pre/existing/path"
    monkeypatch.setenv("PADDLE_PDX_CACHE_HOME", pre_existing)

    set_cache_env_vars(project_root=tmp_path)

    assert os.environ["PADDLE_PDX_CACHE_HOME"] == pre_existing


def test_update_env_value_updates_existing_key(tmp_path: Path):
    """update_env_value 更新已存在的 key。"""
    env_path = tmp_path / ".env"
    env_path.write_text("FOO=bar\nBAZ=qux\n")

    update_env_value(env_path, "FOO", "newvalue")

    content = env_path.read_text()
    assert "FOO=newvalue" in content
    assert "BAZ=qux" in content


def test_update_env_value_appends_missing_key(tmp_path: Path):
    """update_env_value 追加不存在的 key。"""
    env_path = tmp_path / ".env"
    env_path.write_text("FOO=bar\n")

    update_env_value(env_path, "NEW", "value")

    content = env_path.read_text()
    assert "NEW=value" in content
    assert "FOO=bar" in content
