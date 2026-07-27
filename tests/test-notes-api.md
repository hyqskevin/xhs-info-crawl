# 测试用例：笔记 API（`/api/v1/notes`）

维度：接口（后端）。

## 目标

笔记作为活动管理主聚合维度（自 2026-07-20 起替代旧 `Activity` 单独状态机），以下 API 行为必须稳定：

- `GET /api/v1/notes` —— 列表（分页、筛选、关键词搜索、OCR 摘要）
- `GET /api/v1/notes/{id}` —— 详情（子活动、来源图片）
- `PATCH /api/v1/notes/{id}` —— 编辑标题/正文/城市/发布时间（原文链接只读）
- `POST /api/v1/notes/{id}/review` —— 单篇通过/驳回
- `POST /api/v1/notes/{id}/reprocess` —— 清空子活动重新走抓取
- `POST /api/v1/notes/batch/approve` —— 批量通过（兼容旧合同）
- `GET /api/v1/notes/{id}/signed-image-url` —— 来源图片鉴权 URL

## 可执行测试锚点

所有断言落在自动化测试里：

- 列表 / 详情 / 编辑 / 单篇审核 / 批量审核：[backend/tests/test_notes_api.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_notes_api.py)
- 关键词搜索：`test_notes_api.py::test_list_notes_supports_keyword_filter_against_title`、`..._against_content`、`..._empty_or_missing_keyword_returns_all`、`..._keyword_with_no_match_returns_empty`
- OCR 摘要长度保护 + `summary_truncated`：[backend/tests/test_note_summary.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_note_summary.py)
- 推文列表去除摘要列、OCR 进入详情：`ActivitiesView.spec.ts` 内的 "does NOT render a summary column in the note list"
- 来源图片鉴权：[backend/tests/test_blogger_notes_signed_url.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_blogger_notes_signed_url.py) 中与 `signed-image-url` 关联的用例
- 子活动审批通过校验至少 1 条未删除：[backend/tests/test_note_zero_activity_and_window.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_note_zero_activity_and_window.py) 对应 spec

## 用例编号

| ID | 场景 | 期望 | 锚点 |
|---|---|---|---|
| TC-NOTES-001 | 未携带 Token | 401 | `test_auth_api.py` 通用断言 |
| TC-NOTES-002 | 列表默认一页 20 条 | 返回 `items + pagination` | `test_notes_api.py::test_notes_list_returns_one_row_per_post` |
| TC-NOTES-003 | 列表筛选 `city=shanghai` | city_code 命中 | `test_activities_api.py` 中相关 city 过滤 |
| TC-NOTES-004 | 列表 `keyword=foo` 命中 title | 返回含 `foo` 的笔记 | `test_notes_api.py::test_list_notes_supports_keyword_filter_against_title` |
| TC-NOTES-005 | 列表 `keyword` 命中 content | 返回正文包含的笔记 | `test_notes_api.py::test_list_notes_supports_keyword_filter_against_content` |
| TC-NOTES-006 | 列表 keyword 为空 | 不写 WHERE | `test_notes_api.py::test_list_notes_empty_or_missing_keyword_returns_all` |
| TC-NOTES-007 | 列表 keyword 不命中 | 空列表 + total=0 | `test_notes_api.py::test_list_notes_keyword_with_no_match_returns_empty` |
| TC-NOTES-008 | 详情包含全部子活动 | `activities[]` 不软删除 | `test_notes_api.py::test_note_detail_contains_all_child_activities` |
| TC-NOTES-009 | 编辑标题/正文/城市/发布时间 | 写入成功 | `test_notes_api.py::test_update_note_changes_editable_fields_but_keeps_source_url` |
| TC-NOTES-010 | 编辑提交非法 title/city | 422 | `test_notes_api.py::test_update_note_rejects_invalid_title_or_city` |
| TC-NOTES-011 | 编辑不允许改 source_url | 保持原值 | `test_notes_api.py::test_update_note_changes_editable_fields_but_keeps_source_url` |
| TC-NOTES-012 | 单篇 review → APPROVED | status 写入，子活动保持可见 | `test_notes_api.py::test_review_single_note_sets_requested_status` |
| TC-NOTES-013 | 单篇 review 未知状态 | 422 | `test_notes_api.py::test_review_single_note_rejects_unknown_status` |
| TC-NOTES-014 | 批量 approve | 全表 APPROVED | `test_notes_api.py::test_batch_approve_notes_approves_post_not_children` |
| TC-NOTES-015 | OCR 摘要 ≤ 4 KiB + `summary_truncated` | 截断字段 | `test_note_summary.py` 5 个 case |
| TC-NOTES-016 | 来源图片未登录访问 | 401 | `test_blogger_notes_signed_url.py` 公开 URL 测试 |
| TC-NOTES-017 | 旧 `/activities/batch/approve` | 410 Gone | `test_activity_status_removal.py` |

## 验收

- `uv run --project backend pytest backend/tests/test_notes_api.py backend/tests/test_note_summary.py -q` 全绿；
- 前端 `ActivitiesView.spec.ts` 与 `DashboardView.spec.ts` 引用此 API 的 case 不退化；
- 与 [tests/test-note-edit-single-review.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-note-edit-single-review.md)、[tests/test-parse-real-published-at.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-parse-real-published-at.md)、[tests/test-note-list-no-summary.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-note-list-no-summary.md) 不重复。
