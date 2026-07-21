# Alembic Migration 0012: 兜底 seed admin 用户

> 状态：审核中。

## 1. 目标

当前部署/重置数据库后没有 admin 用户，无法登录。
现有 admin 凭据是手工 SQL 插入；这在新人部署、CI 重建、测试夹具重置等场景下是隐患。

要求：alembic migration `0012_seed_admin.py` 在 `upgrade()` 阶段：

- 若 `users` 表为空，插入默认 `admin` 用户；
- 密码优先读取 `INITIAL_ADMIN_PASSWORD` 环境变量；
- 未设置时用 `Admin@123` 且写 WARNING 日志提示"生产环境必须更改"；
- 幂等：若 admin 用户已存在则跳过；
- **不动现有 admin**——`downgrade()` 删除该用户（仅当 username==admin 时）。

## 2. 设计

### 2.1 文件位置

`backend/migrations/versions/0012_seed_admin.py`

### 2.2 行为

```python
def upgrade():
    bind = op.get_bind()
    if not bind.scalar(select(func.count()).select_from(User)):
        password = os.environ.get('INITIAL_ADMIN_PASSWORD', 'Admin@123')
        if password == 'Admin@123':
            logger.warning('INITIAL_ADMIN_PASSWORD not set; using default Admin@123. Production MUST override.')
        admin = User(
            username='admin',
            password_hash=hash_password(password),
            display_name='Administrator',
            enabled=True,
        )
        bind.add(admin)
        bind.commit()
```

```python
def downgrade():
    bind = op.get_bind()
    bind.execute(delete(User).where(User.username == 'admin'))
```

### 2.3 提早 import 兼容性

`app.models.user.User` 与 `app.core.security.hash_password` 必须已经存在。若 `users` 表尚未迁移（不可能，因为 `0001_initial` 已建），依然 for safety 加 try/except 包裹。

## 3. 测试

`backend/tests/test_seed_admin_migration.py`：

| case | 步骤 | 期望 |
|---|---|---|
| `test_seed_admin_when_users_empty` | 跑 upgrade | User 表 1 条，username='admin'，password_hash 非空 |
| `test_seed_admin_skips_when_already_exists` | 预先插 admin，跑 upgrade | 用户仍 1 条（不重复） |
| `test_seed_admin_uses_environment_password` | 设置 env `INITIAL_ADMIN_PASSWORD=custom-pwd` 后跑 | 验证 password_hash 与 custom-pwd 匹配 |
| `test_seed_admin_emits_warning_when_default` | 不设 env | WARNING 日志写出 |
| `test_downgrade_removes_admin_user` | upgrade → downgrade → users 表再次为空 |

## 4. 验收

- 全新 SQLite + `alembic upgrade head` 后能用 `admin / Admin@123` 登录（不依赖手工 SQL）；
- env 改名后密码跟着变；
- 现有生产 DB（已有 admin）跑该 migration 不报错、不重复插入；
- 全量后端测试 ≥ 320 passed。

## 5. 风险

- 唯一风险：环境变量在测试里要预先清理，否则污染跨测试。
- migration 不能在 CI 重复执行时 panic；幂等已保证。
