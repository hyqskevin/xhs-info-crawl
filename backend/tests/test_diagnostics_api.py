"""仪表盘连接检测（opencli / xhs-login / xhs-pool）API + 单元测试。

关联 spec: docs/superpowers/specs/2026-08-10-diagnostics-opencli-mode-detection-design.md
"""
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.security import create_access_token
from app.services import diagnostics as diagnostics_module


def _admin_token() -> str:
    return create_access_token({"sub": "admin", "role": "admin"})


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_admin_token()}"}


def test_snapshot_returns_three_sections(client: TestClient, monkeypatch) -> None:
    """三合一聚合：三段字段都返回。"""
    monkeypatch.setattr(diagnostics_module, "probe_opencli", lambda s: {"ok": True, "bin": "opencli", "resolved": "/u/l/bin/opencli", "reason": None, "version": "0.1.2"})
    monkeypatch.setattr(diagnostics_module, "probe_xhs_login", lambda s: {"logged_in": True, "username": "小红", "user_id": "u-1", "reason": None})
    monkeypatch.setattr(diagnostics_module, "probe_xhs_pool", lambda s: {"mode": "cdp", "cdp_endpoint": "http://127.0.0.1:9222", "cdp_reachable": True, "sessions": [{"id": "s1"}], "reason": None})

    response = client.get("/api/v1/diagnostics/snapshot", headers=_auth_headers())
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["opencli"]["ok"] is True
    assert body["xhs_login"]["logged_in"] is True
    assert body["xhs_login"]["username"] == "小红"
    assert body["xhs_pool"]["cdp_reachable"] is True
    assert "checked_at" in body


def test_opencli_probe_missing_bin_returns_503(client: TestClient, monkeypatch) -> None:
    """opencli bin 找不到 → 503 + reason 提示设置 OPENCLI_BIN。"""
    def fake_probe(settings):
        return {"ok": False, "bin": settings.opencli_bin, "resolved": None, "reason": "opencli 不在 PATH，请设置 OPENCLI_BIN 环境变量", "version": None}

    monkeypatch.setattr(diagnostics_module, "probe_opencli", fake_probe)

    response = client.get("/api/v1/diagnostics/opencli", headers=_auth_headers())
    assert response.status_code == 503
    assert "OPENCLI_BIN" in response.json()["message"]


def test_xhs_login_probe_authentication_required_returns_200_logged_in_false(client: TestClient, monkeypatch) -> None:
    """whoami 抛 AuthenticationRequired → 200 logged_in=false reason=auth_required。"""
    monkeypatch.setattr(diagnostics_module, "probe_xhs_login", lambda s: {"logged_in": False, "username": None, "user_id": None, "reason": "auth_required"})

    response = client.get("/api/v1/diagnostics/xhs-login", headers=_auth_headers())
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["logged_in"] is False
    assert body["reason"] == "auth_required"


def test_xhs_login_probe_timeout_returns_200_logged_in_false(client: TestClient, monkeypatch) -> None:
    """whoami 超时 → 200 logged_in=false reason=timeout。"""
    monkeypatch.setattr(diagnostics_module, "probe_xhs_login", lambda s: {"logged_in": False, "username": None, "user_id": None, "reason": "timeout"})

    response = client.get("/api/v1/diagnostics/xhs-login", headers=_auth_headers())
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["reason"] == "timeout"


def test_xhs_pool_probe_cdp_unreachable_returns_200_cdp_reachable_false(client: TestClient, monkeypatch) -> None:
    """CDP 不可达 → 200 cdp_reachable=false reason 非空。"""
    monkeypatch.setattr(diagnostics_module, "probe_xhs_pool", lambda s: {"mode": "cdp", "version": None, "version_tuple": None, "cdp_endpoint": s.opencli_cdp_endpoint, "cdp_reachable": False, "sessions": [], "reason": "CDP 端点 http://127.0.0.1:9222 连接被拒"})

    response = client.get("/api/v1/diagnostics/xhs-pool", headers=_auth_headers())
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["cdp_reachable"] is False
    assert body["reason"] and "CDP" in body["reason"]


def test_snapshot_isolates_failures(client: TestClient, monkeypatch) -> None:
    """/snapshot 单段失败不影响其它段返回。"""
    def boom(settings):
        raise RuntimeError("opencli 出问题了")

    monkeypatch.setattr(diagnostics_module, "probe_opencli", boom)
    monkeypatch.setattr(diagnostics_module, "probe_xhs_login", lambda s: {"logged_in": True, "username": "小红", "user_id": "u-1", "reason": None})
    monkeypatch.setattr(diagnostics_module, "probe_xhs_pool", lambda s: {"mode": "cdp", "version": None, "version_tuple": None, "cdp_endpoint": "http://127.0.0.1:9222", "cdp_reachable": True, "sessions": [], "reason": None})

    response = client.get("/api/v1/diagnostics/snapshot", headers=_auth_headers())
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["opencli"]["ok"] is False
    assert body["opencli"]["reason"] and "opencli 出问题了" in body["opencli"]["reason"]
    assert body["xhs_login"]["logged_in"] is True
    assert body["xhs_pool"]["cdp_reachable"] is True


# ── daemon status 输出解析 ──

DAEMON_STATUS_OK = """Daemon: running (PID 1152)
Version: v1.8.5
Uptime: 62h 40m
Extension: connected (v1.0.22)
Profiles: jjm94buu v1.0.22
Memory: 20 MB
Port: 19825
"""

DAEMON_STATUS_EXT_DISCONNECTED = """Daemon: running (PID 1152)
Version: v1.8.5
Extension: disconnected
Port: 19825
"""


def test_parse_daemon_status_healthy() -> None:
    """_parse_daemon_status 解析正常运行输出。"""
    result = diagnostics_module._parse_daemon_status(DAEMON_STATUS_OK)
    assert result["daemon_running"] is True
    assert result["extension_connected"] is True
    assert result["profiles"] == ["jjm94buu"]
    assert result["daemon_port"] == 19825


def test_parse_daemon_status_extension_disconnected() -> None:
    """_parse_daemon_status 解析扩展断开。"""
    result = diagnostics_module._parse_daemon_status(DAEMON_STATUS_EXT_DISCONNECTED)
    assert result["daemon_running"] is True
    assert result["extension_connected"] is False
    assert result["profiles"] == []


# ── 版本解析 _parse_opencli_version ──

def test_parse_opencli_version_formats() -> None:
    """_parse_opencli_version 支持多种格式。"""
    assert diagnostics_module._parse_opencli_version("v1.8.5") == (1, 8, 5)
    assert diagnostics_module._parse_opencli_version("1.8.5") == (1, 8, 5)
    assert diagnostics_module._parse_opencli_version("opencli v1.8.5") == (1, 8, 5)
    assert diagnostics_module._parse_opencli_version("opencli version 1.8.5") == (1, 8, 5)
    assert diagnostics_module._parse_opencli_version("1.8.5\nbuild 123") == (1, 8, 5)


def test_parse_opencli_version_invalid() -> None:
    """无效输入返回 None。"""
    assert diagnostics_module._parse_opencli_version("invalid") is None
    assert diagnostics_module._parse_opencli_version("") is None
    assert diagnostics_module._parse_opencli_version("1.8") is None  # 缺 patch


# ── probe_xhs_pool 版本路由（单元测试，测真实逻辑）──

def test_xhs_pool_daemon_mode_new_version(monkeypatch) -> None:
    """版本≥1.8.5 → daemon 检测 → mode=daemon。"""
    monkeypatch.setattr(diagnostics_module.shutil, "which", lambda name: "/usr/local/bin/opencli")
    monkeypatch.setattr(diagnostics_module, "_safe_version", lambda path, timeout=5.0: "v1.8.5")
    monkeypatch.setattr(diagnostics_module, "_probe_daemon", lambda path: {"success": True, "output": DAEMON_STATUS_OK})

    settings = Settings()
    result = diagnostics_module.probe_xhs_pool(settings)

    assert result["mode"] == "daemon"
    assert result["version"] == "v1.8.5"
    assert result["version_tuple"] == [1, 8, 5]
    assert result["daemon_running"] is True
    assert result["extension_connected"] is True
    assert result["profiles"] == ["jjm94buu"]
    assert result["daemon_port"] == 19825
    assert result["reason"] is None


def test_xhs_pool_daemon_mode_extension_disconnected(monkeypatch) -> None:
    """版本≥1.8.5 + daemon 运行但扩展断开 → mode=daemon, reason 非空。"""
    monkeypatch.setattr(diagnostics_module.shutil, "which", lambda name: "/usr/local/bin/opencli")
    monkeypatch.setattr(diagnostics_module, "_safe_version", lambda path, timeout=5.0: "v1.8.5")
    monkeypatch.setattr(diagnostics_module, "_probe_daemon", lambda path: {"success": True, "output": DAEMON_STATUS_EXT_DISCONNECTED})

    settings = Settings()
    result = diagnostics_module.probe_xhs_pool(settings)

    assert result["mode"] == "daemon"
    assert result["daemon_running"] is True
    assert result["extension_connected"] is False
    assert result["reason"]


def test_xhs_pool_cdp_mode_old_version(monkeypatch) -> None:
    """版本<1.8.5 → cdp 检测 → mode=cdp。"""
    monkeypatch.setattr(diagnostics_module.shutil, "which", lambda name: "/usr/local/bin/opencli")
    monkeypatch.setattr(diagnostics_module, "_safe_version", lambda path, timeout=5.0: "v1.7.2")
    monkeypatch.setattr(diagnostics_module, "_probe_cdp", lambda endpoint, timeout=2.0: (True, None))

    settings = Settings()
    result = diagnostics_module.probe_xhs_pool(settings)

    assert result["mode"] == "cdp"
    assert result["version"] == "v1.7.2"
    assert result["version_tuple"] == [1, 7, 2]
    assert result["cdp_reachable"] is True
    assert result["daemon_running"] is None
    assert result["reason"] is None


def test_xhs_pool_fallback_when_version_unparseable(monkeypatch) -> None:
    """版本解析失败 → 能力探测兜底 → daemon 成功 → mode=daemon。"""
    monkeypatch.setattr(diagnostics_module.shutil, "which", lambda name: "/usr/local/bin/opencli")
    monkeypatch.setattr(diagnostics_module, "_safe_version", lambda path, timeout=5.0: "unknown-format")
    monkeypatch.setattr(diagnostics_module, "_probe_daemon", lambda path: {"success": True, "output": DAEMON_STATUS_OK})

    settings = Settings()
    result = diagnostics_module.probe_xhs_pool(settings)

    assert result["mode"] == "daemon"
    assert result["version"] == "unknown-format"
    assert result["version_tuple"] is None
    assert result["daemon_running"] is True


def test_xhs_pool_fallback_to_cdp_when_daemon_fails(monkeypatch) -> None:
    """版本解析失败 + daemon 失败 → cdp 兜底 → mode=cdp。"""
    monkeypatch.setattr(diagnostics_module.shutil, "which", lambda name: "/usr/local/bin/opencli")
    monkeypatch.setattr(diagnostics_module, "_safe_version", lambda path, timeout=5.0: None)
    monkeypatch.setattr(diagnostics_module, "_probe_daemon", lambda path: {"success": False, "output": None})
    monkeypatch.setattr(diagnostics_module, "_probe_cdp", lambda endpoint, timeout=2.0: (True, None))

    settings = Settings()
    result = diagnostics_module.probe_xhs_pool(settings)

    assert result["mode"] == "cdp"
    assert result["version"] is None
    assert result["version_tuple"] is None
    assert result["cdp_reachable"] is True


def test_xhs_pool_opencli_not_found(monkeypatch) -> None:
    """opencli 不在 PATH → mode=unknown。"""
    monkeypatch.setattr(diagnostics_module.shutil, "which", lambda name: None)

    settings = Settings()
    result = diagnostics_module.probe_xhs_pool(settings)

    assert result["mode"] == "unknown"
    assert result["reason"]
    assert "opencli" in result["reason"]


def test_xhs_pool_all_fail_returns_unknown(monkeypatch) -> None:
    """版本失败 + daemon 失败 + cdp 失败 → mode=unknown。"""
    monkeypatch.setattr(diagnostics_module.shutil, "which", lambda name: "/usr/local/bin/opencli")
    monkeypatch.setattr(diagnostics_module, "_safe_version", lambda path, timeout=5.0: None)
    monkeypatch.setattr(diagnostics_module, "_probe_daemon", lambda path: {"success": False, "output": None})
    monkeypatch.setattr(diagnostics_module, "_probe_cdp", lambda endpoint, timeout=2.0: (False, "CDP 连接被拒"))

    settings = Settings()
    result = diagnostics_module.probe_xhs_pool(settings)

    assert result["mode"] == "unknown"
    assert result["reason"]
