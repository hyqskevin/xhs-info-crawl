# 仪表盘与周报需求对齐（方案 A 轻量版）— 设计 spec

> 对应 `docs/TODO.md` 待办 #11，用户 2026-07-27 拍板方案 A 轻量版。
> 范围：本周统计卡片（口径修正）+ 最近 5 条任务日志 + 周报删除 + 周报 Markdown 渲染预览。
> **明确不做**：「最近 4 周活动数量趋势」——与现有「抓取趋势（最近 20 次）」折线图信息重合，需要时单独立项。

## 背景（取证）

- SPEC 3.2 要求顶部卡片「本周抓取笔记数、生成活动数、待审核去重、最近任务状态」与底部「最近 5 条任务日志」。现状：`/dashboard/summary` 的 `weekly_notes_count`/`weekly_activities_count` 统计的是**全量**（非本周），且前端 DashboardView 根本没渲染这两个数字——卡片整组缺失。
- SPEC 3.7 要求周报「预览（Markdown 渲染）、下载、删除」。现状：预览对话框用 `{{ preview }}` 显示原始 Markdown 文本（未渲染）；无删除端点与按钮。

## 设计

### 后端

1. **`GET /dashboard/summary` 口径修正**：
   - `weekly_notes_count`：本周一 00:00（北京）以来抓取的笔记数 → `Note.created_at >= 本周起点`（`created_at` 为 UTC naive，起点按北京周一 00:00 换算 UTC naive）；
   - `weekly_activities_count`：同口径 `Activity.created_at >= 本周起点`；
   - 字段名保留（语义对齐 SPEC 的「本周」），`pending_duplicates`/`pending_review`/`last_task` 不变。
2. **`GET /dashboard/summary` 新增 `recent_logs`**：全库最新 5 条 `TaskLog`（`id desc`），每条含 `task_id, level, message, created_at`。
3. **`DELETE /reports/{report_id}`**：删除周报记录；不存在返回 404；重复删除幂等 404。周报无磁盘文件（下载为实时生成），只删 DB 行。

### 前端

4. **DashboardView 顶部统计卡片**：本周笔记数 / 本周活动数 / 待审核去重（`pending_duplicates`）三张 stat 卡片 + 复用现有最近任务卡片，数据源 `dashboard/summary`。
5. **DashboardView 底部「最近日志」**：渲染 `recent_logs` 5 条（级别 tag + 消息 + 时间），点击跳转 `/tasks`（任务列表可查日志）。
6. **ReportsView**：
   - 预览改用 `marked` 渲染 + `dompurify` 消毒后 `v-html`（笔记正文来自第三方抓取，必须消毒）；
   - 操作列加「删除」按钮（ElMessageBox 确认 → `DELETE /reports/{id}` → 刷新列表）。
   - 新增依赖：`marked`、`dompurify`、`@types/dompurify`(dev)。

## 验收

- 后端定向测试：周一口径（本周/上周数据分流正确）、`recent_logs` 取最新 5 条且含 task_id、DELETE 周报 200→404 幂等；
- 前端 spec：DashboardView 渲染三卡片与日志列表、ReportsView 删除按钮调 API、预览输出渲染后 HTML（含 `<h` 标签而非纯文本）；
- 后端全量 + 前端全量 + `npm run build` 全绿。
