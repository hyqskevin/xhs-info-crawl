"""验证后端启动时挂载 frontend/dist 静态文件(打包版需要)。

关联 spec: docs/superpowers/specs/2026-08-10-one-click-packaging-design.md § 7.1
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_static_frontend_mounted_when_dist_exists(tmp_path: Path) -> None:
    """frontend/dist 存在时,后端应挂载 StaticFiles,根路径返回 index.html。"""
    fake_dist = tmp_path / "frontend" / "dist"
    fake_dist.mkdir(parents=True)
    (fake_dist / "index.html").write_text("<html><body>main app</body></html>")

    app = FastAPI()
    from app.main import mount_static_frontend_if_exists
    mount_static_frontend_if_exists(app, fake_dist)

    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "main app" in resp.text


def test_static_frontend_not_mounted_when_dist_missing(tmp_path: Path) -> None:
    """frontend/dist 不存在时,后端不挂载静态文件,根路径返回 404。"""
    nonexistent = tmp_path / "nonexistent-dist"

    app = FastAPI()
    from app.main import mount_static_frontend_if_exists
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

    app = FastAPI()
    from app.main import mount_static_frontend_if_exists
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

    app = FastAPI()
    from app.main import mount_static_frontend_if_exists
    mount_static_frontend_if_exists(app, fake_dist)

    with TestClient(app) as client:
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "SPA" in resp.text
