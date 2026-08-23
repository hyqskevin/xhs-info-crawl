"""launcher DATA_DIR 路径解析测试(v0.7.0+6)。

背景:
- 用户 .env 里 DATA_DIR 是相对路径 (./data / data) 时,launcher / .app 模式下
  backend 子进程 cwd 是 .app/Contents/Resources/xhs-info-crawl/,相对路径
  会解析到 .app/data/,导致日志/celery/run/全丢
- dev 模式下 backend cwd = backend/,相对路径解析到 backend/data/,看似正常
- 修法:launcher bootstrap 时把 DATA_DIR 转绝对路径,再启动 backend

关联 spec: docs/superpowers/specs/2026-08-23-data-dir-absolute-path-launcher-design.md
"""
from __future__ import annotations

from pathlib import Path

from launcher.env_bootstrap import (
    DEFAULT_DATA_DIR,
    resolve_data_dir,
    update_env_value,
    _read_env_value,
)


def _make_env(tmp_path: Path, lines: list[str]) -> Path:
    env_path = tmp_path / ".env"
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return env_path


def test_resolve_relative_data_dir_to_absolute(tmp_path: Path) -> None:
    """DATA_DIR=./data → 绝对路径 = <project_root>/data,写入 .env。

    修前: launcher 不动 DATA_DIR,backend 进程从 cwd 解析 → 丢数据
    修后: resolve_data_dir 把 ./data 转成 <project_root>/.resolve()/data
    """
    env_path = _make_env(tmp_path, ["DATA_DIR=./data"])

    resolved = resolve_data_dir(env_path, project_root=tmp_path)

    assert Path(resolved).is_absolute(), f"resolved 应是绝对路径,实际 {resolved}"
    # 写入 .env
    assert _read_env_value(env_path, "DATA_DIR", "") == resolved
    # 应等于 project_root/.resolve()/data
    expected = (tmp_path / "data").resolve()
    assert Path(resolved).resolve() == expected


def test_resolve_relative_data_dir_without_dot_prefix(tmp_path: Path) -> None:
    """DATA_DIR=data → 绝对路径 = <project_root>/data(无 ./ 前缀也走同一条路径)。"""
    env_path = _make_env(tmp_path, ["DATA_DIR=data"])

    resolved = resolve_data_dir(env_path, project_root=tmp_path)

    assert Path(resolved).is_absolute()
    assert Path(resolved).resolve() == (tmp_path / "data").resolve()


def test_resolve_keeps_absolute_data_dir(tmp_path: Path) -> None:
    """DATA_DIR=/Users/foo/bar → 绝对路径,不修改,直接写入 .env。"""
    abs_dir = str(tmp_path / "absolute_user_data")
    env_path = _make_env(tmp_path, [f"DATA_DIR={abs_dir}"])

    resolved = resolve_data_dir(env_path, project_root=tmp_path)

    assert Path(resolved).is_absolute()
    assert Path(resolved).resolve() == Path(abs_dir).resolve()
    assert _read_env_value(env_path, "DATA_DIR", "") == resolved


def test_resolve_empty_data_dir_to_default(tmp_path: Path) -> None:
    """DATA_DIR 空 → DEFAULT_DATA_DIR(~/Library/Application Support/...)展开为绝对路径。

    默认值是字符串 DEFAULT_DATA_DIR 常量,以 ~/ 开头;resolve_data_dir 应展开 ~。
    """
    env_path = _make_env(tmp_path, [])  # 完全空 .env

    resolved = resolve_data_dir(env_path, project_root=tmp_path)

    assert Path(resolved).is_absolute(), f"空 DATA_DIR 应展开为绝对路径,实际 {resolved}"
    # 不应该含有 ~/ 未展开
    assert "~/" not in resolved, f"~ 未展开,实际 {resolved}"
    # 应该等于 DEFAULT_DATA_DIR 展开后
    expected_default = str(Path(DEFAULT_DATA_DIR).expanduser().resolve())
    assert Path(resolved).resolve() == Path(expected_default).resolve()
    # 已写入 .env
    assert _read_env_value(env_path, "DATA_DIR", "") == resolved


def test_resolve_relative_data_dir_with_tilde(tmp_path: Path) -> None:
    """DATA_DIR=~/Library/foo → 已经是绝对路径(expanduser 展开后),不修改。"""
    env_path = _make_env(tmp_path, ["DATA_DIR=~/Library/foo"])

    resolved = resolve_data_dir(env_path, project_root=tmp_path)

    assert Path(resolved).is_absolute()
    assert "~/" not in resolved
    # 应等于 ~/Library/foo 展开后
    assert Path(resolved).resolve() == (Path("~/Library/foo").expanduser()).resolve()


def test_bootstrap_env_integration_converts_data_dir(tmp_path: Path) -> None:
    """bootstrap_env 端到端:用户 .env DATA_DIR=./data → 启动后 DATA_DIR 是绝对路径。

    这是用户 v0.7.0 ~ v0.7.1 反复遇到的核心回归:
    之前 launcher 不动 DATA_DIR,backend 子进程 cwd = .app 内,数据写到 .app/data/ 全丢。
    本测试调 launcher.bootstrap_env 端到端验证 .env 真的被改成绝对路径。
    """
    from launcher.main import bootstrap_env

    env_path = _make_env(tmp_path, [
        "DATA_DIR=./data",
        "SECRET_KEY=pytest-only-jwt-secret-at-least-32-bytes",
    ])

    api_port, web_port = bootstrap_env(tmp_path)

    # 端口应被分配
    assert 8001 <= api_port <= 8020
    assert 5173 <= web_port <= 5199

    # DATA_DIR 应该是绝对路径
    final_data_dir = _read_env_value(env_path, "DATA_DIR", "")
    assert Path(final_data_dir).is_absolute(), (
        f"bootstrap_env 没把 DATA_DIR 转绝对路径,仍是 {final_data_dir}"
    )
    assert "~/" not in final_data_dir
    # 应等于 <tmp_path>/data
    assert Path(final_data_dir).resolve() == (tmp_path / "data").resolve()