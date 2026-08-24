"""验证 launcher 启动 celery beat 时显式传 --schedule 走 DATA_DIR/celery/celerybeat-schedule。

关联 spec: docs/superpowers/specs/2026-08-24-celery-beat-schedule-absolute-path-launcher-design.md

修复 v0.7.0+7 没覆盖的场景:
- process_manager.py 启动 beat 命令没传 --schedule,celery beat 默认写到 worker cwd
- .app 内 launcher 跑时,cwd = .app/Contents/Resources/xhs-info-crawl/,
  celerybeat-schedule.db 写到 .app/celerybeat-schedule.db
- 升级 .app 时 schedule 状态丢失,beat 会重新触发所有到期任务

修法:_resolve_beat_schedule_path() 读 .env 的 CELERY_FOLDER(或 fallback 到 DATA_DIR/celery),
转绝对路径,beat 命令显式传 --schedule <绝对路径>。
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
    (root / "runtime" / "venv" / "bin" / "python").write_text("", encoding="utf-8")
    return root


def test_beat_schedule_default_under_data_dir_celery(
    project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """.env 无 CELERY_FOLDER → schedule 路径 = DATA_DIR/celery/celerybeat-schedule(绝对)。"""
    data_dir = project_root.parent / "data-default"
    _write_env(project_root / ".env", [f"DATA_DIR={data_dir}"])

    from launcher.process_manager import ProcessManager

    pm = ProcessManager(
        project_root=project_root, venv_python=project_root / "runtime" / "venv" / "bin" / "python"
    )
    beat_cmd = pm._commands["beat"]
    # 命令必须含 --schedule,且 schedule 路径在 DATA_DIR/celery/celerybeat-schedule
    schedule_idx = beat_cmd.index("--schedule")
    schedule_path = Path(beat_cmd[schedule_idx + 1])
    assert schedule_path.is_absolute()
    assert schedule_path == (data_dir / "celery" / "celerybeat-schedule").resolve()


def test_beat_schedule_uses_celery_folder_from_env(
    project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """.env CELERY_FOLDER=/custom/celery → schedule = /custom/celery/celerybeat-schedule。"""
    _write_env(
        project_root / ".env",
        [
            "DATA_DIR=" + str(project_root.parent / "data-x"),
            "CELERY_FOLDER=/custom/celery",
        ],
    )

    from launcher.process_manager import ProcessManager

    pm = ProcessManager(
        project_root=project_root, venv_python=project_root / "runtime" / "venv" / "bin" / "python"
    )
    beat_cmd = pm._commands["beat"]
    schedule_idx = beat_cmd.index("--schedule")
    schedule_path = Path(beat_cmd[schedule_idx + 1])
    assert schedule_path.is_absolute()
    assert schedule_path == Path("/custom/celery/celerybeat-schedule").resolve()


def test_beat_schedule_relative_celery_folder_resolved(
    project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """.env CELERY_FOLDER=./celery(相对)→ 解析成 project_root/celery/celerybeat-schedule。"""
    _write_env(
        project_root / ".env",
        [
            "DATA_DIR=" + str(project_root.parent / "data-r"),
            "CELERY_FOLDER=./celery",
        ],
    )

    from launcher.process_manager import ProcessManager

    pm = ProcessManager(
        project_root=project_root, venv_python=project_root / "runtime" / "venv" / "bin" / "python"
    )
    beat_cmd = pm._commands["beat"]
    schedule_idx = beat_cmd.index("--schedule")
    schedule_path = Path(beat_cmd[schedule_idx + 1])
    assert schedule_path.is_absolute()
    assert schedule_path == (project_root / "celery" / "celerybeat-schedule").resolve()


def test_beat_schedule_absolute_path_preserved(
    project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """.env CELERY_FOLDER=/abs/path/celery → schedule = /abs/path/celery/celerybeat-schedule(原样)。"""
    _write_env(
        project_root / ".env",
        [
            "DATA_DIR=" + str(project_root.parent / "data-abs"),
            "CELERY_FOLDER=/abs/path/celery",
        ],
    )

    from launcher.process_manager import ProcessManager

    pm = ProcessManager(
        project_root=project_root, venv_python=project_root / "runtime" / "venv" / "bin" / "python"
    )
    beat_cmd = pm._commands["beat"]
    schedule_idx = beat_cmd.index("--schedule")
    schedule_path = Path(beat_cmd[schedule_idx + 1])
    assert schedule_path == Path("/abs/path/celery/celerybeat-schedule").resolve()


def test_beat_schedule_fallback_when_no_data_dir(
    project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """.env 完全缺失 → 兜底 project_root/data/celery/celerybeat-schedule(原行为,不崩)。"""
    # .env 不存在
    from launcher.process_manager import ProcessManager

    pm = ProcessManager(
        project_root=project_root, venv_python=project_root / "runtime" / "venv" / "bin" / "python"
    )
    beat_cmd = pm._commands["beat"]
    schedule_idx = beat_cmd.index("--schedule")
    schedule_path = Path(beat_cmd[schedule_idx + 1])
    assert schedule_path.is_absolute()
    assert schedule_path == (project_root / "data" / "celery" / "celerybeat-schedule").resolve()
