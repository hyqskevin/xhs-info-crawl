"""多小红书账号配置 CRUD + check-login 端点。

关联 spec: docs/superpowers/specs/2026-08-10-multi-xhs-account-design.md
"""
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import require_admin
from app.models.xhs_account import XhsAccount
from app.services.crawler import AuthenticationRequired, VerificationRequired
from app.services.opencli_adapter import OpenCLIAdapter

router = APIRouter(prefix="/xhs-accounts", tags=["xhs-accounts"])
Admin = Annotated[dict[str, str], Depends(require_admin)]
DB = Annotated[Session, Depends(get_db)]


class XhsAccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    remark: str = Field(default="", max_length=256)
    session_name: str = Field(min_length=1, max_length=64)
    enabled: bool = True
    priority: int = 0


class XhsAccountUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    remark: str | None = Field(default=None, max_length=256)
    enabled: bool | None = None
    priority: int | None = None


def _dump(account: XhsAccount) -> dict[str, Any]:
    return {
        "id": account.id,
        "name": account.name,
        "remark": account.remark,
        "session_name": account.session_name,
        "login_status": account.login_status,
        "enabled": account.enabled,
        "priority": account.priority,
        "created_at": account.created_at,
        "updated_at": account.updated_at,
    }


@router.get("")
def list_xhs_accounts(_: Admin, db: DB) -> dict:
    rows = db.scalars(
        select(XhsAccount).order_by(XhsAccount.priority, XhsAccount.id)
    ).all()
    # 与 /settings/{kind} 口径一致：data 直接返回数组，前端 rows.value = res.data.data
    return {"code": 200, "message": "success", "data": [_dump(r) for r in rows]}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_xhs_account(payload: XhsAccountIn, _: Admin, db: DB) -> dict:
    existing = db.scalar(select(XhsAccount).where(XhsAccount.session_name == payload.session_name))
    if existing is not None:
        raise HTTPException(409, f"session_name '{payload.session_name}' 已存在")
    account = XhsAccount(
        name=payload.name,
        remark=payload.remark,
        session_name=payload.session_name,
        enabled=payload.enabled,
        priority=payload.priority,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return {"code": 201, "message": "success", "data": _dump(account)}


@router.put("/{account_id}")
def update_xhs_account(account_id: int, payload: XhsAccountUpdateIn, _: Admin, db: DB) -> dict:
    account = db.get(XhsAccount, account_id)
    if account is None:
        raise HTTPException(404, "账号不存在")
    if payload.name is not None:
        account.name = payload.name
    if payload.remark is not None:
        account.remark = payload.remark
    if payload.enabled is not None:
        account.enabled = payload.enabled
    if payload.priority is not None:
        account.priority = payload.priority
    db.commit()
    db.refresh(account)
    return {"code": 200, "message": "success", "data": _dump(account)}


@router.delete("/{account_id}")
def delete_xhs_account(account_id: int, _: Admin, db: DB) -> dict:
    account = db.get(XhsAccount, account_id)
    if account is not None:
        db.delete(account)
        db.commit()
    return {"code": 200, "message": "success", "data": {"id": account_id}}


@router.post("/{account_id}/check-login")
def check_login(account_id: int, _: Admin, db: DB) -> dict:
    """检查指定账号的登录状态（调 opencli whoami）。

    成功：login_status='logged_in'，返回 logged_in=True + whoami 原始数据。
    未登录/风控：login_status='logged_out'，返回 logged_in=False + 错误信息。
    其他异常：503。
    """
    account = db.get(XhsAccount, account_id)
    if account is None:
        raise HTTPException(404, "账号不存在")
    settings = get_settings()
    try:
        raw = OpenCLIAdapter(settings, session=account.session_name).check_login()
        account.login_status = "logged_in"
        db.commit()
        db.refresh(account)
        # 返回完整 account dump，前端可直接合并到 rows；同时带 login_status 便于 ElTag 刷新
        return {"code": 200, "message": "success", "data": {**_dump(account), "logged_in": True, "raw": raw}}
    except (AuthenticationRequired, VerificationRequired) as exc:
        account.login_status = "logged_out"
        db.commit()
        db.refresh(account)
        return {"code": 200, "message": "success", "data": {**_dump(account), "logged_in": False, "error": str(exc)}}
    except Exception as exc:
        raise HTTPException(503, f"登录检查失败：{exc}") from exc
