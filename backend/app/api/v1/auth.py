from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token, verify_password
from app.models.user import User


router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


def compute_user_permissions(session: Session, user_id: int) -> list[str]:
    """返回用户所有所属分组的权限码并集；若 role=admin 额外附加 '*'。"""
    from app.models.group import GroupPermission, Permission, UserGroup
    from app.models.user import User

    user = session.get(User, user_id)
    codes: set[str] = set()
    if user is not None and user.role == "admin":
        codes.add("*")
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
def login(payload: LoginRequest, db: Annotated[Session, Depends(get_db)]):
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    settings = get_settings()
    permissions = compute_user_permissions(db, user.id)
    token = create_access_token({"sub": user.username, "role": user.role, "permissions": permissions})
    return {"code": 200, "message": "success", "data": {"access_token": token, "token_type": "bearer", "expires_in": settings.jwt_expire_hours * 3600}}
