# 测试用例：前端 UI、按钮与路由跳转

## 测试环境

- Vue 3 + Element Plus
- Playwright + 本机 Google Chrome
- 前端接口通过 Playwright route mock 或真实 FastAPI 测试环境提供
- UI 禁止使用 Emoji 图标，菜单图标必须来自 `@element-plus/icons-vue`

## 已实现用例

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

## 待业务页面实现后启用

- TC-UI-007：登录表单校验、登录成功与错误提示。
- TC-UI-008：新增活动、编辑、状态审核、删除确认。
- TC-UI-009：活动筛选、分页和详情跳转。
- TC-UI-010：任务触发按钮、防重复点击、状态与日志刷新。
- TC-UI-011：去重双栏对比、合并与忽略按钮。
- TC-UI-012：周报生成、预览、Markdown 下载和 Excel 下载。
- TC-UI-013：配置中心城市、关键词、博主和 OpenCLI 连接测试。

## 运行

```bash
npm --prefix frontend run test:e2e
```
