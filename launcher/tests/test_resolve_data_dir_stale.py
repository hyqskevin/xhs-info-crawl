"""launcher 检测 .app/.env 的 DATA_DIR 陈旧值并 fallback 默认。

关联 spec: docs/superpowers/specs/2026-08-24-launcher-detect-stale-data-dir-and-fallback-default-design.md

测试覆盖:
1. DATA_DIR= 不存在的绝对路径 → fallback 到 DEFAULT_DATA_DIR
2. DATA_DIR= 存在的绝对路径 → 沿用,不 fallback
3. 目录存在但不含 app.db → 不 fallback(避免 launcher 替用户决定)
4. DATA_DIR= 指向文件而非目录 → fallback
5. DATA_DIR= 空字符串 → fallback(沿用 v0.7.0+6)
6. 陈旧 fallback 时 logger.warning 输出
7. 陈旧 fallback 时 default 参数生效
8. fallback 写回 .env 后幂等
9. fallback 默认路径不可写 → 抛 StaleDataDirFallbackError
"""
from __future__ import annotations

from pathlib import Path

import pytest

from launcher.env_bootstrap import (
    DEFAULT_DATA_DIR,
    StaleDataDirFallbackError,
    _read_env_value,
    resolve_data_dir,
)


class TestResolveDataDirStale:
    """launcher 检测 .app/.env 的 DATA_DIR 陈旧值并 fallback 默认。"""

    def test_resolve_data_dir_falls_back_when_target_missing(self, tmp_path: Path) -> None:
        """DATA_DIR= 不存在的绝对路径 → fallback 到 DEFAULT_DATA_DIR,写回 .env"""
        env_path = tmp_path / ".env"
        env_path.write_text("DATA_DIR=/nonexistent/path/data\n", encoding="utf-8")
        result = resolve_data_dir(env_path, project_root=tmp_path)
        expected = str(Path(DEFAULT_DATA_DIR).expanduser())
        assert result == expected
        # .env 已被改写为绝对路径
        assert _read_env_value(env_path, "DATA_DIR", "") == expected

    def test_resolve_data_dir_does_not_fallback_when_target_exists(self, tmp_path: Path) -> None:
        """DATA_DIR= 存在的绝对路径 → 沿用,不 fallback"""
        real_dir = tmp_path / "existing-data"
        real_dir.mkdir()
        env_path = tmp_path / ".env"
        env_path.write_text(f"DATA_DIR={real_dir}\n", encoding="utf-8")
        result = resolve_data_dir(env_path, project_root=tmp_path)
        assert result == str(real_dir.resolve())

    def test_resolve_data_dir_does_not_fallback_when_target_exists_but_no_app_db(
        self, tmp_path: Path
    ) -> None:
        """目录存在但不含 app.db → 不 fallback(避免 launcher 替用户决定是不是数据目录)"""
        empty_dir = tmp_path / "empty-dir"
        empty_dir.mkdir()
        env_path = tmp_path / ".env"
        env_path.write_text(f"DATA_DIR={empty_dir}\n", encoding="utf-8")
        result = resolve_data_dir(env_path, project_root=tmp_path)
        # 沿用字面值,不 fallback
        assert result == str(empty_dir.resolve())

    def test_resolve_data_dir_falls_back_when_path_is_file_not_dir(self, tmp_path: Path) -> None:
        """DATA_DIR= 指向一个文件而非目录 → fallback"""
        f = tmp_path / "not-a-dir"
        f.write_text("x", encoding="utf-8")
        env_path = tmp_path / ".env"
        env_path.write_text(f"DATA_DIR={f}\n", encoding="utf-8")
        result = resolve_data_dir(env_path, project_root=tmp_path)
        assert "Library/Application Support" in result

    def test_resolve_data_dir_falls_back_when_path_empty(self, tmp_path: Path) -> None:
        """DATA_DIR= 空字符串 → fallback(沿用 v0.7.0+6 行为)"""
        env_path = tmp_path / ".env"
        env_path.write_text("DATA_DIR=\n", encoding="utf-8")
        result = resolve_data_dir(env_path, project_root=tmp_path)
        assert "Library/Application Support" in result

    def test_resolve_data_dir_logs_warning_on_stale(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """陈旧 fallback 时必须输出 logger.warning,启动器日志卡片能看到"""
        import logging

        env_path = tmp_path / ".env"
        env_path.write_text("DATA_DIR=/stale/path\n", encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger="launcher.env_bootstrap"):
            resolve_data_dir(env_path, project_root=tmp_path)
        assert any(
            "陈旧" in record.message or "fallback" in record.message.lower()
            for record in caplog.records
        )

    def test_resolve_data_dir_uses_default_param_over_env_default(self, tmp_path: Path) -> None:
        """default 参数显式传非 DEFAULT_DATA_DIR 时,陈旧 fallback 用 default 参数"""
        env_path = tmp_path / ".env"
        env_path.write_text("DATA_DIR=/stale\n", encoding="utf-8")
        custom_default = str(tmp_path / "custom-default")
        result = resolve_data_dir(
            env_path, project_root=tmp_path, default=custom_default
        )
        assert result == custom_default

    def test_resolve_data_dir_idempotent_after_fallback(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """fallback 写回 .env 后,再次调用 resolve_data_dir 应走"路径有效"分支,不再重复触发 warning"""
        import logging

        env_path = tmp_path / ".env"
        env_path.write_text("DATA_DIR=/stale\n", encoding="utf-8")

        # 第一次:必然 fallback + warning(陈旧)
        with caplog.at_level(logging.WARNING, logger="launcher.env_bootstrap"):
            first_result = resolve_data_dir(env_path, project_root=tmp_path)
        assert "Library/Application Support" in first_result
        assert any(
            "陈旧" in record.message for record in caplog.records
        ), "第一次 fallback 应该输出 warning"

        # 记录第一次调用后 caplog 里的陈旧 warning 数
        first_warning_count = sum(
            1 for r in caplog.records if "陈旧" in r.message
        )
        caplog.clear()

        # 第二次:已 fallback 写回 .env,不应再触发 fallback warning
        resolve_data_dir(env_path, project_root=tmp_path)
        second_warning_count = sum(
            1 for r in caplog.records if "陈旧" in r.message
        )
        assert second_warning_count == 0, (
            f"第二次调用不应再触发陈旧 fallback warning,"
            f"实际新增 {second_warning_count} 条"
        )

    def test_resolve_data_dir_raises_on_unwritable_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """陈旧 fallback 时默认路径不可写 → 抛 StaleDataDirFallbackError"""
        env_path = tmp_path / ".env"
        env_path.write_text("DATA_DIR=/stale\n", encoding="utf-8")
        # mock DEFAULT_DATA_DIR 指向一个不可创建的位置
        unwritable = "/dev/null/should-not-exist/never"
        monkeypatch.setattr(
            "launcher.env_bootstrap.DEFAULT_DATA_DIR", unwritable
        )
        with pytest.raises(StaleDataDirFallbackError, match="fallback 失败"):
            resolve_data_dir(env_path, project_root=tmp_path)