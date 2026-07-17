from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

def now(): return datetime.now(timezone.utc)

class City(Base):
    __tablename__ = "cities"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    recent_filter: Mapped[str] = mapped_column(String(16), default="一周内")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Keyword(Base):
    __tablename__ = "keywords"
    id: Mapped[int] = mapped_column(primary_key=True)
    word: Mapped[str] = mapped_column(String(128))
    city_code: Mapped[str] = mapped_column(String(32), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class Blogger(Base):
    __tablename__ = "bloggers"
    id: Mapped[int] = mapped_column(primary_key=True)
    platform_user_id: Mapped[str] = mapped_column(String(128), unique=True)
    username: Mapped[str] = mapped_column(String(128))
    profile_url: Mapped[str] = mapped_column(String(512))
    city_code: Mapped[str] = mapped_column(String(32), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
