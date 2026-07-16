# 页面 UI 交互设计

## UI 实现规范

- 前端基于 Vue 3，统一使用 **Element Plus**（Element UI 的 Vue 3 对应版本）作为 UI 组件库。
- 图标统一使用 **`@element-plus/icons-vue`**，优先选择语义匹配的 Element Plus 官方图标。
- 禁止使用 Emoji 充当菜单、按钮、状态、提示或装饰图标；无合适图标时优先使用文字，不得用 Emoji 替代。
- 页面布局、表单、按钮、表格、分页、标签、提示、弹窗、抽屉、加载、空状态、上传等能力，优先组合 Element Plus 官方组件实现。
- 尽量不自行实现已有的通用 UI 组件，不重复造轮子。只有 Element Plus 明确不具备所需能力，且业务确有必要时，才允许创建自定义组件。
- 自定义组件必须复用 Element Plus 的颜色、字号、间距、圆角和交互状态，避免形成第二套视觉体系。
- 所有危险操作使用 Element Plus 的确认组件；成功、警告和错误反馈使用 `ElMessage`、`ElNotification` 或 `ElAlert`，不得自行绘制临时提示层。
- 图标按钮必须提供可访问名称或 Tooltip，不能只依赖图标表达含义。

### 优先使用的组件映射

| 场景 | Element Plus 组件 |
|------|-------------------|
| 页面框架与导航 | `ElContainer`、`ElAside`、`ElHeader`、`ElMain`、`ElMenu` |
| 列表与筛选 | `ElTable`、`ElForm`、`ElInput`、`ElSelect`、`ElDatePicker`、`ElPagination` |
| 状态展示 | `ElTag`、`ElBadge`、`ElProgress`、`ElResult`、`ElEmpty`、`ElSkeleton` |
| 编辑与详情 | `ElDialog`、`ElDrawer`、`ElDescriptions`、`ElTabs`、`ElImage` |
| 操作与反馈 | `ElButton`、`ElPopconfirm`、`ElMessageBox`、`ElMessage`、`ElNotification` |
| 配置录入 | `ElSwitch`、`ElInputNumber`、`ElUpload`、`ElTransfer` |

若设计稿与上述规范冲突，以复用 Element Plus 官方组件和图标为优先原则。

## 页面清单

| 页面 | 路径 | 主要功能 | 角色 |
|------|------|----------|------|
| 登录页 | `/login` | 账号密码登录 | 所有用户 |
| 仪表盘 | `/dashboard` | 本周数据概览、任务状态 | 管理员/运营 |
| 活动列表 | `/activities` | 查看、搜索、编辑、删除活动 | 管理员/运营 |
| 活动详情 | `/activities/:id` | 编辑单个活动字段 | 管理员/运营 |
| 去重审核 | `/duplicates` | 确认/合并/忽略去重候选 | 管理员/运营 |
| 配置中心 | `/settings` | 城市、关键词、博主白名单、OpenCLI | 管理员 |
| 任务日志 | `/tasks` | 查看历史任务与错误 | 管理员 |
| 周报管理 | `/reports` | 预览、下载、重新生成周报 | 管理员/运营 |

## 仪表盘

- 顶部卡片：本周抓取笔记数、生成活动数、待审核去重、最近任务状态
- 中部图表：最近 4 周活动数量趋势（按城市）
- 底部列表：最近 5 条任务日志，点击跳转详情

## 活动列表

- 筛选条件：城市、活动类型、举办时间、状态（已审核/待审核/已忽略）
- 表格字段：活动名称、城市、举办时间、地点、费用、类型、来源笔记、状态、操作
- 操作按钮：编辑、删除、忽略、加入周报
- 分页：每页 20 条

## 活动编辑弹窗

- 字段表单：活动名称、城市、举办时间、地点、费用、活动类型、来源链接、摘要
- 原始笔记预览：标题、正文、来源链接
- 图片列表：缩略图 + OCR 文字
- 操作：保存、取消、标记为已审核

## 去重审核

- 双栏对比：左侧活动 A，右侧活动 B
- 显示相似度得分、匹配字段高亮
- 操作：合并（保留 A / 保留 B / 合并为新记录）、不是重复、稍后处理

## 配置中心

### 城市管理

- 表格：城市名称、城市代码、启用状态
- 操作：新增、编辑、删除、启用/禁用

### 关键词词库

- 表格：关键词、关联城市、启用状态
- 操作：新增、编辑、删除、批量导入/导出

### 博主白名单

- 表格：博主主页 URL/ID、博主名称、关联城市、启用状态
- 操作：新增、编辑、删除

### OpenCLI 配置

- 字段：
  - `OPENCLI_CDP_ENDPOINT`：本地 Chrome CDP 端点（如 `http://localhost:9222`）
  - `OPENCLI_PROFILE`：默认 Chrome profile
  - 搜索间隔（秒，默认 10-15）
  - 单关键词抓取数量（默认 50-100）
- 操作：保存、测试连接

## 周报管理

- 列表：生成时间、覆盖城市、活动数量、操作（预览、下载 Excel/Markdown、删除）
- 预览页：按城市分组，按活动类型排序，显示 Markdown 渲染效果
- 下载：同一批审核结果可生成并下载 `.xlsx` 与 `.md` 文件
