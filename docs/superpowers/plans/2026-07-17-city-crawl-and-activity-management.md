# City Crawl and Activity Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按城市统一配置关键词与小红书时间范围，并将活动管理改为面向爬取结果的筛选、分页和审核界面。

**Architecture:** `City` 保存原生时间筛选值，`Keyword` 继续保存城市的一对多关键词；设置 API 聚合两张表。爬虫按任务城市加载设置，活动 API 继续用内部 code 查询，前端只展示城市名称。

**Tech Stack:** FastAPI、SQLAlchemy、Alembic、Celery、Vue 3、Element Plus、Vitest、Playwright

## Global Constraints

- `code` 仅作内部关联键，后端自动生成，前端不展示。
- 时间范围只允许“不限、一天内、一周内、半年内”。
- 爬取活动默认“待审核”，仅“已通过”进入周报。
- 不手工新增活动。
- UI 使用 Element Plus 及其图标，不使用 emoji。

---

### Task 1: 城市组合配置 API 与迁移

**Files:**
- Modify: `backend/app/models/config.py`
- Modify: `backend/app/api/v1/settings.py`
- Create: `backend/migrations/versions/0003_city_recent_filter.py`
- Test: `backend/tests/test_config_task_duplicate_api.py`

**Interfaces:**
- Consumes: `POST/PUT /api/v1/settings/cities` 的 `name`、`keywords`、`recent_filter`、`enabled`。
- Produces: 含 `keywords: string[]` 和 `recent_filter` 的城市对象；内部 `code` 自动生成。

- [ ] **Step 1: 写城市组合新增、更新和非法时间范围的失败测试**
- [ ] **Step 2: 运行定向测试并确认因接口尚未实现而失败**
- [ ] **Step 3: 增加迁移、模型字段、code 生成和事务内关键词同步**
- [ ] **Step 4: 运行定向测试并确认通过**

### Task 2: 按城市时间范围抓取

**Files:**
- Modify: `backend/app/services/opencli_adapter.py`
- Modify: `backend/app/tasks/crawl_task.py`
- Test: `backend/tests/test_opencli_and_dedup_integration.py`
- Test: `backend/tests/test_pipeline_services.py`

**Interfaces:**
- Consumes: `OpenCLIAdapter.search_recent(query, recent_filter)`。
- Produces: 对应小红书筛选点击行为；抓取任务按城市关键词组合执行。

- [ ] **Step 1: 写不同时间范围点击行为和城市组合解析失败测试**
- [ ] **Step 2: 运行测试并确认签名或行为不匹配**
- [ ] **Step 3: 实现原生筛选映射及任务配置加载**
- [ ] **Step 4: 运行爬虫服务测试并确认通过**

### Task 3: 配置中心界面

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/views/SettingsView.vue`
- Modify: `frontend/src/views/SettingsView.spec.ts`
- Modify: `frontend/e2e/business.spec.ts`
- Modify: `frontend/e2e/documented-flows.spec.ts`

**Interfaces:**
- Consumes: 聚合城市设置 API 和博主 API。
- Produces: 城市组合新增/编辑、博主编辑和 OpenCLI 测试界面。

- [ ] **Step 1: 写前端失败测试，断言无 code 输入、可见编辑和时间范围**
- [ ] **Step 2: 运行 Vitest 并确认失败**
- [ ] **Step 3: 使用 Element Plus 实现城市与博主表单及中文表格**
- [ ] **Step 4: 运行组件测试并确认通过**

### Task 4: 活动管理筛选与分页

**Files:**
- Modify: `frontend/src/views/ActivitiesView.vue`
- Modify: `frontend/src/views/ActivitiesView.spec.ts`
- Modify: `frontend/e2e/business.spec.ts`
- Modify: `frontend/e2e/documented-flows.spec.ts`
- Test: `backend/tests/test_activities_api.py`

**Interfaces:**
- Consumes: 城市设置列表和 `GET /activities` 的分页、城市、状态、起止日期参数。
- Produces: 无新增入口的活动审核、时间范围筛选和 10/20/50/100 分页。

- [ ] **Step 1: 写 API 日期分页和前端交互失败测试**
- [ ] **Step 2: 运行测试并确认旧 UI 不满足要求**
- [ ] **Step 3: 实现中文状态、城市映射、日期筛选和分页控件**
- [ ] **Step 4: 运行后端及前端定向测试并确认通过**

### Task 5: 文档与完整验证

**Files:**
- Modify: `docs/ui-design.md`
- Modify: `docs/database-design.md`
- Modify: `docs/crawler-design.md`
- Modify: `tests/test-frontend-ui-e2e.md`
- Modify: `tests/EXECUTION_STATUS.md`

**Interfaces:**
- Consumes: 已实现的界面和接口行为。
- Produces: 与实现一致的设计与测试案例。

- [ ] **Step 1: 更新设计和测试文档**
- [ ] **Step 2: 运行后端全量测试、前端组件测试、构建和浏览器 E2E**
- [ ] **Step 3: 运行迁移并对本地页面做浏览器验证**

### Task 6: 仪表盘抓取入口与纯监控任务页

**Files:**
- Modify: `backend/app/api/v1/tasks.py`
- Modify: `backend/app/tasks/crawl_task.py`
- Modify: `frontend/src/views/DashboardView.vue`
- Modify: `frontend/src/views/TasksView.vue`
- Test: `backend/tests/test_config_task_duplicate_api.py`
- Test: `frontend/src/views/DashboardView.spec.ts`
- Test: `frontend/src/views/TasksView.spec.ts`

**Interfaces:**
- Consumes: 城市、关键词、时间范围、博主配置。
- Produces: 仪表盘发起抓取请求；任务页只展示监控信息。

- [ ] **Step 1: 写仪表盘选择提交及任务页无触发入口的失败测试**
- [ ] **Step 2: 实现任务参数校验与仪表盘选择器**
- [ ] **Step 3: 运行组件、接口和浏览器测试**

### Task 7: 去重完成后清理待处理数据

**Files:**
- Modify: `backend/app/api/v1/duplicates.py`
- Modify: `backend/app/api/v1/activities.py`
- Test: `backend/tests/test_config_task_duplicate_api.py`
- Test: `frontend/src/views/DuplicatesView.spec.ts`

**Interfaces:**
- Consumes: 保留 A 或保留 B 的去重决定。
- Produces: 待审核候选消失、未保留活动软删除、保留活动维持原审核状态。

- [ ] **Step 1: 写去重后候选不可见和未保留活动删除的失败测试**
- [ ] **Step 2: 实现默认 pending 查询和状态变更**
- [ ] **Step 3: 运行去重与活动回归测试**
