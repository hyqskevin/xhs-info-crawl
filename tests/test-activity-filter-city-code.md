# 测试用例：活动列表上海筛选

## 测试环境
- 后端：pytest + FastAPI TestClient
- 前端：Vitest + Vue Test Utils
- 数据：SQLite 测试库

## 关联
- spec：`docs/superpowers/specs/2026-07-17-activity-filter-city-code-mismatch-design.md`

## 验收案例

### TC-AFC-001：上海活动列表筛选
**前置**：DB 中有 3 条上海活动、2 条宁波活动。

**操作**：`GET /api/v1/activities?city=city-99f1e469`（上海 city code）。

**预期**：
- 返回 `data.items` 长度 = 3
- 返回 `data.pagination.total = 3`
- 所有 `items[].city_code == "city-99f1e469"`

### TC-AFC-002：未传 city 参数返回全部
**操作**：`GET /api/v1/activities`。

**预期**：返回全部活动（不分城市）。

### TC-AFC-003：无效 city 返回空
**操作**：`GET /api/v1/activities?city=invalid`。

**预期**：返回 `data.items = []`，total = 0。

### TC-AFC-004：前端上海筛选项显示正常活动
**前置**：仪表盘 / 活动管理页面已加载。

**操作**：在城市下拉选 "上海"。

**预期**：
- 列表显示上海活动
- "发现" 数 = 上海活动数
- 不是空状态

## 自动化覆盖

| 用例 | 自动化文件 |
|---|---|
| TC-AFC-001 | `backend/tests/test_activity_api.py::test_filter_by_city_returns_matching_records` |
| TC-AFC-002 | `backend/tests/test_activity_api.py::test_no_filter_returns_all` |
| TC-AFC-003 | `backend/tests/test_activity_api.py::test_invalid_city_returns_empty` |
| TC-AFC-004 | `frontend/src/views/ActivitiesView.spec.ts` 已覆盖渲染 |

## 手动验收

1. 启动 dev-api + dev-web。
2. 浏览器打开活动管理 `/activities`。
3. 城市筛选选 "上海" → 列表显示上海活动，不为空。
4. 取消筛选 → 显示全部活动。
5. 选不存在的城市 → 显示空状态。