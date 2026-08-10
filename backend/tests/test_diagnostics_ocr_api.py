"""OCR 诊断接口测试:启动器用这个接口测试 OCR 是否可用。

关联 spec: docs/superpowers/specs/2026-08-10-one-click-packaging-design.md § 7.2
"""
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import create_access_token


API_PREFIX = "/api/v1"


def _auth_header() -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """每个测试前清除 settings 缓存,让 monkeypatch 生效。"""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_diagnostics_ocr_disabled(monkeypatch) -> None:
    """OCR_ENABLED=false 时返回 ocr_disabled。"""
    monkeypatch.setenv("OCR_ENABLED", "false")
    from app.main import app
    with TestClient(app) as client:
        resp = client.post(f"{API_PREFIX}/diagnostics/ocr", headers=_auth_header())
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["ok"] is False
        assert data["reason"] == "ocr_disabled"


def test_diagnostics_ocr_paddleocr_not_installed(monkeypatch) -> None:
    """paddleocr 未安装时返回 paddleocr_not_installed。"""
    monkeypatch.setenv("OCR_ENABLED", "true")
    from app.main import app

    # PaddleOCREngine(settings) 抛 RuntimeError('Install PaddleOCR using ...') → paddleocr_not_installed
    with patch(
        "app.services.diagnostics_ocr.PaddleOCREngine",
        side_effect=RuntimeError("Install PaddleOCR using docs/paddleocr-setup.md"),
    ):
        with TestClient(app) as client:
            resp = client.post(f"{API_PREFIX}/diagnostics/ocr", headers=_auth_header())
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["ok"] is False
            assert data["reason"] == "paddleocr_not_installed"


def test_diagnostics_ocr_model_not_found(monkeypatch) -> None:
    """模型目录不存在时返回 model_not_found。"""
    monkeypatch.setenv("OCR_ENABLED", "true")
    from app.main import app

    with patch(
        "app.services.diagnostics_ocr.PaddleOCREngine",
        side_effect=FileNotFoundError("model not found"),
    ):
        with TestClient(app) as client:
            resp = client.post(f"{API_PREFIX}/diagnostics/ocr", headers=_auth_header())
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["ok"] is False
            assert data["reason"] == "model_not_found"


def test_diagnostics_ocr_success(monkeypatch) -> None:
    """OCR 正常工作时返回 ok=true + 识别文字 + 耗时。"""
    monkeypatch.setenv("OCR_ENABLED", "true")
    from app.main import app

    # PaddleOCREngine 是类: PaddleOCREngine(settings) 返回实例, 实例(path) 返回结果列表
    mock_engine_cls = MagicMock()
    mock_engine_instance = MagicMock()
    mock_engine_instance.return_value = [("Hello OCR Test 2026", 0.95)]
    mock_engine_cls.return_value = mock_engine_instance
    with patch("app.services.diagnostics_ocr.PaddleOCREngine", mock_engine_cls):
        with TestClient(app) as client:
            resp = client.post(f"{API_PREFIX}/diagnostics/ocr", headers=_auth_header())
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["ok"] is True
            assert "Hello OCR Test" in data["text"]
            assert data["latency_ms"] >= 0


def test_diagnostics_ocr_inference_failed(monkeypatch) -> None:
    """OCR 推理失败时返回 inference_failed。"""
    monkeypatch.setenv("OCR_ENABLED", "true")
    from app.main import app

    # PaddleOCREngine(settings) 成功但实例(path) 抛 RuntimeError → inference_failed
    mock_engine_cls = MagicMock()
    mock_engine_instance = MagicMock()
    mock_engine_instance.side_effect = RuntimeError("inference error")
    mock_engine_cls.return_value = mock_engine_instance
    with patch("app.services.diagnostics_ocr.PaddleOCREngine", mock_engine_cls):
        with TestClient(app) as client:
            resp = client.post(f"{API_PREFIX}/diagnostics/ocr", headers=_auth_header())
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["ok"] is False
            assert data["reason"] == "inference_failed"
