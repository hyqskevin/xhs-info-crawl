"""鉴权 contract 测试：token / 篡改 / role 边界。"""
import time

import jwt
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import create_access_token


def _auth(subject: str = "admin", role: str = "admin") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': subject, 'role': role})}"}


def test_protected_endpoint_rejects_missing_token(client: TestClient) -> None:
    resp = client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 401


def test_protected_endpoint_rejects_tampered_token(client: TestClient) -> None:
    real = create_access_token({"sub": "admin", "role": "admin"})
    # 把 token 中段某字符改了
    head, payload, sig = real.split(".")
    tampered = head + "." + ("X" + payload[1:]) + "." + sig
    resp = client.get(
        "/api/v1/dashboard/summary",
        headers={"Authorization": f"Bearer {tampered}"},
    )
    assert resp.status_code == 401


def test_protected_endpoint_rejects_expired_token(client: TestClient) -> None:
    settings = get_settings()
    expired = jwt.encode(
        {
            "sub": "admin",
            "role": "admin",
            "iat": time.time() - 7200,
            "exp": time.time() - 3600,
        },
        settings.secret_key,
        algorithm="HS256",
    )
    resp = client.get(
        "/api/v1/dashboard/summary",
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert resp.status_code == 401


def test_admin_endpoint_rejects_editor_token(client: TestClient) -> None:
    resp = client.get(
        "/api/v1/settings/cities",
        headers=_auth(subject="editor", role="editor"),
    )
    assert resp.status_code in (401, 403)


def test_valid_admin_token_grants_access(client: TestClient) -> None:
    resp = client.get(
        "/api/v1/dashboard/summary",
        headers=_auth(),
    )
    assert resp.status_code == 200
