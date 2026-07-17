# 周报审核与按周导出 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让已通过活动按单城市和 ISO 周准确导出，并提供批量审核通过入口和明确的空结果提示。

**Architecture:** 后端集中解析 ISO 周边界并以同一查询生成 Markdown 与 Excel；活动 API 提供幂等批量通过接口。前端复用现有表格选择和 Element Plus 反馈模式接入批量操作。

**Tech Stack:** FastAPI、SQLAlchemy、SQLite、Pytest、Vue 3、Element Plus、Vitest

## Global Constraints

- 只有 `APPROVED` 活动进入周报。
- 阶段一周报只允许单城市生成和导出。
- UI 使用 Element Plus 组件和图标，不使用 emoji。
- 不改变阶段一 Vue 3、FastAPI、Celery、SQLite 技术栈。

---

### Task 1: 后端周报按周筛选与空结果提示

**Files:**
- Modify: `backend/app/api/v1/reports.py`
- Test: `backend/tests/test_reports.py`

**Interfaces:**
- Produces: `week_bounds(week: str) -> tuple[datetime, datetime]`
- Produces: `select_activities(db: Session, cities: list[str], week: str) -> list[Activity]`

- [ ] 写入跨周排除、状态排除、空结果和非法周次失败测试。
- [ ] 运行定向 Pytest，确认测试因缺少周次约束和空结果校验而失败。
- [ ] 实现 ISO 周解析、数据库时间边界查询及 422 提示。
- [ ] 让 Excel 下载复用报告保存的周次和城市查询。
- [ ] 运行 `backend/.venv/bin/python -m pytest backend/tests/test_reports.py -q`，确认通过。

### Task 2: 后端批量审核通过

**Files:**
- Modify: `backend/app/api/v1/activities.py`
- Test: `backend/tests/test_activities_api.py`

**Interfaces:**
- Produces: `POST /api/v1/activities/batch/approve`，请求 `{ "ids": number[] }`

- [ ] 写入多记录批量通过、重复提交幂等和空列表校验测试。
- [ ] 运行定向测试，确认接口尚不存在而失败。
- [ ] 实现批量通过接口并更新时间戳。
- [ ] 运行活动 API 测试，确认通过。

### Task 3: 前端批量通过交互

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/views/ActivitiesView.vue`
- Test: `frontend/src/views/ActivitiesView.spec.ts`

**Interfaces:**
- Consumes: `POST /activities/batch/approve`
- Produces: `api.approveActivities(ids: number[])`

- [ ] 扩展组件测试，验证按钮状态、请求参数、成功提示和列表刷新。
- [ ] 运行 Vitest，确认缺少按钮和 API 方法而失败。
- [ ] 使用 Element Plus 成功态按钮和确认框实现批量通过。
- [ ] 运行活动组件测试，确认通过。

### Task 4: 文档与完整验证

**Files:**
- Modify: `tests/test-report-generation.md`
- Modify: `tests/test-activity-crud-api.md`
- Modify: `tests/test-frontend-ui-e2e.md`
- Modify: `docs/api-doc.md`

- [ ] 补充批量通过、周次边界和空结果测试案例。
- [ ] 运行完整后端测试。
- [ ] 运行完整前端测试与生产构建。
- [ ] 执行浏览器关键路径验证：批量通过后生成非空单城市周报。
- [ ] 检查 `git diff --check` 和本地 API 健康状态。
