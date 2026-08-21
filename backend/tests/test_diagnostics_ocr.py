"""probe_ocr 区分 disabled_in_config / not_installed 单元测试。

直接 import probe_ocr 测纯函数,不依赖 FastAPI app / HTTP client。

关联 spec: docs/superpowers/specs/2026-08-21-packaging-ocr-llm-flow-fix-design.md § 改动 4
关联设计: docs/packaging-design.md §3.8 四象限表
"""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

# 把 backend/app 加到 sys.path,跟 status_server.ocr_test 一样的 hack
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """每个测试前清 settings 缓存,让 monkeypatch.setenv 生效。"""
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _make_settings(ocr_enabled_value: str, monkeypatch) -> "Settings":  # noqa: F821
    """构造一个 ocr_enabled 等于给定值的 Settings 实例。"""
    monkeypatch.setenv("OCR_ENABLED", ocr_enabled_value)
    from app.core.config import Settings

    return Settings()


def _ensure_paddleocr_importable():
    """塞一个空 paddleocr 模块到 sys.modules,让 `import paddleocr` 不抛 ImportError。

    行为类似 venv 装好了但还没创建 PaddleOCR 实例。
    """
    if "paddleocr" not in sys.modules:
        sys.modules["paddleocr"] = types.ModuleType("paddleocr")


def _block_paddleocr_import():
    """让 `import paddleocr` 抛 ImportError。"""
    sys.modules.pop("paddleocr", None)
    original_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def _import(name, *args, **kwargs):
        if name == "paddleocr" or name.startswith("paddleocr."):
            raise ImportError(f"No module named '{name}'")
        return original_import(name, *args, **kwargs)

    return patch("builtins.__import__", side_effect=_import)


class TestProbeOcrDisabledVsNotInstalled:
    """probe_ocr 必须区分 disabled_in_config / ocr_not_installed。"""

    def test_disabled_but_paddleocr_importable_returns_disabled_in_config(self, monkeypatch):
        """ocr_enabled=False 且 paddleocr 模块可导入 → ocr_disabled_in_config。

        用户现场情况:启动器已下载 OCR 模型,但 OCR_ENABLED 还是 false(开关没同步)。
        旧实现会返回 ocr_disabled(误导用户"OCR 没开");新实现必须告诉用户
        "OCR 包已装,只是配置没开",UI 才能给"前往系统配置启用"的引导。
        """
        from app.services.diagnostics_ocr import probe_ocr

        settings = _make_settings("false", monkeypatch)
        _ensure_paddleocr_importable()

        result = probe_ocr(settings)

        # 清理
        sys.modules.pop("paddleocr", None)

        assert result["ok"] is False
        assert result["reason"] == "ocr_disabled_in_config", (
            f"paddleocr 已装 + ocr_enabled=False → 应该返回 ocr_disabled_in_config "
            f"让 UI 引导用户去系统配置开启；实际: {result}"
        )

    def test_disabled_and_paddleocr_not_importable_returns_ocr_not_installed(self, monkeypatch):
        """ocr_enabled=False 且 paddleocr ImportError → ocr_not_installed。

        UI 据此给"OCR 未安装,请先安装"的引导。
        """
        from app.services.diagnostics_ocr import probe_ocr

        settings = _make_settings("false", monkeypatch)

        with _block_paddleocr_import():
            result = probe_ocr(settings)

        assert result["ok"] is False
        assert result["reason"] == "ocr_not_installed", (
            f"paddleocr 未装 + ocr_enabled=False → 应该返回 ocr_not_installed "
            f"告诉用户先装 OCR；实际: {result}"
        )

    def test_paddleocr_not_installed_when_enabled_unchanged(self, monkeypatch):
        """ocr_enabled=True 但 paddleocr 没装 → 仍然走 paddleocr_not_installed(原有行为)。

        从 v0.5.x 起的诊断回归保护:如果 ocr_enabled=True 但实际包没装,
        报错文案要保留 paddleocr_not_installed (由 PaddleOCREngine._init 抛
        "Install PaddleOCR" 触发)。这个改动 4 不破坏该路径。
        """
        from app.services.diagnostics_ocr import probe_ocr

        settings = _make_settings("true", monkeypatch)

        with patch(
            "app.services.diagnostics_ocr.PaddleOCREngine",
            side_effect=RuntimeError("Install PaddleOCR using docs/paddleocr-setup.md"),
        ):
            result = probe_ocr(settings)

        assert result["ok"] is False
        assert result["reason"] == "paddleocr_not_installed", (
            f"ocr_enabled=True 但 paddleocr 没装,必须保留 paddleocr_not_installed "
            f"(后向兼容 PaddleOCREngine 抛 RuntimeError 路径): {result}"
        )
