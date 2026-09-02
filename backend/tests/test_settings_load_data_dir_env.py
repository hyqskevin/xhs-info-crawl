"""验证 backend Settings 同时读 cwd .env + DATA_DIR/.env,cwd/.env 优先级更高。

关联 spec: docs/superpowers/specs/2026-09-02-env-loading-priority-design.md

设计约束:
- dev 模式下项目根 `.env` 中的用户配置(如 MINIMAX_API_KEY)必须生效,
  不能被 `data/.env` 里的空值覆盖。
- 生产打包场景下 `.app/.env` 作为系统 key 来源,
  用户 key 仍可从 `DATA_DIR/.env` 读取。
- 进程 env 优先级最高(测试/CI 覆盖一切)。
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


def test_cwd_env_overrides_data_dir(
    tmp_path: Path, fresh_settings_cache, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cwd/.env 优先级 > DATA_DIR/.env(dev 模式下项目根 .env 胜出)。"""
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
    _write_env(
        data_dir / ".env",
        ["MINIMAX_API_KEY=data-key"],
    )
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)

    from app.core.config import get_settings

    s = get_settings()
    assert s.minimax_api_key == "cwd-key"


def test_data_dir_env_fallback_when_cwd_missing(
    tmp_path: Path, fresh_settings_cache, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cwd/.env 缺字段时,DATA_DIR/.env 作为补充源 fallback。"""
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
    _write_env(
        data_dir / ".env",
        [
            "MINIMAX_BASE_URL=https://data.example/v1",
        ],
    )
    for k in ("MINIMAX_API_KEY", "MINIMAX_BASE_URL"):
        monkeypatch.delenv(k, raising=False)

    from app.core.config import get_settings

    s = get_settings()
    assert s.minimax_api_key == "cwd-key"  # cwd 有值,用 cwd
    assert s.minimax_base_url == "https://data.example/v1"  # cwd 缺,从 DATA_DIR fallback


def test_env_var_overrides_data_dir(
    tmp_path: Path, fresh_settings_cache, monkeypatch: pytest.MonkeyPatch
) -> None:
    """进程 env > cwd/.env > DATA_DIR/.env(测试/CI 覆盖一切)。"""
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

    进程 env > cwd/.env > DATA_DIR/.env

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
            "MINIMAX_API_KEY=data-key",
            "MINIMAX_BASE_URL=https://data.example/v1",
        ],
    )
    # 进程 env 只覆盖 model,不覆盖 api_key/base_url
    monkeypatch.setenv("MINIMAX_MODEL", "runtime-model")

    for k in ("MINIMAX_API_KEY", "MINIMAX_BASE_URL"):
        monkeypatch.delenv(k, raising=False)

    from app.core.config import get_settings

    s = get_settings()
    assert s.minimax_api_key == "cwd-key"  # cwd 覆盖 DATA_DIR
    assert s.minimax_model == "runtime-model"  # env 覆盖一切
    assert s.minimax_base_url == "https://data.example/v1"  # cwd 缺,从 DATA_DIR fallback
