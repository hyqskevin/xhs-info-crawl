"""操作日志查询 API。

关联 spec: docs/superpowers/specs/2026-08-12-system-admin-design.md §3.3
"""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import require_permission
from app.models.audit import AuditLog


router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


class AuditLogOut(BaseModel):
    id: int
    actor_user_id: int | None
    actor_username: str
    action: str
    resource_type: str | None
    resource_id: int | None
    target_label: str | None
    method: str
    path: str
    status_code: int
    client_ip: str
    user_agent: str | None
    extra: str | None
    created_at: datetime


class AuditLogPage(BaseModel):
    total: int
    items: list[AuditLogOut]


@router.get("", response_model=AuditLogPage)
def list_audit_logs(
    actor_username: str | None = Query(None),
    action: list[str] | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    _: Annotated[dict, Depends(require_permission("users:manage"))] = None,
    db=Depends(get_db),
):
    stmt = select(AuditLog)
    count_stmt = select(AuditLog)
    if actor_username:
        stmt = stmt.where(AuditLog.actor_username.contains(actor_username))
        count_stmt = count_stmt.where(AuditLog.actor_username.contains(actor_username))
    if action:
        stmt = stmt.where(AuditLog.action.in_(action))
        count_stmt = count_stmt.where(AuditLog.action.in_(action))
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= date_from)
        count_stmt = count_stmt.where(AuditLog.created_at >= date_from)
    if date_to:
        stmt = stmt.where(AuditLog.created_at <= date_to)
        count_stmt = count_stmt.where(AuditLog.created_at <= date_to)
    total = len(db.execute(count_stmt).scalars().all())
    rows = (
        db.execute(stmt.order_by(AuditLog.id.desc()).offset((page - 1) * size).limit(size))
        .scalars()
        .all()
    )
    return AuditLogPage(
        total=total,
        items=[
            AuditLogOut(
                id=r.id, actor_user_id=r.actor_user_id, actor_username=r.actor_username,
                action=r.action, resource_type=r.resource_type, resource_id=r.resource_id,
                target_label=r.target_label, method=r.method, path=r.path,
                status_code=r.status_code, client_ip=r.client_ip,
                user_agent=r.user_agent, extra=r.extra, created_at=r.created_at,
            ) for r in rows
        ],
    )