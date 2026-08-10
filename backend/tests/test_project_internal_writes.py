"""验证所有写操作都在项目内，不污染项目外部目录。

关联 spec: docs/superpowers/specs/2026-08-10-project-internal-writes-only-design.md
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.config import Settings, get_settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
PRODUCTION_CODE_DIR = BACKEND_DIR / "app"


# ============================================================
# 1. Settings 配置字段测试
# ============================================================


class TestSettingsPaths:
    """验证 Settings 有 task_registry_path 和 tmp_dir 字段，默认在项目内。"""

    def test_settings_has_task_registry_path_field(self) -> None:
        """Settings 应有 task_registry_path 字段。"""
        s = Settings()
        assert hasattr(s, "task_registry_path"), "Settings 应有 task_registry_path 字段"

    def test_settings_task_registry_path_default_in_project(self) -> None:
        """task_registry_path 默认值应在 ./data/ 下。"""
        s = Settings()
        path = s.task_registry_path
        # 解析后应在项目内
        resolved = path if path.is_absolute() else PROJECT_ROOT / path
        assert str(resolved).startswith(str(PROJECT_ROOT)), (
            f"task_registry_path 应在项目内，实际: {resolved}"
        )

    def test_settings_has_tmp_dir_field(self) -> None:
        """Settings 应有 tmp_dir 字段。"""
        s = Settings()
        assert hasattr(s, "tmp_dir"), "Settings 应有 tmp_dir 字段"

    def test_settings_tmp_dir_default_in_project(self) -> None:
        """tmp_dir 默认值应在 ./data/tmp 下。"""
        s = Settings()
        path = s.tmp_dir
        resolved = path if path.is_absolute() else PROJECT_ROOT / path
        assert str(resolved).startswith(str(PROJECT_ROOT)), (
            f"tmp_dir 应在项目内，实际: {resolved}"
        )


# ============================================================
# 2. task_registry 路径测试
# ============================================================


class TestTaskRegistryPath:
    """验证 task_registry 不再写 /tmp。"""

    def test_task_registry_path_not_in_tmp(self) -> None:
        """REGISTRY_PATH 不应是 /tmp/ 开头。"""
        from app.services import task_registry

        path = task_registry.REGISTRY_PATH
        assert not str(path).startswith("/tmp"), (
            f"task_registry.REGISTRY_PATH 不应指向 /tmp，实际: {path}"
        )

    def test_task_registry_path_in_project(self) -> None:
        """REGISTRY_PATH 应在项目内。"""
        from app.services import task_registry

        path = task_registry.REGISTRY_PATH
        assert str(path).startswith(str(PROJECT_ROOT)), (
            f"task_registry.REGISTRY_PATH 应在项目内，实际: {path}"
        )


# ============================================================
# 3. 生产代码静态检查：无硬编码外部路径
# ============================================================


class TestNoHardcodedExternalPaths:
    """验证生产代码无硬编码的外部路径。"""

    # 需要检查的目录
    SCAN_DIRS = [
        PRODUCTION_CODE_DIR / "services",
        PRODUCTION_CODE_DIR / "api",
        PRODUCTION_CODE_DIR / "tasks",
        PRODUCTION_CODE_DIR / "core",
    ]

    # 禁止出现的模式（注释除外）
    FORBIDDEN_PATTERNS = [
        (r'["\'](/tmp/)', "硬编码 /tmp/ 路径"),
        (r'tempfile\.gettempdir\(\)', "使用 tempfile.gettempdir()"),
        (r'Path\.home\(\)', "使用 Path.home()"),
        (r'expanduser\s*\(\s*["\']~', "使用 expanduser('~')"),
        (r'os\.path\.expanduser\s*\(\s*["\']~', "使用 os.path.expanduser('~')"),
    ]

    @pytest.mark.parametrize("scan_dir", SCAN_DIRS)
    def test_no_forbidden_paths_in_production_code(self, scan_dir: Path) -> None:
        """生产代码不应硬编码 /tmp、Path.home()、expanduser('~') 等。"""
        if not scan_dir.exists():
            pytest.skip(f"目录不存在: {scan_dir}")

        violations: list[str] = []
        for py_file in scan_dir.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            for line_no, line in enumerate(content.splitlines(), 1):
                # 跳过注释行
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for pattern, desc in self.FORBIDDEN_PATTERNS:
                    if re.search(pattern, line):
                        violations.append(
                            f"{py_file.relative_to(PROJECT_ROOT)}:{line_no} {desc}: {line.strip()}"
                        )

        assert not violations, (
            "生产代码发现硬编码外部路径:\n" + "\n".join(violations)
        )
