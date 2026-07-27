# 测试用例：城市 API（`/api/v1/settings/cities`）

维度：接口（后端）。

## 目标

配置中心城市相关接口（CRUD + 时间范围 + 关键词字段），且必须与 `dedupe_cities` 迁移逻辑一致：

- `GET /api/v1/settings/cities` —— 列表（含 keyword_groups、时间范围）
- `POST /api/v1/settings/cities` —— 新增（name + 时间范围 + 关键词列表 + keyword_group_ids）
- `PATCH /api/v1/settings/cities/{id}` —— 编辑
- `DELETE /api/v1/settings/cities/{id}` —— 删除（无人引用）

## 可执行测试锚点

- 关键词组多对多 + 旧字段兼容：[backend/tests/test_keyword_group_models.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_keyword_group_models.py)
- 抓取范围按城市：[backend/tests/test_crawl_scope.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_crawl_scope.py)
- 城市唯一约束 + dedupe：[backend/tests/test_dedupe_cities_script.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_dedupe_cities_script.py)
- 城市筛选 E2E：[tests/test-activity-filter-city-code.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-activity-filter-city-code.md)
- 配置中心 UI：[frontend/src/views/SettingsView.spec.ts](file:///Users/kevin_w/Documents/github/xhs-info-crawl/frontend/src/views/SettingsView.spec.ts)

## 用例编号

| ID | 场景 | 期望 | 锚点 |
|---|---|---|---|
| TC-CITY-001 | 未登录访问 | 401 | `test_auth_api.py` |
| TC-CITY-002 | 列表返回 `keyword_groups[]` 与 `recent_days` | 字段就位 | `test_keyword_group_models.py` |
| TC-CITY-003 | 新增重复 name | 命中 unique 约束 409 | `test_dedupe_cities_script.py::test_dedupe_does_not_touch_distinct_names` + City 模型 |
| TC-CITY-004 | 新增启用 + keyword_group_ids 命中既有组 | 入库 + 反查一致 | `test_keyword_group_models.py::test_attach_groups` |
| TC-CITY-005 | 编辑 cities 修改 recent_days | 列表反映 | `test_keyword_group_models.py` |
| TC-CITY-006 | 删除被关键词组引用 | 422 | 模型层 `ondelete` 与 API 检查 |
| TC-CITY-007 | 删除被博客主引用 | 422 | 同上 |
| TC-CITY-008 | 删除前执行 `dedupe` | 仍然幂等 | `test_dedupe_cities_script.py` |
| TC-CITY-009 | `dedupe` 保留最早启用的 canonical | 迁移后 SELECT COUNT 下降 | `test_dedupe_keeps_oldest_enabled_city` |
| TC-CITY-010 | `dedupe` notes / blogger_city / keyword_group_cities 迁移到 canonical | 关联外键一致 | `test_dedupe_migrates_notes_and_blogger_city` |
| TC-CITY-011 | `dedupe` 改写 `crawl_tasks.params` JSON | 旧 city → canonical | `test_dedupe_rewrites_crawl_task_json_params` |
| TC-CITY-012 | `dedupe` 反复执行 | 幂等 | `test_dedupe_is_idempotent` |

## 验收

- `uv run --project backend pytest backend/tests/test_keyword_group_models.py backend/tests/test_dedupe_cities_script.py backend/tests/test_crawl_scope.py -q` 全绿。
- 不与 [tests/test-activity-filter-city-code.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-activity-filter-city-code.md)（E2E）、[tests/test-crawl-scope-config-driven.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-crawl-scope-config-driven.md) 重复。
