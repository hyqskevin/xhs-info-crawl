# 前端双层测试覆盖设计

## 目标

每个可访问页面同时具备 Vitest 组件测试和 Playwright 浏览器功能测试；公共布局、路由守卫与 HTTP 鉴权单独具备模块测试。

## 覆盖边界

| 单元 | 组件/模块测试 | 浏览器测试 |
|---|---|---|
| LoginView | 必填校验、登录调用 | 登录成功/失败、路由守卫 |
| DashboardView | 健康状态渲染 | 服务状态、SQLite、无 Emoji |
| ActivitiesView | 列表加载、新增弹窗 | 新增、编辑、审核、删除、筛选、分页、详情 |
| TasksView | 列表加载、任务提交 | 防重复、暂停状态、日志 |
| DuplicatesView | 候选与双栏详情加载 | 双栏、保留 A/B、忽略 |
| ReportsView | 列表加载、生成 | 生成、预览、MD/XLSX 下载 |
| SettingsView | 配置加载、切换 | 城市/关键词/博主、删除、OpenCLI |
| AppLayout | 菜单、标题、退出 | 五个菜单路由跳转 |
| Router/HTTP | 未登录守卫、Token 请求头 | 由登录和业务页面测试间接覆盖 |

## 实现原则

- 组件测试 Mock API 边界，挂载真实 Vue 组件和 Element Plus 插件。
- 浏览器测试继续使用本机 Google Chrome，Mock 外部接口，验证真实 DOM、按钮和跳转。
- 每个测试验证用户可观察行为，不断言组件内部实现细节。
- `tests/test-frontend-ui-e2e.md` 维护唯一覆盖矩阵和最新数量。
