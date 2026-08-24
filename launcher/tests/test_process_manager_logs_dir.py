"""验证 launcher 的 logs_dir 走 DATA_DIR/logs(不再硬编码 project_root/data/logs)。

关联 spec: docs/superpowers/specs/2026-08-23-settings-load-data-dir-env-design.md §修复 2

修复 v0.7.0+6 没覆盖的场景:
- launcher 的 process_manager 之前硬编码 self._logs_dir = project_root / "data" / "logs"
- .app 内 launcher 跑时 api/worker/beat/web 的 stdout 都写到 .app/data/logs/
- 用户期望这些日志在 ~/.xhs-info-crawl/logs/(DATA_DIR)

修法:ProcessManager.__init__ 读 .env 的 LOG_DIR,缺失/空/相对路径 → 自动 resolve 到 DATA_DIR/logs。
"""
from __future__ import annotations

from pathlib import Path

import pytest


def _write_env(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """构造一个最小可用的 project_root(有 venv)。"""
    root = tmp_path / "proj"
    (root / "runtime" / "venv" / "bin").mkdir(parents=True)
    # venv_python 必须存在才能让 ProcessManager 实例化不报错
    (root / "runtime" / "venv" / "bin" / "python").write_text("", encoding="utf-8")
    return root


def test_logs_dir_defaults_to_data_dir_logs(
    project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """.env 无 LOG_DIR → logs_dir = <DATA_DIR>/logs,不是 project_root/data/logs。"""
    data_dir = project_root.parent / "data-default"
    _write_env(project_root / ".env", [f"DATA_DIR={data_dir}"])

    from launcher.process_manager import ProcessManager

    pm = ProcessManager(project_root=project_root, venv_python=project_root / "runtime" / "venv" / "bin" / "python")
    assert pm._logs_dir == data_dir / "logs"


def test_logs_dir_from_env_absolute(
    project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """.env 显式 LOG_DIR=/custom/logs → 用 /custom/logs(不强制改写)。"""
    custom_logs = project_root.parent / "custom" / "logs"
    _write_env(
        project_root / ".env",
        [
            "DATA_DIR=" + str(project_root.parent / "data-x"),
            "LOG_DIR=" + str(custom_logs),
        ],
    )

    from launcher.process_manager import ProcessManager

    pm = ProcessManager(project_root=project_root, venv_python=project_root / "runtime" / "venv" / "bin" / "python")
    assert pm._logs_dir == custom_logs.resolve()


def test_logs_dir_relative_resolved(
    project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """.env LOG_DIR=./logs(相对)→ 解析为 project_root/logs,避免重蹈 DATA_DIR 覆辙。"""
    _write_env(
        project_root / ".env",
        [
            "DATA_DIR=" + str(project_root.parent / "data-r"),
            "LOG_DIR=./logs",
        ],
    )

    from launcher.process_manager import ProcessManager

    pm = ProcessManager(project_root=project_root, venv_python=project_root / "runtime" / "venv" / "bin" / "python")
    assert pm._logs_dir == (project_root / "logs").resolve()


def test_logs_dir_created_on_init(
    project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """logs_dir 不存在时,__init__ 应自动创建(便于直接写日志不报错)。"""
    data_dir = project_root.parent / "data-create"
    _write_env(project_root / ".env", [f"DATA_DIR={data_dir}"])

    from launcher.process_manager import ProcessManager

    pm = ProcessManager(project_root=project_root, venv_python=project_root / "runtime" / "venv" / "bin" / "python")
    assert pm._logs_dir.exists()
    assert pm._logs_dir.is_dir()


def test_logs_dir_fallback_when_data_dir_missing(
    project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """.env 完全没 DATA_DIR(也设不了 LOG_DIR)→ 兜底用 project_root/data/logs(原行为),不崩。"""
    # .env 不存在
    from launcher.process_manager import ProcessManager

    pm = ProcessManager(project_root=project_root, venv_python=project_root / "runtime" / "venv" / "bin" / "python")
    # 兜底路径 — 避免破坏旧 .app 行为
    assert pm._logs_dir == (project_root / "data" / "logs").resolve()
