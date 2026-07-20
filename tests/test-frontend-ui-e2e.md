# 测试用例：前端 UI、按钮与路由跳转

## 测试环境

- Vue 3 + Element Plus
- Playwright + 本机 Google Chrome
- 前端接口通过 Playwright route mock 或真实 FastAPI 测试环境提供
- UI 禁止使用 Emoji 图标，菜单图标必须来自 `@element-plus/icons-vue`

## 双层覆盖矩阵

每个实际使用的 Vue 组件必须有 Vitest 组件测试；每个可访问页面必须有 Playwright 浏览器功能测试。公共根组件、布局、路由和 HTTP 客户端不单独对应页面 URL，因此使用模块测试，并由各页面浏览器流程间接验证集成行为。

| 组件/模块 | Vitest 文件 | Chrome 功能场景 |
|---|---|---|
| `App.vue` | `src/App.spec.ts` | 所有路由页面启动均覆盖 |
| `AppLayout.vue` | `src/layouts/AppLayout.spec.ts` | TC-UI-002～006 菜单跳转 |
| `LoginView.vue` | `src/views/LoginView.spec.ts` | TC-UI-007 |
| `DashboardView.vue` | `src/views/DashboardView.spec.ts` | TC-UI-001 |
| `ActivitiesView.vue` | `src/views/ActivitiesView.spec.ts` | TC-UI-008～009 |
| `TasksView.vue` | `src/views/TasksView.spec.ts` | TC-UI-010 |
| `DuplicatesView.vue` | `src/views/DuplicatesView.spec.ts` | TC-UI-011 |
| `ReportsView.vue` | `src/views/ReportsView.spec.ts` | TC-UI-012 |
| `SettingsView.vue` | `src/views/SettingsView.spec.ts` | TC-UI-013 |
| 路由守卫 | `src/router/index.spec.ts` | TC-UI-007 未登录/已登录跳转 |
| HTTP 鉴权 | `src/api/http.spec.ts` | 登录后全部业务请求 |

未被路由或其他组件引用的 `PlaceholderView.vue` 已删除，不作为产品组件保留。

### TC-UI-001：仪表盘加载

- 访问 `/dashboard`
- 显示系统标题、后端健康状态和 SQLite 标签
- 发起抓取区域从配置中心加载城市、关键词、时间范围和博主。
- 城市为单选，关键词和博主为多选；切换城市时联动刷新可选项。
- 页面正文不包含 Emoji 图标

### TC-UI-002～006：侧边菜单跳转

逐一点击 Element Plus 菜单项，并验证 URL 与页面标题：

| 按钮 | 目标路径 |
|------|----------|
| 活动管理 | `/activities` |
| 去重审核 | `/duplicates` |
| 任务日志 | `/tasks` |
| 周报管理 | `/reports` |
| 配置中心 | `/settings` |

可执行代码：`frontend/e2e/navigation.spec.ts`。

### TC-UI-007：登录表单与访问控制

- 未登录访问业务路由会跳转 `/login`。
- 空用户名或密码时显示校验提示，且不会请求登录接口。
- 登录成功保存 Token 并进入仪表盘。
- 登录失败显示错误提示并停留在登录页。

### TC-UI-008：活动编辑、审核与删除

- 页面不提供手工新增活动入口，活动只来自抓取任务。
- 编辑活动名称并将“待审核”改为“已通过”。
- 删除弹窗选择“取消”时不发请求；选择“确定”后执行软删除并提示成功。

### TC-UI-009：活动筛选、分页与详情

- 使用城市名称下拉筛选并校验内部 `city` 请求参数。
- 按活动开始日期范围筛选并校验 `start_date`、`end_date`。
- 点击下一页并校验 `page=2`；修改每页数量时支持 10/20/50/100 并回到第一页。
- 打开详情抽屉并显示名称、时间、地点、费用和摘要。

### TC-UI-010：任务触发、状态与日志

- 在仪表盘选择城市、关键词、时间范围和博主后提交抓取任务并显示成功提示。
- 请求进行中禁用“开始抓取”，强制再次点击也不会重复提交。
- 任务日志页不显示抓取参数输入和“开始抓取”按钮。
- 显示“等待登录”状态和登录过期错误。
- 点击日志打开抽屉并显示任务日志。
- 仪表盘展示发现、下载、OCR、提取、失败、当前阶段与当前笔记，并轮询最新进度。
- 失败任务显示“继续抓取”，点击后请求同一任务 ID 的 restart 接口并显示 Toast。
- 运行中任务显示“停止抓取”，确认后请求 stop 接口；展示“正在停止”“已停止”和“已跳过”计数。
- 已停止任务显示“继续抓取”，沿用原任务 ID。

### TC-UI-011：去重审核

- 双栏展示活动 A/B 的名称、时间和地点。
- 验证保留 A、保留 B 的合并请求。
- 保留后候选从待处理列表消失，未保留活动不再出现在活动管理中，保留活动仍为待审核。
- 验证“不是重复”忽略请求和成功提示。

### TC-UI-012：周报

- 使用周选择器和已启用城市下拉生成单城市周报并刷新列表。
- 打开 Markdown 内容预览。
- Markdown 下载按钮生成 `format=md` 地址。
- Excel 下载按钮生成 `format=xlsx` 地址。

### TC-UI-013：配置中心

- 新增城市时同时保存多个关键词和小红书原生时间范围，不显示或输入城市代码。
- 编辑城市和博主配置。
- 删除配置并刷新列表。
- OpenCLI 登录正常时显示成功提示。
- OpenCLI 返回认证错误时留在配置页，并提示在 Chrome 登录小红书。
- OpenCLI 请求期间按钮旁显示独立 Loading 图标，请求完成后图标隐藏并显示 Toast。

### TC-UI-014：活动批量删除

- 未勾选活动时“批量删除”不可用。
- 勾选当前页多条活动后确认删除，请求体携带全部 ID，成功后显示删除数量并刷新列表。

### TC-UI-015：活动来源图片详情

- 活动详情抽屉桌面端宽度 70%，展示原文标题和原文链接。
- 详情表格下展示该笔记全部来源图片；点击缩略图打开 Element Plus 多图预览。
- 图片请求携带登录 Token；关闭抽屉后释放 Blob URL；无图时显示 Element Plus Empty。

### TC-UI-016：等待登录任务恢复

- `PAUSED` 任务卡展示“打开小红书登录”和“检测登录并继续”，其他状态不展示这组按钮。
- 打开登录页与检测登录使用独立 Loading，完成后隐藏并显示 Toast。
- 登录未完成时保持暂停并提示；登录成功后复用原任务继续。
- 组件测试：`frontend/src/views/DashboardView.spec.ts`。
- 浏览器功能测试：`frontend/e2e/documented-flows.spec.ts`。

### TC-UI-017：未知活动日期

- 活动列表、详情和编辑区域把空日期显示为“待确认”。
- 组件测试：`frontend/src/views/ActivitiesView.spec.ts`。
- 浏览器功能测试：`frontend/e2e/business.spec.ts`。

### TC-UI-018：批量审核通过并生成周报

- 未勾选活动时“批量通过”不可用。
- 勾选当前页多条活动后确认，通过请求体提交全部活动 ID。
- 成功后显示通过数量、清空选择并刷新列表。
- 在周报管理选择相同城市和活动所在周次后，生成结果活动数大于 0。
- 所选周次没有已通过活动时，Toast 直接展示后端原因，不生成空周报。
- 组件测试：`frontend/src/views/ActivitiesView.spec.ts`、`frontend/src/views/ReportsView.spec.ts`。
- 浏览器功能测试：`frontend/e2e/business.spec.ts`。

可执行代码：

- `frontend/e2e/business.spec.ts`：各业务编号主路径。
- `frontend/e2e/documented-flows.spec.ts`：校验、异常、分页、防重复、双栏、下载等完整分支。
- `frontend/e2e/navigation.spec.ts`：仪表盘、Emoji 禁止规则与菜单跳转。

当前文档用例同时覆盖组件测试与 Chrome 浏览器功能测试；实际数量以 `frontend/src/**/*.spec.ts` 和 `frontend/e2e/*.spec.ts` 的最新执行结果为准。

## 运行

```bash
npm --prefix frontend run test:e2e
```

Playwright 固定使用本机 Google Chrome，单 Worker 顺序执行，以避免共享本地开发服务器时产生干扰。
