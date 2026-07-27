# 测试用例：配置中心 API（`/api/v1/settings/*`）

维度：接口（后端）。

## 目标

`/settings/` 命名空间下管理接口 + OpenCLI 端点 + 博主信息补全：

- `GET/POST/PATCH/DELETE /api/v1/settings/bloggers` —— 博主白名单
- `POST /api/v1/settings/bloggers/batch` —— 批量上传（Excel/CSV）
- `GET /api/v1/settings/bloggers/template` —— 模板下载
- `POST /api/v1/settings/bloggers/{id}/enrich` —— OpenCLI 自动补全 user_id/profile_url
- `GET/PUT /api/v1/settings/opencli` —— OpenCLI 配置（CDP endpoint、interval、limit）
- `POST /api/v1/settings/opencli/test` —— 测试连接

## 可执行测试锚点

- 博主 enrich：[backend/tests/test_blogger_enricher.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_blogger_enricher.py)、[backend/tests/test_settings_blogger_enrich_api.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_settings_blogger_enrich_api.py)
- 博主批量导入：[backend/tests/test_blogger_batch_import.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_blogger_batch_import.py)
- 博主可选 xhs_id / 多城市：[backend/tests/test_blogger_optional_xhs_id_multiple_cities.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_blogger_optional_xhs_id_multiple_cities.py)（无则跳过；如缺该文件则可用 `test_crawl_scope.py::test_blogger_bound_to_two_cities_returned_for_both` 替代）
- 博主笔记带 token：[backend/tests/test_blogger_notes_signed_url.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_blogger_notes_signed_url.py)
- 前端：[frontend/src/views/SettingsView.spec.ts](file:///Users/kevin_w/Documents/github/xhs-info-crawl/frontend/src/views/SettingsView.spec.ts)（含博主表格、模板下载、批量上传、补充博主信息、OpenCLI Loading）

## 用例编号

| ID | 场景 | 期望 | 锚点 |
|---|---|---|---|
| TC-SET-001 | 未登录 | 401 | `test_auth_api.py` |
| TC-SET-002 | 列表博主（含 `city_codes[]`） | 字段就位 | `SettingsView.spec.ts::renders blogger list with city tag from city_codes array` |
| TC-SET-003 | 提交博主留空 `platform_user_id` 与 `profile_url` | 201，成功 | `SettingsView.spec.ts::submits a blogger without platform_user_id and profile_url` |
| TC-SET-004 | enrich 接口回填 `profile_url` + `platform_user_id` | 200 + 行更新 | `test_blogger_enricher.py::test_enrich_patches_blogger` |
| TC-SET-005 | enrich 接口 OpenCLI 错误 | 5xx，不写脏数据 | `test_settings_blogger_enrich_api.py::test_enrich_returns_502_on_opencli_error` |
| TC-SET-006 | 批量上传 xlsx 合法 | 200 + 全部生效 | `test_blogger_batch_import.py::test_upload_xlsx_creates_bloggers` |
| TC-SET-007 | 批量上传行号错误 | 422 + 含错误行号 | `test_blogger_batch_import.py::test_upload_xlsx_returns_row_error` |
| TC-SET-008 | 批量上传 > 2 MiB | 422 | 同上 |
| TC-SET-009 | 批量上传 > 500 行 | 422 | 同上 |
| TC-SET-010 | 模板下载 | 200 + `application/octet-stream` | `test_blogger_batch_import.py::test_template_endpoint_returns_xlsx` |
| TC-SET-011 | OpenCLI 测试连接成功 | 200 + Toast 成功 | `SettingsView.spec.ts::shows separate loading icon while testing OpenCLI` |
| TC-SET-012 | OpenCLI 测试连接 77 认证失败 | 留在页面 + 提示登录 | `documented-flows.spec.ts` TC-UI-013 |
| TC-SET-013 | OpenCLI 测试期间 Loading | 按钮独立 loading | `SettingsView.spec.ts` |
| TC-SET-014 | 同一博主多城市 | `city_codes=['shanghai','beijing']` 都被允许 | `test_crawl_scope.py` 系列 |
| TC-SET-015 | 博主笔记带 xsec_token | search 模式回填 | `test_blogger_notes_signed_url.py` |

## 验收

- `uv run --project backend pytest backend/tests/test_blogger_enricher.py backend/tests/test_settings_blogger_enrich_api.py backend/tests/test_blogger_batch_import.py backend/tests/test_blogger_notes_signed_url.py backend/tests/test_crawl_scope.py -q` 全绿。
- 不与 [tests/test-blogger-batch-import.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-blogger-batch-import.md)、[tests/test-blogger-discovery-resilience.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-blogger-discovery-resilience.md)、[tests/test-blogger-optional-xhs-id.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-blogger-optional-xhs-id.md) 重复。
