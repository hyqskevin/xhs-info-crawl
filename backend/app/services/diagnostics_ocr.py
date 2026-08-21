"""OCR 诊断:测试 PaddleOCR 是否可用,供启动器调用。

关联 spec: docs/superpowers/specs/2026-08-10-one-click-packaging-design.md § 7.2
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.services.paddleocr_adapter import PaddleOCREngine

logger = logging.getLogger(__name__)

# 测试图固定路径(包内 fixtures)
OCR_TEST_IMAGE = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "ocr_test.png"


def probe_ocr(settings: Settings) -> dict[str, Any]:
    """测试 OCR 是否可用。

    返回:
        - ok=true: {"ok": true, "text": "...", "latency_ms": 123}
        - ok=false: {"ok": false, "reason": "ocr_disabled_in_config"|"ocr_not_installed"|"paddleocr_not_installed"|"model_not_found"|"inference_failed"|"test_image_missing"}

    四象限区分(关联 spec docs/superpowers/specs/2026-08-21-packaging-ocr-llm-flow-fix-design.md § 改动 4):
    - ocr_enabled=False + paddleocr 已装 → ocr_disabled_in_config
      (引导用户去系统配置打开 OCR_ENABLED)
    - ocr_enabled=False + paddleocr 未装 → ocr_not_installed
      (引导用户先安装 OCR)
    - ocr_enabled=True + paddleocr 未装 → paddleocr_not_installed (原有路径,由 PaddleOCREngine 抛 RuntimeError 触发)
    """
    if not settings.ocr_enabled:
        # 区分"包没装"和"包已装只是开关没开"
        try:
            import paddleocr  # noqa: F401
            installed = True
        except ImportError:
            installed = False
        if installed:
            return {"ok": False, "reason": "ocr_disabled_in_config"}
        return {"ok": False, "reason": "ocr_not_installed"}

    # 检查测试图存在
    if not OCR_TEST_IMAGE.exists():
        return {"ok": False, "reason": "test_image_missing"}

    # 尝试初始化 + 推理
    start = time.perf_counter()
    try:
        engine = PaddleOCREngine(settings)
        results = engine(OCR_TEST_IMAGE)
        latency_ms = int((time.perf_counter() - start) * 1000)
        text = " ".join(t for t, _ in results) if results else ""
        return {
            "ok": True,
            "text": text,
            "latency_ms": latency_ms,
        }
    except FileNotFoundError:
        return {"ok": False, "reason": "model_not_found"}
    except RuntimeError as exc:
        # paddleocr_adapter._init 抛 RuntimeError('Install PaddleOCR using ...') 当 paddleocr 未装
        if "Install PaddleOCR" in str(exc):
            return {"ok": False, "reason": "paddleocr_not_installed"}
        logger.warning("OCR 诊断推理失败: %s", exc, exc_info=True)
        return {"ok": False, "reason": "inference_failed", "error": str(exc)}
    except Exception as exc:
        logger.warning("OCR 诊断推理失败: %s", exc, exc_info=True)
        return {"ok": False, "reason": "inference_failed", "error": str(exc)}
