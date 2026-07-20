# 测试用例：博主白名单可选 xhs_id / 多城市

## 测试环境
- 后端：pytest + FastAPI TestClient
- 前端：Vitest + Vue Test Utils
- 数据：SQLite 测试库

## 关联
- spec：`docs/superpowers/specs/2026-07-17-blogger-optional-xhs-id-multiple-cities-design.md`

## 验收案例

### TC-BOX-001：不填 xhs_id 也能保存博主
**前置**：登录态 OK。

**操作**：`POST /api/v1/settings/bloggers {username: "测试博主", profile_url: "", city_codes: ["shanghai"], enabled: true}`。

**预期**：
- 返回 200/201
- DB 中博主 `platform_user_id = null` 或留空
- 不抛 422

### TC-BOX-002：不填 profile_url 也能保存博主
**操作**：`POST /api/v1/settings/bloggers {username: "测试博主", platform_user_id: null, city_codes: ["shanghai"], enabled: true}`。

**预期**：
- 返回 200/201
- DB 中 `profile_url = ""`
- 仪表盘选该博主时标"待补充"

### TC-BOX-003：同一博主关联多个城市
**前置**：博主 ID = 1 当前已关联 `shanghai`。

**操作**：`PUT /api/v1/settings/bloggers/1 {..., city_codes: ["shanghai", "beijing"]}`。

**预期**：
- 返回 200
- `BloggerCity` 表新增一行 `(blogger_id=1, city_code="beijing", enabled=True)`
- 原 `(blogger_id=1, city_code="shanghai")` 保留

### TC-BOX-004：取消城市关联
**操作**：`PUT /api/v1/settings/bloggers/1 {..., city_codes: ["beijing"]}`。

**预期**：
- 原 `shanghai` 行被删除（enabled=False 或删除）
- `beijing` 行新增

### TC-BOX-005：仪表盘博主下拉显示多城市博主
**前置**：博主 ID = 1 同时关联 `shanghai` 和 `beijing`。

**操作**：仪表盘选 `shanghai`。

**预期**：博主出现在博主下拉列表。

操作：仪表盘选 `beijing`。

**预期**：同一博主也出现。

## 自动化覆盖

| 用例 | 自动化文件 |
|---|---|
| TC-BOX-001 | `backend/tests/test_settings_blogger_api.py::test_create_blogger_without_xhs_id` |
| TC-BOX-002 | `backend/tests/test_settings_blogger_api.py::test_create_blogger_without_profile_url` |
| TC-BOX-003 | `backend/tests/test_blogger_city_api.py::test_blogger_can_be_linked_to_multiple_cities` |
| TC-BOX-004 | `backend/tests/test_blogger_city_api.py::test_remove_blogger_city_link` |
| TC-BOX-005 | `frontend/src/views/DashboardView.spec.ts::starts a crawl from configured city, keywords, time and bloggers` |

## 手动验收

1. 配置中心 → 新增博主 → 不填 xhs_id、不填主页 → 保存成功。
2. 编辑同一博主 → 选多个城市 → 保存。
3. 仪表盘 → 选每个城市 → 该博主出现在博主下拉。