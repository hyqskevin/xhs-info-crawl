# P2 后端静态挂载 + OCR 诊断接口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让后端直接服务前端构建产物(打包版需要),并新增 OCR 诊断接口供启动器测试 OCR 是否可用。

**Architecture:** 在 `main.py` 启动时检测 `frontend/dist` 是否存在,存在则用 `StaticFiles` 挂载到根路径(开发模式无此目录则跳过,不影响);新增 `POST /api/v1/diagnostics/ocr` 接口,调用 `PaddleOCREngine` 对包内测试图做识别,返回 ok/text/latency_ms 或 ok=false/reason。

**Tech Stack:** FastAPI + StaticFiles + paddleocr + pytest

**Spec:** `docs/superpowers/specs/2026-08-10-one-click-packaging-design.md` § 7.1 + § 7.2

---

### Task 1: 写失败测试 — 静态文件挂载

**Files:**
- Create: `backend/tests/test_static_frontend_mount.py`

- [ ] **Step 1: 写测试文件**

创建 `backend/tests/test_static_frontend_mount.py`:

```python
"""验证后端启动时挂载 frontend/dist 静态文件(打包版需要)。

关联 spec: docs/superpowers/specs/2026-08-10-one-click-packaging-design.md § 7.1
"""
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


def test_static_frontend_mounted_when_dist_exists(tmp_path: Path) -> None:
    """frontend/dist 存在时,后端应挂载 StaticFiles,根路径返回 index.html。"""
    # 模拟 dist 目录存在
    fake_dist = tmp_path / "frontend" / "dist"
    fake_dist.mkdir(parents=True)
    (fake_dist / "index.html").write_text("<html><body>main app</body></html>")

    with patch("app.main.settings.frontend_dist_path", fake_dist):
        from app.main import app
        # 重新触发挂载逻辑(通过 lifespan 或直接调用挂载函数)
        from app.main import mount_static_frontend_if_exists
        mount_static_frontend_if_exists(app, fake_dist)

        with TestClient(app) as client:
            resp = client.get("/")
            assert resp.status_code == 200
            assert "main app" in resp.text


def test_static_frontend_not_mounted_when_dist_missing(tmp_path: Path) -> None:
    """frontend/dist 不存在时,后端不挂载静态文件,根路径返回 404。"""
    nonexistent = tmp_path / "nonexistent-dist"

    from app.main import app, mount_static_frontend_if_exists
    mount_static_frontend_if_exists(app, nonexistent)

    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 404


def test_static_frontend_serves_assets(tmp_path: Path) -> None:
    """挂载后,assets 目录下的文件也能访问。"""
    fake_dist = tmp_path / "frontend" / "dist"
    fake_dist.mkdir(parents=True)
    (fake_dist / "index.html").write_text("<html></html>")
    assets_dir = fake_dist / "assets"
    assets_dir.mkdir()
    (assets_dir / "app.js").write_text("console.log('app');")

    from app.main import app, mount_static_frontend_if_exists
    mount_static_frontend_if_exists(app, fake_dist)

    with TestClient(app) as client:
        resp = client.get("/assets/app.js")
        assert resp.status_code == 200
        assert "console.log" in resp.text


def test_static_frontend_spa_fallback(tmp_path: Path) -> None:
    """SPA 模式:未匹配的路由回退到 index.html(如 /dashboard)。"""
    fake_dist = tmp_path / "frontend" / "dist"
    fake_dist.mkdir(parents=True)
    (fake_dist / "index.html").write_text("<html><body>SPA</body></html>")

    from app.main import app, mount_static_frontend_if_exists
    mount_static_frontend_if_exists(app, fake_dist)

    with TestClient(app) as client:
        # /dashboard 不存在为静态文件,应回退到 index.html
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "SPA" in resp.text
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && uv run pytest tests/test_static_frontend_mount.py -v`

Expected: 4 个 FAIL(`mount_static_frontend_if_exists` 不存在)

---

### Task 2: 实现静态文件挂载

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/core/config.py`(新增 `frontend_dist_path` 字段)

- [ ] **Step 1: 在 Settings 新增 frontend_dist_path 字段**

在 `backend/app/core/config.py` 的 Settings 类里,新增字段(放在 `paddle_pdx_cache_home` 附近):

```python
    # 前端构建产物目录(打包版用,开发模式为 None 或不存在)
    frontend_dist_path: Path = Field(
        Path("./frontend/dist"),
        validation_alias="FRONTEND_DIST_PATH",
    )
```

- [ ] **Step 2: 在 main.py 实现挂载函数**

在 `backend/app/main.py` 末尾新增:

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse


def mount_static_frontend_if_exists(app: FastAPI, dist_path: Path) -> None:
    """挂载前端静态文件;dist 不存在则跳过(开发模式)。

    打包版需要这个:后端直接服务前端构建产物,不用单独跑 vite dev server。
    """
    if not dist_path.exists() or not dist_path.is_dir():
        return

    index_html = dist_path / "index.html"
    if not index_html.exists():
        return

    # 挂载 assets 等静态资源
    assets_dir = dist_path / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    # SPA fallback:未匹配的路由回退到 index.html
    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        # 优先返回对应的静态文件
        file_path = dist_path / full_path
        if full_path and file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        # 否则回退到 index.html(让前端路由处理)
        return FileResponse(index_html)
```

- [ ] **Step 3: 在 lifespan 里调用挂载**

在 `backend/app/main.py` 的 `lifespan` 函数里,`init_database()` 后追加:

```python
@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings.ensure_runtime_directories()
    init_database()
    mount_static_frontend_if_exists(app, settings.frontend_dist_path)
    yield
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && uv run pytest tests/test_static_frontend_mount.py -v`

Expected: 4 个 PASS

注意:如果测试因为 `app` 已经在模块级别创建导致重复路由报错,需要调整测试策略——在测试里用独立的 FastAPI 实例,或者用 `importlib.reload` 重新加载 `app.main`。先尝试直接跑,如果有问题再调整。

---

### Task 3: 写失败测试 — OCR 诊断接口

**Files:**
- Create: `backend/tests/test_diagnostics_ocr_api.py`
- Create: `backend/tests/fixtures/ocr_test.png`(测试图)

- [ ] **Step 1: 创建测试 fixtures 目录和测试图**

```bash
mkdir -p backend/tests/fixtures
```

用 Python 生成一张简单的测试图(包含可识别文字):

```python
# 生成测试图脚本,运行后删除
from PIL import Image, ImageDraw, ImageFont
img = Image.new('RGB', (300, 100), color='white')
draw = ImageDraw.Draw(img)
draw.text((20, 30), "Hello OCR Test 2026", fill='black')
img.save('backend/tests/fixtures/ocr_test.png')
```

如果 PIL 不可用,改用 `GenerateImage` 工具或从网上下载一张简单图片。

- [ ] **Step 2: 写测试文件**

创建 `backend/tests/test_diagnostics_ocr_api.py`:

```python
"""OCR 诊断接口测试:启动器用这个接口测试 OCR 是否可用。

关联 spec: docs/superpowers/specs/2026-08-10-one-click-packaging-design.md § 7.2
"""
from pathlib import Path
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from app.core.security import create_access_token


API_PREFIX = "/api/v1"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _auth_header() -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


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

    # 模拟 paddleocr 导入失败
    with patch("builtins.__import__", side_effect=ImportError("no paddleocr")):
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

    # 模拟 paddleocr 可导入但模型目录不存在
    with patch("app.services.diagnostics_ocr.PaddleOCREngine", side_effect=FileNotFoundError("model not found")):
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

    # 模拟 PaddleOCREngine 返回识别结果
    mock_engine = MagicMock()
    mock_engine.return_value = [("Hello OCR Test 2026", 0.95)]
    with patch("app.services.diagnostics_ocr.PaddleOCREngine", mock_engine):
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

    mock_engine = MagicMock()
    mock_engine.side_effect = RuntimeError("inference error")
    with patch("app.services.diagnostics_ocr.PaddleOCREngine", mock_engine):
        with TestClient(app) as client:
            resp = client.post(f"{API_PREFIX}/diagnostics/ocr", headers=_auth_header())
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["ok"] is False
            assert data["reason"] == "inference_failed"
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd backend && uv run pytest tests/test_diagnostics_ocr_api.py -v`

Expected: 5 个 FAIL(接口不存在)

---

### Task 4: 实现 OCR 诊断服务 + 接口

**Files:**
- Create: `backend/app/services/diagnostics_ocr.py`
- Modify: `backend/app/api/v1/diagnostics.py`

- [ ] **Step 1: 创建 OCR 诊断服务**

创建 `backend/app/services/diagnostics_ocr.py`:

```python
"""OCR 诊断:测试 PaddleOCR 是否可用,供启动器调用。

关联 spec: docs/superpowers/specs/2026-08-10-one-click-packaging-design.md § 7.2
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from app.core.config import Settings

logger = logging.getLogger(__name__)

# 测试图固定路径(包内 fixtures)
OCR_TEST_IMAGE = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "ocr_test.png"


def probe_ocr(settings: Settings) -> dict[str, Any]:
    """测试 OCR 是否可用。

    返回:
        - ok=true: {"ok": true, "text": "...", "latency_ms": 123}
        - ok=false: {"ok": false, "reason": "ocr_disabled"|"paddleocr_not_installed"|"model_not_found"|"inference_failed"|"test_image_missing"}
    """
    if not settings.ocr_enabled:
        return {"ok": False, "reason": "ocr_disabled"}

    # 检查测试图存在
    if not OCR_TEST_IMAGE.exists():
        return {"ok": False, "reason": "test_image_missing"}

    # 尝试导入 paddleocr
    try:
        from app.services.paddleocr_adapter import PaddleOCREngine
    except ImportError:
        return {"ok": False, "reason": "paddleocr_not_installed"}

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
    except Exception as exc:
        logger.warning("OCR 诊断推理失败: %s", exc, exc_info=True)
        return {"ok": False, "reason": "inference_failed", "error": str(exc)}
```

- [ ] **Step 2: 在 diagnostics 路由新增 OCR 接口**

在 `backend/app/api/v1/diagnostics.py` 末尾追加:

```python
from app.services import diagnostics_ocr as ocr_svc


@router.post("/ocr")
def diagnostics_ocr(_: dict = Depends(require_admin), settings: Settings = Depends(get_settings)) -> dict:
    """测试 OCR 是否可用(启动器调用)。"""
    payload = ocr_svc.probe_ocr(settings)
    return {"code": 200, "message": "success", "data": payload}
```

- [ ] **Step 3: 运行测试确认通过**

Run: `cd backend && uv run pytest tests/test_diagnostics_ocr_api.py -v`

Expected: 5 个 PASS

注意:测试用 monkeypatch 设置 `OCR_ENABLED`,但 `get_settings()` 有 `lru_cache`。测试里可能需要 `get_settings.cache_clear()`。如果测试因缓存失败,在 conftest.py 的 isolate fixture 里已有 cache_clear 逻辑,应该没问题。如果还是失败,在测试里手动 `from app.core.config import get_settings; get_settings.cache_clear()`。

---

### Task 5: 全量测试 + 静态扫描验证

- [ ] **Step 1: 后端全量测试**

Run: `cd backend && uv run pytest -q`

Expected: 全部 PASS,无 FAIL(包括 P1 的测试 + P2 新增测试)

- [ ] **Step 2: 项目内写操作静态扫描**

Run: `cd backend && uv run pytest tests/test_project_internal_writes.py -v`

Expected: PASS

- [ ] **Step 3: grep 确认无硬编码外部路径**

Run: `cd /Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl && grep -rn "/tmp/\|Path.home()\|expanduser" backend/app/ --include="*.py" | grep -v "# "`

Expected: 无输出

---

### Task 6: 更新 TODO + 提示重启

- [ ] **Step 1: 更新 docs/TODO.md**

把 P2 项标记为 [x],补充结果/验收/部署说明。

- [ ] **Step 2: 提示用户重启**

向用户输出:
```
P2 完成。需要重启 API(uvicorn)让静态挂载生效;worker 不需要重启(没改 worker 代码)。
```

---

## Self-Review

**1. Spec coverage:**
- § 7.1 静态文件挂载 → Task 1 + Task 2 ✓
- § 7.2 OCR 诊断接口 → Task 3 + Task 4 ✓
- 测试要求 → Task 1 + Task 3 + Task 5 ✓

**2. Placeholder scan:** 无 TBD/TODO,所有代码块完整。

**3. Type consistency:**
- `mount_static_frontend_if_exists(app, dist_path)` 函数名在 Task 1/2 一致
- `probe_ocr(settings)` 在 Task 3/4 一致
- `PaddleOCREngine` 已存在于项目,Task 4 复用
- `ocr_enabled` 字段名与项目现有 config.py 一致(需确认,如果字段名不同需调整)
