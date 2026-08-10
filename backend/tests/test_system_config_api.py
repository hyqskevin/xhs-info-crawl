"""GET/PUT /api/v1/settings/system-config 测试。"""
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def _temp_env(content: str, tmp_path: Path) -> str:
    """创建临时 .env 文件并返回路径（在 tmp_path 下，不污染系统 tempdir）。"""
    env_file = tmp_path / ".env"
    env_file.write_text(content, encoding="utf-8")
    return str(env_file)


def test_get_system_config_returns_defaults(client: TestClient) -> None:
    """GET 返回配置项（使用当前 Settings 实例）。"""
    from app.core.config import get_settings
    get_settings.cache_clear()
    response = client.get("/api/v1/settings/system-config", headers=_auth())
    assert response.status_code == 200
    data = response.json()["data"]
    assert "minimax_api_key" in data
    assert "minimax_model" in data
    assert "ocr_enabled" in data
    assert "pipeline_stage_max_retries" in data
    assert "xhs_search_target_count" in data
    assert "search_limit" in data
    assert "weekly_search_limit" in data
    assert "consecutive_note_failure_limit" in data
    assert "activity_future_window_days" in data


def test_put_system_config_writes_env_and_returns_updated(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """PUT 更新部分字段，写入临时 .env，返回更新后的值。"""
    env_path = _temp_env("MINIMAX_MODEL=OldModel\nSEARCH_LIMIT=30\n", tmp_path)
    try:
        monkeypatch.setattr("app.core.config.Settings.model_config", {
            "env_file": env_path, "env_file_encoding": "utf-8", "extra": "ignore",
        })
        monkeypatch.setattr("app.api.v1.settings.get_settings", lambda: _import_settings())

        response = client.put(
            "/api/v1/settings/system-config",
            json={"minimax_model": "NewModel", "search_limit": 60},
            headers=_auth(),
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["minimax_model"] == "NewModel"
        assert data["search_limit"] == 60

        # 验证 .env 文件内容
        content = Path(env_path).read_text()
        assert "MINIMAX_MODEL=NewModel" in content
        assert "SEARCH_LIMIT=60" in content
    finally:
        os.unlink(env_path)


def test_put_system_config_preserves_comments_and_other_keys(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """PUT 保留 .env 中的注释和未修改的 key。"""
    env_content = "# 这是注释\nMINIMAX_MODEL=MiniMax-M3\nSEARCH_LIMIT=50\n\n# 另一条注释\nWEEKLY_SEARCH_LIMIT=500\n"
    env_path = _temp_env(env_content, tmp_path)
    try:
        monkeypatch.setattr("app.core.config.Settings.model_config", {
            "env_file": env_path, "env_file_encoding": "utf-8", "extra": "ignore",
        })
        monkeypatch.setattr("app.api.v1.settings.get_settings", lambda: _import_settings())

        client.put(
            "/api/v1/settings/system-config",
            json={"search_limit": 100},
            headers=_auth(),
        )
        content = Path(env_path).read_text()
        assert "# 这是注释" in content
        assert "# 另一条注释" in content
        assert "MINIMAX_MODEL=MiniMax-M3" in content
        assert "SEARCH_LIMIT=100" in content
        assert "WEEKLY_SEARCH_LIMIT=500" in content
    finally:
        os.unlink(env_path)


def test_put_system_config_appends_new_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """PUT 不存在的 key 追加到 .env 末尾。"""
    env_path = _temp_env("MINIMAX_MODEL=MiniMax-M3\n", tmp_path)
    try:
        monkeypatch.setattr("app.core.config.Settings.model_config", {
            "env_file": env_path, "env_file_encoding": "utf-8", "extra": "ignore",
        })
        monkeypatch.setattr("app.api.v1.settings.get_settings", lambda: _import_settings())

        client.put(
            "/api/v1/settings/system-config",
            json={"pipeline_stage_max_retries": 5},
            headers=_auth(),
        )
        content = Path(env_path).read_text()
        assert "MINIMAX_MODEL=MiniMax-M3" in content
        assert "PIPELINE_STAGE_MAX_RETRIES=5" in content
    finally:
        os.unlink(env_path)


def test_put_system_config_writes_opencli_bin(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """PUT opencli_bin 写入 .env 并在 GET 中返回。"""
    env_path = _temp_env("MINIMAX_MODEL=MiniMax-M3\nOPENCLI_BIN=opencli\n", tmp_path)
    try:
        monkeypatch.setattr("app.core.config.Settings.model_config", {
            "env_file": env_path, "env_file_encoding": "utf-8", "extra": "ignore",
        })
        monkeypatch.setattr("app.api.v1.settings.get_settings", lambda: _import_settings())

        response = client.put(
            "/api/v1/settings/system-config",
            json={"opencli_bin": "/Users/kevin_w/.nvm/versions/node/v22.18.0/bin/opencli"},
            headers=_auth(),
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["opencli_bin"] == "/Users/kevin_w/.nvm/versions/node/v22.18.0/bin/opencli"

        content = Path(env_path).read_text()
        assert "OPENCLI_BIN=/Users/kevin_w/.nvm/versions/node/v22.18.0/bin/opencli" in content
        # 其他 key 未受影响
        assert "MINIMAX_MODEL=MiniMax-M3" in content
    finally:
        os.unlink(env_path)


def test_put_system_config_syncs_os_environ(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """PUT 写 .env 后同步更新 os.environ，避免 pydantic_settings 读到旧 env 值。

    模拟 uvicorn 启动时 ``set -a && source .env`` 将旧值注入 os.environ 的场景。
    若不同步 os.environ，Settings() 重建时优先读 os.environ 的旧值，PUT 等于无效。
    """
    env_path = _temp_env("OPENCLI_BIN=/old/path/opencli\n", tmp_path)
    monkeypatch.setenv("OPENCLI_BIN", "/old/path/opencli")
    try:
        monkeypatch.setattr("app.core.config.Settings.model_config", {
            "env_file": env_path, "env_file_encoding": "utf-8", "extra": "ignore",
        })
        monkeypatch.setattr("app.api.v1.settings.get_settings", lambda: _import_settings())

        response = client.put(
            "/api/v1/settings/system-config",
            json={"opencli_bin": "/new/path/opencli"},
            headers=_auth(),
        )
        assert response.status_code == 200
        # .env 文件已更新
        assert "OPENCLI_BIN=/new/path/opencli" in Path(env_path).read_text()
        # os.environ 也必须同步更新，否则 Settings() 重建时仍读旧值
        assert os.environ.get("OPENCLI_BIN") == "/new/path/opencli"
        # GET 返回新值
        assert response.json()["data"]["opencli_bin"] == "/new/path/opencli"
    finally:
        os.unlink(env_path)


def _import_settings():
    """重新导入 Settings 以获取最新 .env 配置（测试用）。"""
    from app.core.config import Settings
    return Settings()