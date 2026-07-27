# 测试用例：去重审核 API（`/api/v1/duplicates`）

维度：接口（后端）。

## 目标

推文（笔记）维度的去重候选列表 + 合并 / 忽略 / 标记操作：

- `GET /api/v1/duplicates` —— 候选列表（status、分页）
- `GET /api/v1/duplicates/{id}` —— 双栏详情
- `POST /api/v1/duplicates/{id}/merge` —— 保留 A / 保留 B
- `POST /api/v1/duplicates/{id}/ignore` —— 不是重复（标记 ignored）

## 可执行测试锚点

- 候选生成 / 合并 / 状态流：[backend/tests/test_note_dedup.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_note_dedup.py)
- 推文维度 + 软删除候选：[backend/tests/test_note_centric_management_dedup_report.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_note_centric_management_dedup_report.py)（候选合并后清理悬空引用）
- 旧 `Duplicate` Activity 维度契约（已迁移）：[backend/tests/test_activity_dedup.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_activity_dedup.py) 仍然可作回归基线
- 双栏前端：[frontend/src/views/DuplicatesView.spec.ts](file:///Users/kevin_w/Documents/github/xhs-info-crawl/frontend/src/views/DuplicatesView.spec.ts)
- 浏览器双栏场景：Playwright `frontend/e2e/documented-flows.spec.ts` 内 TC-UI-011

## 用例编号

| ID | 场景 | 期望 | 锚点 |
|---|---|---|---|
| TC-DUP-001 | 未登录访问 | 401 | `test_auth_api.py` 通用断言 |
| TC-DUP-002 | 列表 `status=pending` | 仅返回 pending 候选 | `test_note_dedup.py` + 集成层 |
| TC-DUP-003 | 列表 `status=ignored` | 仅返回已忽略 | 同上 |
| TC-DUP-004 | 列表分页 | items + pagination | 同上 |
| TC-DUP-005 | 详情：双栏内容 | 双方 note + 子活动 + 相似度 + matched_fields | `test_note_dedup.py` |
| TC-DUP-006 | 合并 keep=a | 候选 status=resolved；未保留 note 不再出现在活动管理；保留 note 仍为待审核 | `test_note_dedup.py::test_merge_keeps_a` |
| TC-DUP-007 | 合并 keep=b | 同上，方向对称 | `test_merge_keeps_b` |
| TC-DUP-008 | 合并候选指向已删除 note | 返回 422，不留悬空 | `test_note_centric_management_dedup_report.py` |
| TC-DUP-009 | 忽略候选 | status=ignored，下次列表不再返回 | `test_note_dedup.py::test_ignore_sets_status` |
| TC-DUP-010 | 关联 110 个悬空 pending | 迁移脚本清理 | `test_note_centric_management_dedup_report.py` 相关 case |
| TC-DUP-011 | matched_fields 写入为 JSON 列表 | 不再写入逗号字符串 | `test_note_dedup.py` 模型层 |
| TC-DUP-012 | 双栏提交空 body | 422 | 前端组件 + 后端 schema |

## 验收

- `uv run --project backend pytest backend/tests/test_note_dedup.py backend/tests/test_note_centric_management_dedup_report.py -q` 全绿。
- 前端 `DuplicatesView.spec.ts` 1 case + Playwright `documented-flows.spec.ts` 通过。
- 不与 [tests/test-note-centric-management-dedup-report.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-note-centric-management-dedup-report.md) 重复步骤描述，仅指向其锚点。
