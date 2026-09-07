from datetime import datetime

from app.core.timeutil import now_cn

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _now() -> datetime:
    """统一时间戳默认值/自动更新值;UTC 避免时区漂移。"""
    return now_cn()


class WeeklyReport(Base):
    __tablename__ = "weekly_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    week: Mapped[str] = mapped_column(String(16), index=True)
    # 可读名称，如「2026-W33 · 宁波 · 关键词：咖啡」
    name: Mapped[str] = mapped_column(String(256), default="")
    # 规范化后的组合签名，用于「完整组合相同 → 视为同一份」判重
    signature: Mapped[str] = mapped_column(String(512), index=True)
    # 生成时使用的筛选条件（JSON list）
    keyword_group_ids: Mapped[str] = mapped_column(Text, default="[]")
    keywords: Mapped[str] = mapped_column(Text, default="[]")
    blogger_group_ids: Mapped[str] = mapped_column(Text, default="[]")
    blogger_ids: Mapped[str] = mapped_column(Text, default="[]")
    cities: Mapped[str] = mapped_column(Text)
    activity_count: Mapped[int] = mapped_column(Integer, default=0)
    note_count: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # onupdate=_now:与 Schedule / XhsAccount / Activity / SearchUsage 同款语义;
    # 任何 SQLAlchemy UPDATE 都会刷新 updated_at,API 端点不再需要手工赋值。
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
