# 多账号体系 + RBAC 设计

> 状态：审核中。

## 1. 目标

当前只有单一 admin 账号。新增**账号管理**模块，要求：

- 多个账号都能使用全部功能（多账号平等）；
- 账号可以分组，分组关联权限集；
- 账号的访问 = 该账号在所有所属分组中的权限并集；
- 权限粒度至少到 API path，例如 `notes:review`、`tasks:crawl`、`settings:cities:write`、`users:manage` 等。

> 用户原话："多账号是指多个账号可以使用所有功能，不是角色划分，角色划分叫子账号"。所以**默认新账号 + "管理员分组" = 等同 admin**；子账号留作未来扩展。

## 2. 设计

### 2.1 数据模型

| 表 | 字段 | 说明 |
|---|---|---|
| `users` | id, username (unique), password_hash, display_name, enabled, created_at | 现有，已是字段增加 `display_name` `enabled` |
| `groups` | id, name (unique), description, created_at | 账号的分组 |
| `permissions` | id, code (unique), description | 权限字典，例如 `users:manage`、`notes:review`、`tasks:crawl`、`settings:*` |
| `group_permissions` | group_id, permission_id | group → permissions |
| `user_groups` | user_id, group_id | user → groups |

**admin 兜底**：
- 一个内置分组 `Administrators`，关联所有 `*` 权限；
- 现有 admin 用户自动加入该分组；
- 新建账号若没有指定分组，**默认**也加入 `Administrators`（等价于多账号平等）。

### 2.2 API

| 路径 | 方法 | 权限 | 说明 |
|---|---|---|---|
| `/api/v1/users` | GET | `users:read` | 列出所有账号 |
| `/api/v1/users` | POST | `users:manage` | 新建账号（username + 初始密码，可选分组） |
| `/api/v1/users/{id}` | PUT | `users:manage` | 改 display_name / enabled / 密码重置 |
| `/api/v1/users/{id}/groups` | PUT | `users:manage` | 重置账号所属分组 |
| `/api/v1/groups` | GET / POST | `users:read` / `users:manage` | 列出 / 新建分组 |
| `/api/v1/groups/{id}/permissions` | PUT | `users:manage` | 重置分组的权限 |
| `/api/v1/permissions` | GET | `users:read` | 字典表（用于前端选权限） |

权限粒度**先粗后细**：

| 权限 code | 覆盖 |
|---|---|
| `users:manage` | 账号管理 |
| `settings:write` | 配置中心写 |
| `tasks:crawl` | 发起/停止抓取任务 |
| `notes:review` | 单篇/批量审核推文 |
| `reports:generate` | 生成周报 |
| `notes:edit` | 编辑推文 |
| `activities:edit` | 编辑子活动 |
| `duplicates:resolve` | merge/ignore 重复项 |
| `notes:delete` | 删除推文 |

并在后端每个 endpoint 加 dep 检查。

### 2.3 前端（左侧 nav 新增"账号管理"）

```
├─ 仪表盘
├─ 抓取日志
├─ 活动管理
├─ 重复项
├─ 周报
├─ 配置中心
└─ 账号管理       ← 新增
```

`/accounts` 路由，新 `AccountsView.vue`：

- 顶部 tab：`账号` / `分组` / `权限`；
- "账号"：表格 username + display_name + enabled + 分组 chips + 删除按钮；
- "分组"：分组表 + 分组详情面板（关联权限多选）；
- "权限"：read-only 权限字典，附说明。

无 `users:manage` 权限的账号：访问 `/accounts` 看到 403 页（前端用 ApiError 拦截）。
无权限的页面（如未开通 `tasks:crawl`）也隐藏 nav。

## 3. 测试

### 3.1 后端

| 文件 | 案例数 |
|---|---|
| `tests/test_users_api.py` | 列表 / 新建 / 改 / 加分组 / 跨账号越权 403 |
| `tests/test_groups_api.py` | 列表 / 新建 / 改权限集 |
| `tests/test_rbac_enforcement.py` | 已有 endpoint 用不同账号 → 200 / 403 |
| `tests/test_default_administrators_group.py` | admin 用户默认入组；新建账号默认入组 |

### 3.2 前端

`frontend/src/views/AccountsView.spec.ts`：tab 切换、表格呈现、新建账号表单。

## 4. 验收

- 后端 308+ 测试；
- 前端 49+ 测试；
- build 通过；
- 实际：用 admin 新建一个 `editor` 账号 → 分配给"运营"分组，权限只有 `notes:review` 与 `tasks:crawl` → 用 editor 登录 → 抓取日志页无法起新任务（409），但能单篇审核推文；其他 admin 独占功能（如 `users:manage`）显示 403 页面。

## 5. TODO 关联

`docs/TODO.md` 增项"多账号与 RBAC"。

## 6. 风险

- 现有 admin 用户是手工 SQL 创建的，需要在 migration 里迁移到 `Administrators` 组 + 加 enabled 字段；失败回滚；
- 现有 `require_admin` 装饰器要替换为更通用的 `require_permission(code)`，逐个 endpoint 检查工作量极大；
- token 改动 `sub` 仍是 user id，但 role / permissions 一起嵌入 JWT（短过期 + 刷新机制）。
