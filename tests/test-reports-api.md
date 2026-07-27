# 测试用例：周报 API（`/api/v1/reports`）

维度：接口（后端）。

## 目标

周报生成 / 预览 / 下载（md / xlsx）相关接口：

- `GET /api/v1/reports` —— 历史列表（按周排序）
- `POST /api/v1/reports/generate` —— 生成周报（单城市 + ISO week）
- `GET /api/v1/reports/{id}` —— 详情 / Markdown 内容
- `GET /api/v1/reports/{id}/download?format=md|xlsx` —— 下载

## 可执行测试锚点

- MD / XLSX 双格式 + 鉴权下载：[backend/tests/test_reports.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_reports.py)
- 单城市约束：[backend/tests/test_report_city_validation.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_report_city_validation.py)
- 周报按周排序 + ISO 提示：[backend/tests/test_note_weekly_reports.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_note_weekly_reports.py)
- 前端：ReportsView.vue + [frontend/src/views/ReportsView.spec.ts](file:///Users/kevin_w/Documents/github/xhs-info-crawl/frontend/src/views/ReportsView.spec.ts)
- 浏览器周报场景：Playwright `frontend/e2e/documented-flows.spec.ts` TC-UI-012

## 用例编号

| ID | 场景 | 期望 | 锚点 |
|---|---|---|---|
| TC-REPORT-001 | 未登录访问 | 401 | `test_auth_api.py` |
| TC-REPORT-002 | 列表按周倒序 | 最近 1 周排首位 | `test_note_weekly_reports.py` |
| TC-REPORT-003 | 列表 ISO 周 | week 字段格式 `YYYY-Www` | `test_note_weekly_reports.py` |
| TC-REPORT-004 | generate 多城市 | 422（仅单城市） | `test_report_city_validation.py` |
| TC-REPORT-005 | generate 启用城市 + 同周重复 | 422，不允许重复生成 | `test_reports.py::test_duplicate_week_rejected` |
| TC-REPORT-006 | generate 空数据周次 | Toast 报错，不生成空周报 | `ReportsView.spec.ts` 间接 |
| TC-REPORT-007 | generate 正常 | 列表新增一行，activity_count > 0 | `test_reports.py::test_generate_creates_record` |
| TC-REPORT-008 | 详情含 Markdown | `content` 字段 | `test_reports.py::test_detail_returns_markdown` |
| TC-REPORT-009 | download `format=md` | 鉴权头 + 200，文件以 `.md` 流 | `test_reports.py::test_download_md_with_token` |
| TC-REPORT-010 | download `format=xlsx` | 同上 | `test_reports.py::test_download_xlsx_with_token` |
| TC-REPORT-011 | download 无 token | 401 | `test_reports.py::test_download_requires_auth` |
| TC-REPORT-012 | 下载按钮 URL 含 `format=` | 前端编码稳定 | `documented-flows.spec.ts` TC-UI-012 |

## 验收

- `uv run --project backend pytest backend/tests/test_reports.py backend/tests/test_report_city_validation.py backend/tests/test_note_weekly_reports.py -q` 全绿。
- 不与 [tests/test-report-generation.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-report-generation.md) 重复（后者是 E2E 验收流水，本文是 API 契约）。
