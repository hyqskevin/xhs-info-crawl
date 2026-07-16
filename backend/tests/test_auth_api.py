from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, validate_password_strength
from app.models.user import User


@pytest.fixture
def users(db_session: Session) -> None:
    db_session.add_all(
        [
            User(username="admin", password_hash=hash_password("Admin@123"), role="admin"),
            User(username="editor", password_hash=hash_password("Editor@123"), role="editor"),
        ]
    )
    db_session.commit()


def login(client: TestClient, username: str = "admin", password: str = "Admin@123") -> str:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    return response.json()["data"]["access_token"]


def test_login_with_correct_credentials(client: TestClient, users: None) -> None:
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "Admin@123"})
    assert response.status_code == 200
    assert response.json()["data"]["access_token"].count(".") == 2
    assert response.json()["data"]["token_type"] == "bearer"
    assert response.json()["data"]["expires_in"] == 86400


@pytest.mark.parametrize("username,password", [("admin", "WrongPass"), ("missing", "anything")])
def test_login_rejects_invalid_credentials(client: TestClient, users: None, username: str, password: str) -> None:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 401
    assert response.json()["message"] == "用户名或密码错误"


def test_protected_route_rejects_missing_invalid_and_expired_tokens(client: TestClient) -> None:
    assert client.get("/api/v1/activities").status_code == 401
    assert client.get("/api/v1/activities", headers={"Authorization": "Bearer invalid.token.here"}).status_code == 401
    expired = create_access_token({"sub": "admin", "role": "admin"}, timedelta(seconds=-1))
    assert client.get("/api/v1/activities", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_editor_cannot_access_admin_route(client: TestClient, users: None) -> None:
    token = login(client, "editor", "Editor@123")
    response = client.delete("/api/v1/settings/cities/1", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_admin_is_not_forbidden_from_admin_route(client: TestClient, users: None) -> None:
    token = login(client)
    response = client.delete("/api/v1/settings/cities/1", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code != 403


@pytest.mark.parametrize(
    ("password", "expected"),
    [("123456", False), ("abcdef", False), ("abc123", False), ("Abc123!@", True), ("MyP@ssw0rd2025", True)],
)
def test_password_strength_validation(password: str, expected: bool) -> None:
    assert validate_password_strength(password) is expected


@pytest.mark.skip(reason="TC-AUTH-010 is optional and excluded from phase-one scope")
def test_token_refresh() -> None:
    pass
