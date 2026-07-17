# Resilient Management Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复非 ISO 活动日期导致整批失败的问题，提供单笔记容错、细化进度和同任务续跑，同时完成 OpenCLI 测试反馈、单城市周报下载及活动批量删除。

**Architecture:** 抓取流水线在提取边界归一化不可信模型字段，并以单笔记事务和阶段重试隔离错误；`CrawlTask` 持久化阶段计数，仪表盘轮询摘要并从失败状态续跑。管理端继续复用 Element Plus 与现有 FastAPI API，通过鉴权 Blob 下载和批量软删除完善操作闭环。

**Tech Stack:** Python 3.11、FastAPI、SQLAlchemy、Alembic、Celery filesystem broker、SQLite、Vue 3、Element Plus、Axios、Vitest、Playwright

## Global Constraints

- UI 只使用 Element Plus 及 `@element-plus/icons-vue`，不使用 Emoji，不自行实现已有组件。
- 周报只允许一个已启用城市，后端请求仍使用 `cities: [cityCode]`。
- 活动批量删除只处理明确勾选的当前页记录并保持软删除。
- 单笔记最终失败必须继续下一条；只有登录、数据库或任务基础设施错误停止整批。
- 重试次数和间隔写入 `.env` 与 `.env.example`。
- 每个实现步骤遵循测试先失败、最小实现、测试转绿的顺序。

---

### Task 1: MiniMax 日期与字段归一化

**Files:**
- Modify: `backend/app/services/extraction.py`
- Modify: `backend/app/services/minimax.py`
- Test: `backend/tests/test_multi_activity_archive.py`
- Test: `backend/tests/test_pipeline_services.py`

**Interfaces:**
- Produces: `normalize_activity_row(row: dict[str, Any], now: datetime) -> dict[str, Any]`。
- Produces: `normalize_activity_datetime(value: Any, now: datetime) -> str | None`，支持 ISO、`YYYY-M-D`、`M/D`、`M月D日`。

- [ ] **Step 1: 写日期归一化失败测试**

```python
def test_llm_partial_dates_are_normalized_without_crashing():
    result = extract_activities("活动", datetime(2026, 7, 17), lambda _: {"activities": [
        {"name": "春日市集", "start_time": "4/5", "end_time": "非法日期", "location": "月湖公园", "source_image_indexes": [1]}
    ]})[0]
    assert result["start_time"] == "2026-04-05T00:00:00"
    assert result["end_time"] is None
    assert result["status"] == "RAW"
```

- [ ] **Step 2: 运行 `backend/.venv/bin/pytest backend/tests/test_multi_activity_archive.py -q`，确认因 `4/5` 未归一化而失败。**
- [ ] **Step 3: 实现日期、置信度、图片序号和状态归一化，并在 MiniMax 提示词中明确 ISO 8601。**
- [ ] **Step 4: 运行上述测试，预期全部通过。**
- [ ] **Step 5: 提交 `fix: normalize extracted activity dates`。**

### Task 2: 任务进度字段、环境参数与迁移

**Files:**
- Create: `backend/migrations/versions/0004_crawl_progress.py`
- Modify: `backend/app/models/task.py`
- Modify: `backend/app/core/config.py`
- Modify: `.env.example`
- Modify: `.env`
- Test: `backend/tests/test_scaffold_contract.py`
- Test: `backend/tests/test_config_task_duplicate_api.py`

**Interfaces:**
- Produces: `current_stage`, `downloaded_notes`, `ocr_notes`, `extracted_notes`, `current_note` 数据库字段。
- Produces: `Settings.pipeline_stage_max_retries` 和 `Settings.pipeline_stage_retry_delay_seconds`。

- [ ] **Step 1: 写模型字段与环境变量失败测试，断言默认值为 `2` 和 `2.0`。**
- [ ] **Step 2: 运行定向测试，确认字段不存在。**
- [ ] **Step 3: 创建 Alembic `0004`，字段计数默认 0、文本可空；更新模型、配置和带中文注释的 env 文件。**
- [ ] **Step 4: 运行 `backend/.venv/bin/alembic -c backend/alembic.ini upgrade head` 并查询 SQLite 表结构。**
- [ ] **Step 5: 运行定向测试，预期通过。**
- [ ] **Step 6: 提交 `feat: persist crawl stage progress`。**

### Task 3: 阶段重试、降级和单笔记事务隔离

**Files:**
- Create: `backend/app/services/pipeline.py`
- Modify: `backend/app/tasks/crawl_task.py`
- Modify: `backend/app/services/ocr.py`
- Test: `backend/tests/test_crawl_task_resilience.py`
- Test: `backend/tests/test_pipeline_services.py`

**Interfaces:**
- Produces: `run_stage(operation, attempts, delay, retryable) -> Any`。
- Produces: `process_note(db, task, city_code, item, adapter, settings) -> bool`；成功返回 `True`，单笔记最终失败返回 `False` 并记录日志。

- [ ] **Step 1: 写阶段临时失败后成功、MiniMax 最终失败规则降级、第一条失败但第二条继续的失败测试。**
- [ ] **Step 2: 运行 `backend/.venv/bin/pytest backend/tests/test_crawl_task_resilience.py -q`，确认流水线尚未隔离。**
- [ ] **Step 3: 实现 URL 去重、阶段重试、OCR 单图隔离、规则降级和每笔记 savepoint；AuthenticationRequired 必须继续向上抛出。**
- [ ] **Step 4: 每个阶段更新 `current_stage/current_note` 和对应计数；结束时根据失败数写 `COMPLETED` 或 `COMPLETED_WITH_ERRORS`。**
- [ ] **Step 5: 运行定向测试与 `backend/tests/test_opencli_and_dedup_integration.py`，预期通过。**
- [ ] **Step 6: 提交 `feat: isolate crawl note failures`。**

### Task 4: 失败任务同 ID 续跑与仪表盘进度 API

**Files:**
- Modify: `backend/app/api/v1/tasks.py`
- Modify: `backend/app/api/v1/dashboard.py`
- Test: `backend/tests/test_config_task_duplicate_api.py`
- Test: `backend/tests/test_crawl_task_resilience.py`

**Interfaces:**
- Produces: `POST /api/v1/tasks/{task_id}/restart`。
- Produces: `/dashboard/summary.data.last_task` 完整进度对象。

- [ ] **Step 1: 写失败任务复用 ID 重新入队、非失败拒绝、并发拒绝和停用城市拒绝测试。**
- [ ] **Step 2: 写仪表盘摘要含阶段计数与错误的失败测试。**
- [ ] **Step 3: 运行定向测试并确认 404/字段缺失。**
- [ ] **Step 4: 实现续跑状态重置但保留成功计数与已有 Note；追加“任务继续抓取”日志并重新入队。**
- [ ] **Step 5: 扩展仪表盘序列化，返回 `progress_percent`，当 `total_notes=0` 时返回 `null`。**
- [ ] **Step 6: 运行定向测试，预期通过。**
- [ ] **Step 7: 提交 `feat: restart failed crawl tasks`。**

### Task 5: OpenCLI 测试加载反馈

**Files:**
- Modify: `frontend/src/views/SettingsView.vue`
- Modify: `frontend/src/views/SettingsView.spec.ts`
- Modify: `frontend/e2e/business.spec.ts`

**Interfaces:**
- Consumes: 现有 `api.testOpenCLI()`。
- Produces: `testingOpenCLI` 状态、按钮右侧 `Loading` 图标和完成 Toast。

- [ ] **Step 1: 写可控 Promise 组件测试，断言请求挂起时按钮禁用且出现 `.is-loading`，完成后隐藏并显示 Toast。**
- [ ] **Step 2: 运行 `npm --prefix frontend test -- --run src/views/SettingsView.spec.ts`，确认失败。**
- [ ] **Step 3: 使用 `Loading` 图标、`try/catch/finally` 实现交互，不使用按钮内置 loading 替代旁侧图标。**
- [ ] **Step 4: 运行组件测试，预期通过。**
- [ ] **Step 5: 提交 `feat: show opencli test progress`。**

### Task 6: 单城市周选择与鉴权文件下载

**Files:**
- Modify: `backend/app/api/v1/reports.py`
- Modify: `backend/tests/test_reports.py`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/views/ReportsView.vue`
- Modify: `frontend/src/views/ReportsView.spec.ts`
- Modify: `frontend/e2e/business.spec.ts`

**Interfaces:**
- Consumes: `GET /settings/cities` 已启用城市。
- Produces: `api.downloadReport(id, format)` Blob 请求。
- Produces: ISO 周转换 `toIsoWeek(date: Date) -> string`。

- [ ] **Step 1: 写后端零城市/多城市 422 测试，以及前端周选择、单城市提交和 Blob 下载失败测试。**
- [ ] **Step 2: 运行后端和组件定向测试，确认失败。**
- [ ] **Step 3: 为 `GenerateRequest.cities` 增加 `min_length=1,max_length=1`，前端使用 `ElDatePicker type="week"` 与单选 `ElSelect`。**
- [ ] **Step 4: 使用 Axios `responseType:'blob'`、临时下载链接和 `URL.revokeObjectURL` 实现 MD/XLSX 下载。**
- [ ] **Step 5: 运行定向测试，预期通过。**
- [ ] **Step 6: 提交 `feat: select and download single-city reports`。**

### Task 7: 活动批量软删除

**Files:**
- Modify: `backend/app/api/v1/activities.py`
- Modify: `backend/tests/test_activities_api.py`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/views/ActivitiesView.vue`
- Modify: `frontend/src/views/ActivitiesView.spec.ts`
- Modify: `frontend/e2e/documented-flows.spec.ts`

**Interfaces:**
- Produces: `DELETE /api/v1/activities/batch`，请求 `{ids:number[]}`，响应 `{deleted_ids:number[],deleted_count:number}`。
- Produces: `api.deleteActivities(ids: number[])`。

- [ ] **Step 1: 写 ID 去重批量软删除、空列表 422、无有效记录 404、未认证 401 测试。**
- [ ] **Step 2: 写前端勾选后按钮启用、确认后提交 ID 且成功刷新测试。**
- [ ] **Step 3: 运行定向测试并确认接口与 UI 不存在。**
- [ ] **Step 4: 在动态 `/{activity_id}` 路由之前实现批量端点；使用一次事务更新状态和时间。**
- [ ] **Step 5: 添加 selection 列、批量删除按钮和成功/失败 Toast；失败保留选择。**
- [ ] **Step 6: 运行定向测试，预期通过。**
- [ ] **Step 7: 提交 `feat: batch delete activities`。**

### Task 8: 任务页与仪表盘细化进度

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/views/TasksView.vue`
- Modify: `frontend/src/views/TasksView.spec.ts`
- Modify: `frontend/src/views/DashboardView.vue`
- Modify: `frontend/src/views/DashboardView.spec.ts`
- Modify: `frontend/e2e/business.spec.ts`

**Interfaces:**
- Consumes: 完整 `last_task` 摘要与 `api.restartTask(id)`。
- Produces: 3 秒轮询、阶段中文映射、五项计数、`ElProgress` 和失败续跑按钮。

- [ ] **Step 1: 写任务页细化列和仪表盘进度卡失败测试。**
- [ ] **Step 2: 写 fake timer 测试，断言每 3 秒刷新且卸载后停止；写失败任务续跑按钮测试。**
- [ ] **Step 3: 运行组件测试并确认失败。**
- [ ] **Step 4: 实现进度卡、阶段/状态中文映射、轮询清理、续跑 loading 与 Toast。**
- [ ] **Step 5: 运行组件测试，预期通过。**
- [ ] **Step 6: 提交 `feat: display crawl progress on dashboard`。**

### Task 9: 文档、浏览器验证与全量回归

**Files:**
- Modify: `docs/api-doc.md`
- Modify: `docs/database-design.md`
- Modify: `docs/crawler-design.md`
- Modify: `docs/ui-design.md`
- Modify: `tests/test-crawler-engine.md`
- Modify: `tests/test-task-scheduling.md`
- Modify: `tests/test-frontend-ui-e2e.md`
- Modify: `tests/EXECUTION_STATUS.md`
- Modify: `frontend/e2e/business.spec.ts`
- Modify: `frontend/e2e/documented-flows.spec.ts`

**Interfaces:**
- Produces: 与实现一致的设计、API、测试案例和执行结果。

- [ ] **Step 1: 更新文档，明确“发现”只代表搜索候选以及各阶段计数含义。**
- [ ] **Step 2: 补齐 OpenCLI loading、单城市周报下载、批量删除、进度轮询与续跑 Playwright 案例。**
- [ ] **Step 3: 运行 `backend/.venv/bin/pytest backend/tests -q`，预期 0 failed。**
- [ ] **Step 4: 运行 `npm --prefix frontend test -- --run`，预期 0 failed。**
- [ ] **Step 5: 运行 `npm --prefix frontend run build`，预期退出码 0。**
- [ ] **Step 6: 运行 `npm --prefix frontend run test:e2e`，预期 0 failed。**
- [ ] **Step 7: 在本地浏览器验证三个管理交互和任务进度，记录真实结果。**
- [ ] **Step 8: 提交 `docs: document resilient management workflow`。**
