"""抓取流水线并行加速测试。

关联 spec: docs/superpowers/specs/2026-08-10-crawl-pipeline-parallel-speedup-design.md
"""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings


# ============================================================
# 1. Settings 配置字段测试
# ============================================================


class TestSettingsParallelConfig:
    """验证 Settings 有并行配置字段。"""

    def test_settings_has_ocr_parallel_workers(self) -> None:
        """Settings 应有 ocr_parallel_workers 字段。"""
        s = Settings()
        assert hasattr(s, "ocr_parallel_workers"), "Settings 应有 ocr_parallel_workers 字段"

    def test_ocr_parallel_workers_default_is_2(self) -> None:
        """ocr_parallel_workers 默认值应为 2。"""
        s = Settings()
        assert s.ocr_parallel_workers == 2

    def test_settings_has_minimax_concurrency(self) -> None:
        """Settings 应有 minimax_concurrency 字段。"""
        s = Settings()
        assert hasattr(s, "minimax_concurrency"), "Settings 应有 minimax_concurrency 字段"

    def test_minimax_concurrency_default_is_1(self) -> None:
        """minimax_concurrency 默认值应为 1（向后兼容）。"""
        s = Settings()
        assert s.minimax_concurrency == 1


# ============================================================
# 2. MiniMax 并行调用测试
# ============================================================


class TestMiniMaxParallel:
    """验证 MiniMax extract_many_parallel 支持并行调用。"""

    def test_extract_many_parallel_when_concurrency_gt_1(self) -> None:
        """当 minimax_concurrency > 1 时，extract_many_parallel 应并行调用 extract_many。"""
        from app.services.minimax import MiniMaxClient

        settings = Settings()
        settings.minimax_concurrency = 2

        client = MiniMaxClient(settings)

        call_times: list[float] = []

        def mock_extract_many(text: str, reference=None) -> dict:
            call_times.append(time.time())
            time.sleep(0.1)  # 模拟 API 延迟
            return {"activities": []}

        with patch.object(client, "extract_many", side_effect=mock_extract_many):
            texts = ["text1", "text2", "text3", "text4"]
            results = client.extract_many_parallel(texts)

        assert len(results) == 4
        # 并行时 4 次 0.1s 调用应小于 0.3s（串行需 0.4s）
        total_time = call_times[-1] - call_times[0]
        assert total_time < 0.3, f"并行调用耗时 {total_time:.2f}s，预期 < 0.3s"

    def test_extract_many_serial_when_concurrency_is_1(self) -> None:
        """当 minimax_concurrency == 1 时，extract_many_parallel 应串行调用。"""
        from app.services.minimax import MiniMaxClient

        settings = Settings()
        settings.minimax_concurrency = 1

        client = MiniMaxClient(settings)

        call_order: list[str] = []

        def mock_extract_many(text: str, reference=None) -> dict:
            call_order.append(text)
            time.sleep(0.05)
            return {"activities": []}

        with patch.object(client, "extract_many", side_effect=mock_extract_many):
            texts = ["text1", "text2", "text3"]
            results = client.extract_many_parallel(texts)

        assert len(results) == 3
        # 串行时调用顺序应保持不变
        assert call_order == ["text1", "text2", "text3"]

    def test_extract_many_parallel_preserves_order(self) -> None:
        """extract_many_parallel 应按输入顺序返回结果。"""
        from app.services.minimax import MiniMaxClient

        settings = Settings()
        settings.minimax_concurrency = 3

        client = MiniMaxClient(settings)

        def mock_extract_many(text: str, reference=None) -> dict:
            time.sleep(0.02)
            return {"activities": [{"name": text}]}

        with patch.object(client, "extract_many", side_effect=mock_extract_many):
            texts = ["a", "b", "c", "d"]
            results = client.extract_many_parallel(texts)

        assert [r["activities"][0]["name"] for r in results] == ["a", "b", "c", "d"]


# ============================================================
# 3. 图片 OCR 并行测试
# ============================================================


class TestOCRParallel:
    """验证图片 OCR 并行执行。"""

    def test_ocr_process_batch_exists(self) -> None:
        """OCRService 应有 process_batch 方法。"""
        from app.services.ocr import OCRService

        assert hasattr(OCRService, "process_batch"), "OCRService 应有 process_batch 方法"

    def test_ocr_processes_images_in_parallel(self) -> None:
        """process_batch 应使用 ThreadPoolExecutor 并行处理多张图片。"""
        from app.services.ocr import OCRService

        settings = Settings()
        settings.ocr_parallel_workers = 2

        mock_engine = MagicMock()
        call_times: list[float] = []

        def mock_call(path: Path):
            call_times.append(time.time())
            time.sleep(0.1)
            return [(f"text_{path}", 0.9)]  # 返回 lines: list[tuple[str, float]]

        mock_engine.side_effect = mock_call
        ocr = OCRService(mock_engine, settings.ocr_min_confidence)

        images = [Path(f"img{i}.jpg") for i in range(4)]
        results = ocr.process_batch(images, workers=settings.ocr_parallel_workers)

        assert len(results) == 4
        # 并行时 4 次 0.1s 调用应小于 0.3s
        total_time = call_times[-1] - call_times[0]
        assert total_time < 0.3, f"并行 OCR 耗时 {total_time:.2f}s，预期 < 0.3s"

    def test_ocr_process_batch_preserves_order(self) -> None:
        """process_batch 应按输入顺序返回结果。"""
        from app.services.ocr import OCRService

        settings = Settings()
        settings.ocr_parallel_workers = 3

        mock_engine = MagicMock()

        def mock_call(path: Path):
            time.sleep(0.02)
            return [(str(path), 0.9)]

        mock_engine.side_effect = mock_call
        ocr = OCRService(mock_engine, settings.ocr_min_confidence)

        images = [Path("a.jpg"), Path("b.jpg"), Path("c.jpg")]
        results = ocr.process_batch(images, workers=settings.ocr_parallel_workers)

        assert results[0]["text"] == "a.jpg"
        assert results[1]["text"] == "b.jpg"
        assert results[2]["text"] == "c.jpg"

    def test_ocr_process_batch_serial_when_workers_is_1(self) -> None:
        """workers=1 时应串行处理。"""
        from app.services.ocr import OCRService

        settings = Settings()
        settings.ocr_parallel_workers = 1

        mock_engine = MagicMock()
        call_order: list[str] = []

        def mock_call(path: Path):
            call_order.append(str(path))
            time.sleep(0.02)
            return [(str(path), 0.9)]

        mock_engine.side_effect = mock_call
        ocr = OCRService(mock_engine, settings.ocr_min_confidence)

        images = [Path("x.jpg"), Path("y.jpg"), Path("z.jpg")]
        results = ocr.process_batch(images, workers=1)

        assert call_order == ["x.jpg", "y.jpg", "z.jpg"]
