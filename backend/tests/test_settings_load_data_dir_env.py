"""验证 backend Settings 同时读 cwd .env + DATA_DIR/.env,DATA_DIR 优先级更高。

关联 spec: docs/superpowers/specs/2026-08-23-settings-load-data-dir-env-design.md

修复 v0.7.0+6 没覆盖的场景:
- launcher UI 填的 LLM/OCR 配置写到 DATA_DIR/.env(用户配置主源)
- backend 子进程 cwd = .app/Contents/Resources/xhs-info-crawl/,只读 cwd 下 .env(.app/.env)
- 结果 .app/.env 里 LLM 永远是空,DATA_DIR/.env 永远没被 backend 读到

本测试验证 Settings 同时支持 cwd/.env + DATA_DIR/.env,DATA_DIR 优先级高,
进程 env 优先级最高。
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def fresh_settings_cache():
    """清空 lru_cache,确保每个 case 都拿到新的 Settings 实例。"""
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _write_env(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_cwd_env_only(tmp_path: Path, fresh_settings_cache, monkeypatch: pytest.MonkeyPatch) -> None:
    """仅有 cwd/.env:字段按 cwd 解析(回归测试,确保不破坏现有行为)。"""
    cwd = tmp_path / "workdir"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    _write_env(
        cwd / ".env",
        [
            "DATA_DIR=/tmp/data-a",
            "MINIMAX_API_KEY=cwd-key",
            "MINIMAX_MODEL=cwd-model",
        ],
    )
    # DATA_DIR/.env 不存在
    # 清理 env,避免外部污染
    for k in ("MINIMAX_API_KEY", "MINIMAX_MODEL", "MINIMAX_BASE_URL"):
        monkeypatch.delenv(k, raising=False)

    from app.core.config import get_settings

    s = get_settings()
    assert s.minimax_api_key == "cwd-key"
    assert s.minimax_model == "cwd-model"


def test_data_dir_env_only(tmp_path: Path, fresh_settings_cache, monkeypatch: pytest.MonkeyPatch) -> None:
    """仅有 DATA_DIR/.env:cwd/.env 不含该字段,从 DATA_DIR/.env 读。"""
    cwd = tmp_path / "workdir"
    cwd.mkdir()
    data_dir = tmp_path / "data-a"
    data_dir.mkdir()
    monkeypatch.chdir(cwd)
    _write_env(cwd / ".env", ["DATA_DIR=" + str(data_dir)])
    _write_env(
        data_dir / ".env",
        [
            "MINIMAX_API_KEY=data-only-key",
            "MINIMAX_BASE_URL=https://data.example/v1",
        ],
    )
    for k in ("MINIMAX_API_KEY", "MINIMAX_MODEL", "MINIMAX_BASE_URL"):
        monkeypatch.delenv(k, raising=False)

    from app.core.config import get_settings

    s = get_settings()
    assert s.minimax_api_key == "data-only-key"
    assert s.minimax_base_url == "https://data.example/v1"


def test_data_dir_overrides_cwd(
    tmp_path: Path, fresh_settings_cache, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DATA_DIR/.env 优先级 > cwd/.env(用户在 DATA_DIR 配的覆盖 .app/.env 模板)。"""
    cwd = tmp_path / "workdir"
    cwd.mkdir()
    data_dir = tmp_path / "data-a"
    data_dir.mkdir()
    monkeypatch.chdir(cwd)
    _write_env(
        cwd / ".env",
        [
            "DATA_DIR=" + str(data_dir),
            "MINIMAX_API_KEY=cwd-key-old",
        ],
    )
    _write_env(
        data_dir / ".env",
        ["MINIMAX_API_KEY=data-key-new"],
    )
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)

    from app.core.config import get_settings

    s = get_settings()
    assert s.minimax_api_key == "data-key-new"


def test_env_var_overrides_data_dir(
    tmp_path: Path, fresh_settings_cache, monkeypatch: pytest.MonkeyPatch
) -> None:
    """进程 env > DATA_DIR/.env > cwd/.env(测试/CI 覆盖一切)。"""
    cwd = tmp_path / "workdir"
    cwd.mkdir()
    data_dir = tmp_path / "data-a"
    data_dir.mkdir()
    monkeypatch.chdir(cwd)
    _write_env(
        cwd / ".env",
        [
            "DATA_DIR=" + str(data_dir),
            "MINIMAX_API_KEY=cwd-key",
        ],
    )
    _write_env(data_dir / ".env", ["MINIMAX_API_KEY=data-key"])
    monkeypatch.setenv("MINIMAX_API_KEY", "runtime-key")

    from app.core.config import get_settings

    s = get_settings()
    assert s.minimax_api_key == "runtime-key"


def test_missing_data_dir_in_cwd_env(
    tmp_path: Path, fresh_settings_cache, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cwd/.env 无 DATA_DIR → 不报错,DataDirEnvSource 返回空 dict,Settings 走 cwd/.env 默认。"""
    cwd = tmp_path / "workdir"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    _write_env(cwd / ".env", ["MINIMAX_API_KEY=no-data-dir"])
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)

    from app.core.config import get_settings

    s = get_settings()
    assert s.minimax_api_key == "no-data-dir"


def test_data_dir_does_not_exist(
    tmp_path: Path, fresh_settings_cache, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cwd/.env 配了 DATA_DIR 但 DATA_DIR/.env 不存在 → 不报错,走 cwd/.env。"""
    cwd = tmp_path / "workdir"
    cwd.mkdir()
    fake_data = tmp_path / "no-such-dir"
    monkeypatch.chdir(cwd)
    _write_env(
        cwd / ".env",
        [
            "DATA_DIR=" + str(fake_data),
            "MINIMAX_API_KEY=cwd-only",
        ],
    )
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)

    from app.core.config import get_settings

    s = get_settings()
    assert s.minimax_api_key == "cwd-only"


def test_priority_chain_full(
    tmp_path: Path, fresh_settings_cache, monkeypatch: pytest.MonkeyPatch
) -> None:
    """同时存在 cwd/.env + DATA_DIR/.env + 进程 env,验证完整优先级链:

    进程 env > DATA_DIR/.env > cwd/.env

    不同字段来自不同源,确保不被串台。
    """
    cwd = tmp_path / "workdir"
    cwd.mkdir()
    data_dir = tmp_path / "data-a"
    data_dir.mkdir()
    monkeypatch.chdir(cwd)
    _write_env(
        cwd / ".env",
        [
            "DATA_DIR=" + str(data_dir),
            "MINIMAX_API_KEY=cwd-key",
            "MINIMAX_MODEL=cwd-model",
        ],
    )
    _write_env(
        data_dir / ".env",
        [
            "MINIMAX_API_KEY=data-key",  # 覆盖 cwd
            "MINIMAX_BASE_URL=https://data.example/v1",  # cwd 无
        ],
    )
    # 进程 env 只覆盖 model,不覆盖 api_key/base_url
    monkeypatch.setenv("MINIMAX_MODEL", "runtime-model")

    for k in ("MINIMAX_API_KEY", "MINIMAX_BASE_URL"):
        monkeypatch.delenv(k, raising=False)

    from app.core.config import get_settings

    s = get_settings()
    assert s.minimax_api_key == "data-key"  # DATA_DIR 覆盖 cwd
    assert s.minimax_model == "runtime-model"  # env 覆盖一切
    assert s.minimax_base_url == "https://data.example/v1"  # 仅 DATA_DIR 有
