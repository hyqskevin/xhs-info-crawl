"""多小红书账号配置模型。

每个 XhsAccount 对应一个独立的 opencli session（Chrome profile），
run_crawl 按 priority 升序选账号，某账号失效时切换到下一个。

关联 spec: docs/superpowers/specs/2026-08-10-multi-xhs-account-design.md
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class XhsAccount(Base):
    __tablename__ = "xhs_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    remark: Mapped[str] = mapped_column(String(256), default="")
    session_name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    login_status: Mapped[str] = mapped_column(String(16), default="unknown")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
