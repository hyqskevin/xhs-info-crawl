"""poster_templates API + minimax vision path 测试。"""
import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.poster import PosterTemplate


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def test_list_poster_templates_empty(client: TestClient) -> None:
    response = client.get("/api/v1/settings/poster-templates", headers=_auth())
    assert response.status_code == 200
    assert response.json()["data"]["items"] == []


def test_create_poster_template(client: TestClient) -> None:
    response = client.post(
        "/api/v1/settings/poster-templates",
        json={
            "name": "橙橙周末合集",
            "description": "橙底白字，标题分两行",
            "html_template": "<div class='poster'><h1>{{title}}</h1>{{items}}</div>",
            "css_text": ".poster{background:#F26B2C;color:#fff;width:1242px;padding:60px}",
        },
        headers=_auth(),
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["name"] == "橙橙周末合集"
    assert body["source"] == "manual"
    assert body["html_template"].startswith("<div")


def test_create_poster_template_duplicate_name_409(client: TestClient) -> None:
    client.post(
        "/api/v1/settings/poster-templates",
        json={"name": "DUP", "html_template": "<div/>"},
        headers=_auth(),
    )
    response = client.post(
        "/api/v1/settings/poster-templates",
        json={"name": "DUP", "html_template": "<p/>"},
        headers=_auth(),
    )
    assert response.status_code == 409


def test_update_poster_template_keeps_parsed_meta(client: TestClient, db_session: Session) -> None:
    create = client.post(
        "/api/v1/settings/poster-templates",
        json={"name": "META-T", "html_template": "<x/>", "parsed_meta": {"fonts": ["PingFang"]}},
        headers=_auth(),
    )
    tid = create.json()["data"]["id"]

    update = client.put(
        f"/api/v1/settings/poster-templates/{tid}",
        json={"name": "META-T", "html_template": "<y/>"},
        headers=_auth(),
    )
    assert update.status_code == 200
    fetched = db_session.get(PosterTemplate, tid)
    assert fetched.parsed_meta == {"fonts": ["PingFang"]}


def test_delete_poster_template(client: TestClient) -> None:
    create = client.post(
        "/api/v1/settings/poster-templates",
        json={"name": "DEL", "html_template": "<z/>"},
        headers=_auth(),
    )
    tid = create.json()["data"]["id"]
    response = client.delete(f"/api/v1/settings/poster-templates/{tid}", headers=_auth())
    assert response.status_code == 200
    fetched = client.get(f"/api/v1/settings/poster-templates/{tid}", headers=_auth())
    assert fetched.status_code == 404


def test_parse_from_image_without_api_key_returns_503(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import config as config_module

    monkeypatch.setattr(
        config_module.get_settings(),
        "minimax_api_key",
        "",
    )
    # 重读 settings — 直接 setenv 然后 reload。
    monkeypatch.setenv("MINIMAX_API_KEY", "")
    img_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 100
    response = client.post(
        "/api/v1/settings/poster-templates/parse-from-image",
        files={"image": ("sample.png", io.BytesIO(img_bytes), "image/png")},
        headers=_auth(),
    )
    assert response.status_code in (503,)


def test_parse_from_image_with_mocked_vision(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api.v1 import poster_templates as pt_module
    from app.core import config as config_module

    # 给 MINIMAX_API_KEY 一个 fake 值，让 settings.minimax_api_key 非空
    monkeypatch.setattr(config_module.get_settings(), "minimax_api_key", "fake-key-for-test")
    # 给 Minimax API endpoint client 替换 fake
    fake = {
        "html_template": "<div class='poster'><h1>橙色周末</h1><div>row-1</div></div>",
        "css_text": ".poster{background:#F26B2C;color:#fff}",
        "parsed_meta": {"fonts": ["PingFang SC"], "colors": {"primary": "#F26B2C"}, "emoji": ["🕐", "📍"]},
        "name_suggestion": "橙橙风格",
    }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def vision_chat(self, *args, **kwargs):
            return fake

    monkeypatch.setattr(pt_module, "MiniMaxClient", FakeClient)
    img = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 256)
    response = client.post(
        "/api/v1/settings/poster-templates/parse-from-image",
        files={"image": ("sample.png", img, "image/png")},
        headers=_auth(),
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["html_template"].startswith("<div")
    assert body["parsed_meta"]["colors"]["primary"] == "#F26B2C"
    assert body["name_suggestion"] == "橙橙风格"


def test_parse_from_image_too_large_rejected(client: TestClient) -> None:
    big = b"\x89PNG" + b"\xff" * (8 * 1024 * 1024)
    response = client.post(
        "/api/v1/settings/poster-templates/parse-from-image",
        files={"image": ("big.png", io.BytesIO(big), "image/png")},
        headers=_auth(),
    )
    assert response.status_code in (413,)


def test_parse_from_image_non_image_content_type_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/settings/poster-templates/parse-from-image",
        files={"image": ("a.txt", io.BytesIO(b"hello"), "text/plain")},
        headers=_auth(),
    )
    assert response.status_code == 415
