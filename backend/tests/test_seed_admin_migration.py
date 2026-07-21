"""alembic migration 0012_seed_admin 单元测试。

注：alembic 在多数 env 用 sync DB；这里我们直接 import migration 模块调 upgrade/downgrade，
并把 bind 指到一个临时 SQLite（用 Base.metadata 同步创建 schema）。
"""
import importlib
import logging
import os
from pathlib import Path

import pytest
from pwdlib import PasswordHash
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models.user import User


@pytest.fixture
def migration_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Session:
    """给 migration 测试用的隔离 sqlite。"""
    db_path = tmp_path / "seed_admin.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = session_maker()

    # 使 migration 文件用我们的 engine：patch alembic op.get_bind
    from alembic import op as alembic_op

    monkeypatch.setattr(alembic_op, "get_bind", lambda: session)

    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _load_migration_module():
    """Import `migrations.versions.0012_seed_admin` as a module."""
    import importlib.util
    import sys

    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root))
    spec = importlib.util.spec_from_file_location(
        "seed_admin_migration",
        project_root / "migrations" / "versions" / "0012_seed_admin.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seed_admin_when_users_empty(migration_db: Session) -> None:
    # 不设 env，应当使用 Admin@123
    os.environ.pop("INITIAL_ADMIN_PASSWORD", None)
    migration = _load_migration_module()

    migration.upgrade()

    rows = migration_db.scalars(select(User)).all()
    assert len(rows) == 1
    admin = rows[0]
    assert admin.username == "admin"
    assert admin.role == "admin"
    assert admin.password_hash and not admin.password_hash.startswith("Admin@123")


def test_seed_admin_skips_when_already_exists(migration_db: Session) -> None:
    migration_db.add(
        User(
            username="admin",
            password_hash="existing-hash",
            role="admin",
        )
    )
    migration_db.commit()

    migration = _load_migration_module()
    migration.upgrade()

    rows = migration_db.scalars(select(User)).all()
    assert len(rows) == 1
    assert rows[0].password_hash == "existing-hash"


def test_seed_admin_uses_environment_password(migration_db: Session) -> None:
    monkey_env = {"INITIAL_ADMIN_PASSWORD": "S3cure!!-override"}
    for k, v in monkey_env.items():
        os.environ[k] = v
    try:
        migration = _load_migration_module()
        migration.upgrade()

        admin = migration_db.scalar(select(User))
        assert admin is not None
        assert PasswordHash.recommended().verify("S3cure!!-override", admin.password_hash)
    finally:
        os.environ.pop("INITIAL_ADMIN_PASSWORD", None)


def test_seed_admin_emits_warning_when_default(migration_db: Session, caplog: pytest.LogCaptureFixture) -> None:
    os.environ.pop("INITIAL_ADMIN_PASSWORD", None)
    migration = _load_migration_module()

    with caplog.at_level(logging.WARNING):
        migration.upgrade()

    assert any("INITIAL_ADMIN_PASSWORD" in record.message for record in caplog.records)


def test_downgrade_removes_admin_user(migration_db: Session) -> None:
    os.environ.pop("INITIAL_ADMIN_PASSWORD", None)
    migration = _load_migration_module()
    migration.upgrade()
    assert migration_db.scalar(select(func.count()).select_from(User)) == 1

    migration.downgrade()

    assert migration_db.scalar(select(func.count()).select_from(User)) == 0
