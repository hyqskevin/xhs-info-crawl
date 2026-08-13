from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token, verify_password
from app.models.user import User
from app.services.audit import record_audit


router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


def _client_meta(request: Request) -> tuple[str, str | None]:
    """提取登录端点用的 client_ip / user_agent。"""
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("user-agent")
    return client_ip, user_agent


def compute_user_permissions(session: Session, user_id: int) -> list[str]:
    """返回用户所有所属分组的权限码并集。

    不再读 role 字段——* 必须由 group 自己 grant（Administrators 组绑定了 10 条具体权限码，
    在 require_permission 端点上与 * 等价）。role 字段仅作为展示/日志用，不再参与授权。

    关联 spec: docs/superpowers/specs/2026-08-13-permission-only-from-groups-design.md
    """
    from app.models.group import GroupPermission, Permission, UserGroup

    codes: set[str] = set()
    rows = (
        session.query(Permission.code)
        .join(GroupPermission, GroupPermission.permission_id == Permission.id)
        .join(UserGroup, UserGroup.group_id == GroupPermission.group_id)
        .filter(UserGroup.user_id == user_id)
        .all()
    )
    codes.update(c for (c,) in rows)
    return sorted(codes)


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    client_ip, user_agent = _client_meta(request)
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None:
        record_audit(
            actor_user_id=None,
            actor_username=payload.username,
            action="login_failed",
            method="POST", path="/api/v1/auth/login", status_code=401,
            client_ip=client_ip, user_agent=user_agent,
            extra={"reason": "user_not_found"},
        )
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not verify_password(payload.password, user.password_hash):
        record_audit(
            actor_user_id=None,
            actor_username=payload.username,
            action="login_failed",
            method="POST", path="/api/v1/auth/login", status_code=401,
            client_ip=client_ip, user_agent=user_agent,
            extra={"reason": "wrong_password"},
        )
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.enabled:
        record_audit(
            actor_user_id=user.id,
            actor_username=user.username,
            action="login_failed",
            resource_type="user", resource_id=user.id, target_label=user.username,
            method="POST", path="/api/v1/auth/login", status_code=403,
            client_ip=client_ip, user_agent=user_agent,
            extra={"reason": "disabled"},
        )
        raise HTTPException(status_code=403, detail="账号已停用")
    settings = get_settings()
    permissions = compute_user_permissions(db, user.id)
    token = create_access_token({"sub": user.username, "role": user.role, "permissions": permissions})
    record_audit(
        actor_user_id=user.id,
        actor_username=user.username,
        action="login_success",
        resource_type="user", resource_id=user.id, target_label=user.username,
        method="POST", path="/api/v1/auth/login", status_code=200,
        client_ip=client_ip, user_agent=user_agent,
    )
    return {"code": 200, "message": "success", "data": {"access_token": token, "token_type": "bearer", "expires_in": settings.jwt_expire_hours * 3600}}