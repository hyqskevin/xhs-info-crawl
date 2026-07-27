# 测试用例：任务 API（`/api/v1/tasks`）

维度：接口 + 任务调度（后端）。

## 目标

任务相关接口覆盖下列行为：

- `POST /api/v1/tasks/crawl` —— 提交抓取任务（关键词/博主/keyword_group_ids/时间范围）
- `GET /api/v1/tasks` —— 任务列表（分页 + 状态过滤）
- `GET /api/v1/tasks/{id}` —— 任务详情
- `GET /api/v1/tasks/{id}/logs` —— 任务日志
- `POST /api/v1/tasks/{id}/stop` —— 立即停（RUNNING/FAILED/PAUSED/COMPLETED 强制 STOPPED）
- `POST /api/v1/tasks/{id}/restart` —— 续跑（沿用原任务）
- `POST /api/v1/tasks/batch` —— 批量删除（task + log）

## 可执行测试锚点

- API 范围与城市绑定：[backend/tests/test_tasks_api_scope.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_tasks_api_scope.py)
- 自动停止上一个任务（不报错 TASK_IN_PROGRESS）：[backend/tests/test_crawl_auto_stop_previous.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_crawl_auto_stop_previous.py)
- 立即 stop 实现 / 幂等 / 写日志：[backend/tests/test_task_stop_immediate.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_task_stop_immediate.py)
- 执行权栅栏：[backend/tests/test_opencli_execution_fence.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_opencli_execution_fence.py)
- 抓取执行权与停止：[backend/tests/test_crawl_execution_safe_stop.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_crawl_execution_safe_stop.py)
- 批量删除：[backend/tests/test_tasks_batch_delete.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_tasks_batch_delete.py)
- 抓取范围（关键词/博主按配置驱动）：[backend/tests/test_crawl_scope.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_crawl_scope.py)、[backend/tests/test_crawl_scope_with_groups.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_crawl_scope_with_groups.py)
- 单篇城市校验：[backend/tests/test_crawl_task_city_validation.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_crawl_task_city_validation.py)

## 用例编号

| ID | 场景 | 期望 | 锚点 |
|---|---|---|---|
| TC-TASK-001 | 未登录提交抓取 | 401 | `test_auth_api.py` 通用断言 |
| TC-TASK-002 | 提交空 city | 422 | `test_tasks_api_scope.py` |
| TC-TASK-003 | 提交启用城市 + 启用关键词 | Celery 收到 `task_id` + `run_token` | `test_crawl_auto_stop_previous.py`、`test_celery_test_isolation.py` |
| TC-TASK-004 | 提交时存在 RUNNING 旧任务 | 旧任务 stop+新任务创建 | `test_crawl_auto_stop_previous.py::test_crawl_auto_stops_previous_running_task` |
| TC-TASK-005 | 提交时存在 PENDING 旧任务 | 旧任务 stop+新任务创建 | `test_crawl_auto_stops_previous_pending_task` |
| TC-TASK-006 | 无旧任务 | 直接创建新任务成功 | `test_crawl_returns_success_when_no_previous_task` |
| TC-TASK-007 | 列表分页 + status 过滤 | items + pagination | `test_tasks_api_scope.py` |
| TC-TASK-008 | 详情存在 | 全字段 | `test_tasks_api_scope.py` |
| TC-TASK-009 | 详情不存在 | 404 | `test_task_stop_immediate.py::test_stop_404_when_task_not_found` |
| TC-TASK-010 | stop RUNNING | STOP_REQUESTED → SIGKILL → STOPPED | `test_task_stop_immediate.py::test_stop_running_task_sets_stop_requested` + `test_opencli_execution_fence.py` |
| TC-TASK-011 | stop PENDING | 直接 STOPPED | `test_stop_pending_task_sets_stopped` |
| TC-TASK-012 | stop FAILED / COMPLETED | 直接 STOPPED | `test_stop_inactive_task_sets_stopped_immediately` |
| TC-TASK-113 | stop 重复调用 | 幂等 202 | `test_stop_idempotent_when_already_stopped` + `test_stop_idempotent_when_stop_requested` |
| TC-TASK-014 | stop 未注册 PID | 写日志，不报错 | `test_stop_handles_no_registered_pid` |
| TC-TASK-015 | stop 写 TaskLog | 日志含 stop reason | `test_stop_writes_log_entry` |
| TC-TASK-016 | restart 已 STOPPED | 复用原任务 ID，重新进入 RUNNING | `DashboardView.spec.ts::allows a stopped task to continue` + 后端回归 |
| TC-TASK-017 | batch delete `{ids:[1,2]}` | 删除 task + log | `test_tasks_batch_delete.py::test_batch_delete_removes_tasks_and_logs` |
| TC-TASK-018 | batch delete 未知 id | 422 | `test_tasks_batch_delete.py::test_batch_delete_unknown_id_is_422` |
| TC-TASK-019 | batch delete 空列表 | 422 | `test_batch_delete_empty_list_is_422` |
| TC-TASK-020 | batch delete 超 100 | 422 | `test_batch_delete_rejects_over_limit` |
| TC-TASK-021 | 抓取范围仅启用博主 | 不走关键词回退 | `test_crawl_scope.py` 系列 |
| TC-TASK-022 | keyword_group_ids 解析 | 命中组内关键词 | `test_crawl_scope_with_groups.py` |
| TC-TASK-023 | 博主无 profile_url | 跳过 + WARNING | `test_crawl_task_resilience.py` |

## 验收

- `uv run --project backend pytest backend/tests/test_tasks_api_scope.py backend/tests/test_task_stop_immediate.py backend/tests/test_crawl_auto_stop_previous.py backend/tests/test_tasks_batch_delete.py backend/tests/test_crawl_scope.py backend/tests/test_crawl_scope_with_groups.py backend/tests/test_opencli_execution_fence.py backend/tests/test_crawl_task_city_validation.py -q` 全绿。
- 不与 [tests/test-crawl-execution-safe-stop.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-crawl-execution-safe-stop.md)、[tests/test-stop-execution-fence-browser-cleanup.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-stop-execution-fence-browser-cleanup.md)、[tests/test-crawl-scope-config-driven.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-crawl-scope-config-driven.md)、[tests/test-celery-test-isolation.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-celery-test-isolation.md) 重复断言。
