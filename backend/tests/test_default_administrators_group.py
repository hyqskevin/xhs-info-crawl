"""端到端：admin 登录后仍可访问既有 admin-only 端点；editor 不可。

关联 spec: docs/superpowers/specs/2026-08-12-system-admin-design.md §4
"""
import pytest

from app.core.security import create_access_token, hash_password
from app.models.group import Group, UserGroup
from app.models.user import User


def _admin_token():
    return create_access_token({
        "sub": "admin", "role": "admin", "permissions": ["*"],
    })


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def seeded(db_session):
    """每测试 fresh DB seed：内置 admin / Administrators / Viewers / 9 条权限码。

    对应 migration 0020 的 PERMISSION_SEED；测试库不跑 alembic，手工建。
    """
    admin = User(
        username="admin",
        password_hash=hash_password("Admin@123"),
        role="admin",
        display_name="admin",
        enabled=True,
    )
    db_session.add(admin)
    db_session.flush()

    # 9 条权限码 + Administrators（绑全部 9 条）+ Viewers（仅 users:read）
    permission_seed = [
        ("users:manage", "账号管理"),
        ("users:read", "查看账号列表"),
        ("settings:write", "配置中心写"),
        ("tasks:crawl", "发起/停止抓取任务"),
        ("notes:review", "审核推文"),
        ("reports:generate", "生成周报"),
        ("notes:edit", "编辑推文"),
        ("activities:edit", "编辑子活动"),
        ("duplicates:resolve", "merge 重复项"),
        ("notes:delete", "删除推文"),
    ]
    rows = []
    from app.models.group import GroupPermission, Permission  # noqa: PLC0415
    for code, desc in permission_seed:
        rows.append(Permission(code=code, description=desc, is_builtin=True))
    db_session.add_all(rows)
    db_session.flush()

    admins = Group(name="Administrators", description="内置管理员组", is_builtin=True)
    viewers = Group(name="Viewers", description="内置只读组", is_builtin=True)
    db_session.add_all([admins, viewers])
    db_session.flush()

    for p in rows:
        db_session.add(GroupPermission(group_id=admins.id, permission_id=p.id))
    read_p = db_session.query(Permission).filter_by(code="users:read").one()
    db_session.add(GroupPermission(group_id=viewers.id, permission_id=read_p.id))
    db_session.add(UserGroup(user_id=admin.id, group_id=admins.id))
    db_session.commit()
    return {
        "admin_id": admin.id,
        "administrators_id": admins.id,
        "viewers_id": viewers.id,
    }


def test_admin_can_list_permissions(client, seeded):
    """admin 凭 * 能列权限字典。"""
    r = client.get("/api/v1/permissions", headers=_headers(_admin_token()))
    assert r.status_code == 200


def test_editor_without_users_manage_gets_403_on_user_create(client, seeded):
    """editor 凭 notes:review 想创建用户，应 403。"""
    token = create_access_token({
        "sub": "alice", "role": "editor", "permissions": ["notes:review"],
    })
    r = client.post(
        "/api/v1/users",
        json={"username": "bob", "password": "Abc@12345", "is_admin": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


def test_new_account_with_is_admin_joins_administrators(client, seeded, db_session):
    """is_admin=true 创建账号后自动入 Administrators 组。"""
    r = client.post(
        "/api/v1/users",
        json={"username": "alice_new_rbac", "password": "Abc@12345", "is_admin": True},
        headers=_headers(_admin_token()),
    )
    assert r.status_code == 201
    user = db_session.query(User).filter_by(username="alice_new_rbac").one()
    groups = (
        db_session.query(Group)
        .join(UserGroup, UserGroup.group_id == Group.id)
        .filter(UserGroup.user_id == user.id).all()
    )
    names = [g.name for g in groups]
    assert "Administrators" in names


def test_existing_admin_only_endpoints_still_200_for_admin(client, seeded):
    """admin 仍可访问既有 admin-only 端点（require_admin 通过 role=admin 或 * 通配）。

    /api/v1/audit-logs（Task 6 实现的 admin-only 端点）做烟测。
    """
    r = client.get("/api/v1/audit-logs", headers=_headers(_admin_token()))
    assert r.status_code == 200


def test_legacy_token_admin_role_can_access_admin_endpoint(client, seeded):
    """旧 token 没有 permissions 字段但 role=admin，仍可访问既有 admin-only 端点。

    spec §4.3 高风险：现有 admin token 没有 permissions 字段；require_admin 内部
    兼容 `role=admin` 与 `*` 通配，必须对旧 token 放行。

    验证用真正的 require_admin 端点（/api/v1/tasks），不挑 /audit-logs 因为它
    走 require_permission("users:manage") 是 Task 6 新增语义，本测试只覆盖
    既有 require_admin 端点的兼容路径。
    """
    import jwt as pyjwt
    from app.core.config import get_settings

    settings = get_settings()
    legacy = pyjwt.encode(
        {"sub": "admin", "role": "admin"},
        settings.secret_key, algorithm="HS256",
    )
    # 既有 admin-only 端点（GET /api/v1/tasks，纯 require_admin，无副作用）
    r = client.get(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {legacy}"},
    )
    # 旧 token role=admin → require_admin 放行
    assert r.status_code == 200