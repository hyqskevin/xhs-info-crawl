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

### TC-UI-008：活动新增、编辑、审核与删除

- 缺少活动名称或开始时间时阻止提交。
- 填写表单并新增活动。
- 编辑活动名称并将状态审核为 `APPROVED`。
- 删除弹窗选择“取消”时不发请求；选择“确定”后执行软删除并提示成功。

### TC-UI-009：活动筛选、分页与详情

- 按城市筛选并校验请求参数。
- 点击下一页并校验 `page=2`。
- 打开详情抽屉并显示名称、时间、地点、费用和摘要。

### TC-UI-010：任务触发、状态与日志

- 提交抓取任务并显示成功提示。
- 请求进行中禁用“开始抓取”，强制再次点击也不会重复提交。
- 显示 `PAUSED` 状态和登录过期错误。
- 点击日志打开抽屉并显示任务日志。

### TC-UI-011：去重审核

- 双栏展示活动 A/B 的名称、时间和地点。
- 验证保留 A、保留 B 的合并请求。
- 验证“不是重复”忽略请求和成功提示。

### TC-UI-012：周报

- 生成周报并刷新列表。
- 打开 Markdown 内容预览。
- Markdown 下载按钮生成 `format=md` 地址。
- Excel 下载按钮生成 `format=xlsx` 地址。

### TC-UI-013：配置中心

- 新增城市、关键词和博主配置。
- 删除配置并刷新列表。
- OpenCLI 登录正常时显示成功提示。
- OpenCLI 返回认证错误时留在配置页，并提示在 Chrome 登录小红书。

可执行代码：

- `frontend/e2e/business.spec.ts`：各业务编号主路径。
- `frontend/e2e/documented-flows.spec.ts`：校验、异常、分页、防重复、双栏、下载等完整分支。
- `frontend/e2e/navigation.spec.ts`：仪表盘、Emoji 禁止规则与菜单跳转。

当前共有 13 个文档用例编号，对应 28 条可独立执行的 Chrome 浏览器场景；组件/模块层共有 11 个 Vitest 文件、12 条场景。

## 运行

```bash
npm --prefix frontend run test:e2e
```

Playwright 固定使用本机 Google Chrome，单 Worker 顺序执行，以避免共享本地开发服务器时产生干扰。
