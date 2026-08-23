import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import Settings, get_settings


# alembic migrations 目录:打包版与 dev 模式都从这里读 migration 脚本
_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


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
    - 10 条权限码(9 条具体 + 1 条 '*' 通配),已存在则跳过
    - 2 个内置组:Administrators(绑全部 10 条 含 '*') + Viewers(仅 users:read)
      **幂等补齐**:即便 Administrators/Viewers 已存在(老 v0.5.x 现场),
      本函数也会补上缺失的权限绑(含 '*');不会移除用户手动加的额外绑。
    - role='admin' 用户批量入 Administrators(幂等:user_groups 已存在则跳过)

    关联 spec:
    - docs/superpowers/specs/2026-08-16-packaged-default-login-and-mainthread-window-design.md
    - docs/superpowers/specs/2026-08-16-packaged-admin-permissions-design.md
    - docs/superpowers/specs/2026-08-22-permission-rebind-admin-groups-design.md (老组重绑)

    打包版从不执行 alembic 迁移,所有 IAM 表都空,必须由本函数兜底 seed;
    否则 admin 登录后 token permissions=[] → 所有 require_admin 端点 403。
    老 v0.5.x 用户升级后,本函数自动给老 Administrators 组补齐 '*' + 新 9 条 → 菜单/权限回齐。
    """
    from sqlalchemy.orm import Session

    from app.core.security import hash_password
    from app.models.group import Group, Permission, UserGroup
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

        # 3. Administrators 组——创建或补全
        admins = session.query(Group).filter(Group.name == "Administrators").first()
        if admins is None:
            admins = Group(
                name="Administrators",
                description="内置管理员组,拥有全部权限",
                is_builtin=True,
            )
            session.add(admins)
            session.flush()
        _ensure_group_has_all_permissions(session, admins, include_wildcard=True)

        # 4. Viewers 组——创建或补全
        viewers = session.query(Group).filter(Group.name == "Viewers").first()
        if viewers is None:
            viewers = Group(
                name="Viewers",
                description="内置只读组,仅可查看账号列表",
                is_builtin=True,
            )
            session.add(viewers)
            session.flush()
        _ensure_group_has_minimum_permission(session, viewers, "users:read")

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


def _ensure_group_has_all_permissions(session, group, *, include_wildcard: bool) -> None:
    """幂等补齐组绑全部权限码。

    - 行为:查询当前组已绑 permission_ids,与全表 Permission.id 取差集,缺的批量插入。
    - 不删除任何已有绑——用户手动加的非标准码会被保留。
    - 单次数据库读:SELECT id FROM permissions;SELECT permission_id FROM group_permissions WHERE group_id=?
    - 单次数据库写:仅缺时 INSERT GROUP_PERMISSIONS (group_id, permission_id) ...;不进 SELECT/不重复 INSERT。
    - 性能:启动期对内置组 (Administrators/Viewers) 各调一次;全 IAM 启动期 < 5 ms。

    关联 spec: docs/superpowers/specs/2026-08-22-permission-rebind-admin-groups-design.md
    """
    from app.models.group import GroupPermission, Permission as _Perm  # 局部 import 避免循环依赖

    perm_query = session.query(_Perm)
    if not include_wildcard:
        perm_query = perm_query.filter(_Perm.code != "*")
    all_perms = perm_query.all()
    target_ids = {p.id for p in all_perms}
    if not target_ids:
        return

    bound_ids = {
        row.permission_id
        for row in session.query(GroupPermission.permission_id)
        .filter(GroupPermission.group_id == group.id)
        .all()
    }
    missing_ids = target_ids - bound_ids
    if not missing_ids:
        return
    for pid in missing_ids:
        session.add(GroupPermission(group_id=group.id, permission_id=pid))
    session.flush()


def _ensure_group_has_minimum_permission(session, group, code: str) -> None:
    """幂等保证组至少绑一条 code(Viewers 必 users:read)。

    - 行为:Users 手动删了那条绑也会自动补回。
    - 不删除其它绑。

    关联 spec: docs/superpowers/specs/2026-08-22-permission-rebind-admin-groups-design.md
    """
    from app.models.group import GroupPermission, Permission as _Perm

    perm = session.query(_Perm).filter(_Perm.code == code).one()
    exists = session.query(GroupPermission).filter_by(
        group_id=group.id, permission_id=perm.id
    ).first()
    if exists is None:
        session.add(GroupPermission(group_id=group.id, permission_id=perm.id))
        session.flush()


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
    upgrade_migrations_to_head(selected_engine, selected_settings)
    seed_default_admin(selected_engine)
    if app_settings is not None:
        selected_engine.dispose()


def upgrade_migrations_to_head(engine: Engine, target_settings: Settings | None = None) -> None:
    """启动时把 DB schema 推到 alembic head。

    行为:
    - Base.metadata.create_all 已在上一步跑过(对已存在表不会补列,这是 SQLAlchemy 历史行为)
    - 本函数调 alembic.command.upgrade(cfg, "head") 跑所有 pending migrations,
      把 schema 增量同步到 head(包括 0026/0027 之类的新列)
    - 跑完后用 alembic.command.stamp(cfg, "head") 强制把 alembic_version 设为 head
      (项目历史 0001-0024 用 Base.metadata.create_all,不会更新 alembic_version,
      本函数 stamp 兜底,避免下次启动重跑相同 migration)
    - 失败时**直接抛异常**,lifespan 收到后让 uvicorn 退出非零,launcher 弹"启动失败"
      (设计见 docs/superpowers/specs/2026-08-21-package-startup-auto-migrate-design.md §2.3)

    关联 spec: docs/superpowers/specs/2026-08-21-package-startup-auto-migrate-design.md
    """
    from alembic import command as alembic_command
    from alembic.config import Config as AlembicConfig

    cfg_settings = target_settings or settings
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", cfg_settings.effective_database_url)
    # 跑 pending migrations(从当前 alembic_version 到 head)
    alembic_command.upgrade(cfg, "head")
    # stamp 兜底:把 alembic_version 设为 head,避免下次启动再跑一遍
    alembic_command.stamp(cfg, "head")


def get_db() -> Generator[Session, None, None]:
    database = SessionLocal()
    try:
        yield database
    finally:
        database.close()
