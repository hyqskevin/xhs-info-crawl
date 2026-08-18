import os
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import Settings, get_settings


class Base(DeclarativeBase):
    pass


def create_database_engine(settings: Settings) -> Engine:
    connect_args = {"check_same_thread": False} if settings.effective_database_url.startswith("sqlite") else {}
    return create_engine(settings.effective_database_url, connect_args=connect_args)


settings = get_settings()
engine = create_database_engine(settings)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# 与 backend/migrations/versions/0020_system_admin.py 的 PERMISSION_SEED 保持一致
# 任何内置权限码新增/删除,这里必须同步更新。
_PERMISSION_SEED: tuple[tuple[str, str], ...] = (
    ("users:read", "查看账号列表"),
    ("users:write", "新增/修改账号"),
    ("tasks:run", "发起/续跑抓取任务"),
    ("tasks:stop", "停止/结束抓取任务"),
    ("blogs:write", "新增/修改博主配置"),
    ("reports:generate", "生成周报"),
    ("notes:edit", "编辑推文"),
    ("activities:edit", "编辑子活动"),
    ("duplicates:resolve", "merge/ignore 重复项"),
    ("notes:delete", "删除推文"),
)


def seed_default_iam(db_engine: Engine) -> None:
    """幂等 seed 默认 IAM(用户/组/权限/绑定)。

    - 内置 admin/Admin@123 用户(已有则不覆盖密码)
    - 10 条权限码(9 条具体 + 1 条 '*' 通配)
    - 2 个内置组:Administrators(绑全部 10 条) + Viewers(仅 users:read)
    - role='admin' 用户批量入 Administrators(幂等)

    关联 spec:
    - docs/superpowers/specs/2026-08-16-packaged-default-login-and-mainthread-window-design.md
    - docs/superpowers/specs/2026-08-16-packaged-admin-permissions-design.md

    打包版从不执行 alembic 迁移,所有 IAM 表都空,必须由本函数兜底 seed;
    否则 admin 登录后 token permissions=[] → 所有 require_admin 端点 403。
    """
    from sqlalchemy.orm import Session

    from app.core.security import hash_password
    from app.models.group import Group, GroupPermission, Permission, UserGroup
    from app.models.user import User

    password = os.environ.get("INITIAL_ADMIN_PASSWORD") or "Admin@123"

    with Session(db_engine) as session:
        # 1. 默认 admin 用户(幂等:已有则不覆盖密码)
        if session.query(User).filter(User.username == "admin").first() is None:
            session.add(
                User(
                    username="admin",
                    password_hash=hash_password(password),
                    role="admin",
                    enabled=True,
                )
            )
            session.flush()

        # 2. 权限码(10 条:9 + '*'),已存在则跳过
        existing_codes = {p.code for p in session.query(Permission).all()}
        for code, desc in _PERMISSION_SEED + (("*", "管理员通配(Administrators 组内置)"),):
            if code in existing_codes:
                continue
            session.add(
                Permission(code=code, description=desc, is_builtin=True)
            )
        session.flush()

        # 3. Administrators 组(绑全部 10 条),幂等
        admins = session.query(Group).filter(Group.name == "Administrators").first()
        if admins is None:
            admins = Group(
                name="Administrators",
                description="内置管理员组,拥有全部权限",
                is_builtin=True,
            )
            session.add(admins)
            session.flush()
            all_perm_ids = [p.id for p in session.query(Permission).all()]
            for pid in all_perm_ids:
                session.add(GroupPermission(group_id=admins.id, permission_id=pid))

        # 4. Viewers 组(仅 users:read),幂等
        viewers = session.query(Group).filter(Group.name == "Viewers").first()
        if viewers is None:
            viewers = Group(
                name="Viewers",
                description="内置只读组,仅可查看账号列表",
                is_builtin=True,
            )
            session.add(viewers)
            session.flush()
            read_perm = session.query(Permission).filter(Permission.code == "users:read").one()
            session.add(GroupPermission(group_id=viewers.id, permission_id=read_perm.id))

        # 5. role='admin' 用户批量入 Administrators(幂等:user_groups 已存在则跳过)
        existing_links = {
            (ug.user_id, ug.group_id)
            for ug in session.query(UserGroup)
            .filter(UserGroup.group_id == admins.id)
            .all()
        }
        admin_user_ids = [
            u.id for u in session.query(User).filter(User.role == "admin").all()
        ]
        for uid in admin_user_ids:
            if (uid, admins.id) in existing_links:
                continue
            session.add(UserGroup(user_id=uid, group_id=admins.id))

        session.commit()


# 向后兼容别名(老 spec 仍引用 seed_default_admin)
def seed_default_admin(db_engine: Engine) -> None:
    """保留旧 API,实际调 seed_default_iam。

    关联 spec: docs/superpowers/specs/2026-08-16-packaged-default-login-and-mainthread-window-design.md
    """
    seed_default_iam(db_engine)


def init_database(app_settings: Settings | None = None) -> None:
    from app.models import activity, audit, blogger_city, blogger_group, config, duplicate, group, keyword_group, note, poster, report, schedule, search_usage, task, user, xhs_account  # noqa: F401

    selected_settings = app_settings or settings
    selected_settings.ensure_runtime_directories()
    selected_engine = engine if app_settings is None else create_database_engine(selected_settings)
    with selected_engine.begin() as connection:
        connection.execute(text("SELECT 1"))
    Base.metadata.create_all(selected_engine)
    seed_default_admin(selected_engine)
    if app_settings is not None:
        selected_engine.dispose()


def get_db() -> Generator[Session, None, None]:
    database = SessionLocal()
    try:
        yield database
    finally:
        database.close()
