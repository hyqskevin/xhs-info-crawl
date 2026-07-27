# 测试用例：关键词组 API（`/api/v1/settings/keyword-groups`）

维度：接口（后端）。

## 目标

关键词组（多对多挂多城市、多关键词）+ 抓取任务 `keyword_group_ids` 解析：

- `GET /api/v1/settings/keyword-groups` —— 列表（含关联城市列表）
- `POST /api/v1/settings/keyword-groups` —— 新建（名称 + 关键词 + 城市 ids）
- `PATCH /api/v1/settings/keyword-groups/{id}` —— 编辑
- `DELETE /api/v1/settings/keyword-groups/{id}` —— 删除

## 可执行测试锚点

- API：[backend/tests/test_keyword_group_api.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_keyword_group_api.py)
- 模型：[backend/tests/test_keyword_group_models.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_keyword_group_models.py)
- 抓取解析：[backend/tests/test_crawl_scope_with_groups.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_crawl_scope_with_groups.py)
- 配置中心 UI：[frontend/src/views/SettingsView.spec.ts](file:///Users/kevin_w/Documents/github/xhs-info-crawl/frontend/src/views/SettingsView.spec.ts)
- 仪表盘传入 `keyword_group_ids`：[frontend/src/views/DashboardView.spec.ts](file:///Users/kevin_w/Documents/github/xhs-info-crawl/frontend/src/views/DashboardView.spec.ts)

## 用例编号

| ID | 场景 | 期望 | 锚点 |
|---|---|---|---|
| TC-KWGRP-001 | 未登录访问 | 401 | `test_auth_api.py` |
| TC-KWGRP-002 | 列表返回 `city_ids[]` 与 `keywords[]` | 字段就位 | `test_keyword_group_api.py` |
| TC-KWGRP-003 | 新建名称重复 | 422 | 模型 unique |
| TC-KWGRP-004 | 新建 `keywords` 为空 | 422 | API schema |
| TC-KWGRP-005 | 新建 `city_ids` 含不存在 ID | 422 | 外键校验 |
| TC-KWGRP-006 | 编辑组内单个城市 | 多对多反映 | `test_keyword_group_models.py` |
| TC-KWGRP-007 | 删除组（无爬取引用） | 成功 + cascade 删除关联 | 同上 |
| TC-KWGRP-008 | 抓取提交 `keyword_group_ids=[1,2]` | `resolve_crawl_scope` 展开多组关键词 | `test_crawl_scope_with_groups.py` |
| TC-KWGRP-009 | 与 `keywords` 旧字段共存 | 兼容，前者覆盖后者 | `test_crawl_scope.py` 旧字段 |

## 验收

- `uv run --project backend pytest backend/tests/test_keyword_group_api.py backend/tests/test_keyword_group_models.py backend/tests/test_crawl_scope_with_groups.py -q` 全绿。
- 不与 [tests/test-crawl-scope-config-driven.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-crawl-scope-config-driven.md) 重复。
