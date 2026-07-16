import re
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash

from app.core.config import get_settings


password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    return password_hash.verify(password, encoded)


def validate_password_strength(password: str) -> bool:
    return bool(len(password) >= 8 and re.search(r"[A-Z]", password) and re.search(r"[a-z]", password) and re.search(r"\d", password) and re.search(r"[^A-Za-z0-9]", password))


def create_access_token(data: dict[str, object], expires_delta: timedelta | None = None) -> str:
    settings = get_settings()
    payload = dict(data)
    payload["exp"] = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=settings.jwt_expire_hours))
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def get_current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> dict[str, str]:
    if credentials is None:
        raise HTTPException(status_code=401, detail="未提供认证凭据")
    try:
        payload = jwt.decode(credentials.credentials, get_settings().secret_key, algorithms=["HS256"])
        return {"username": str(payload["sub"]), "role": str(payload["role"])}
    except (jwt.InvalidTokenError, KeyError) as exc:
        raise HTTPException(status_code=401, detail="认证凭据无效或已过期") from exc


def require_admin(user: Annotated[dict[str, str], Depends(get_current_user)]) -> dict[str, str]:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="权限不足")
    return user
