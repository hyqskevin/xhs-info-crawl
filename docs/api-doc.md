# 接口文档

## 接口规范

- 基础路径：`/api/v1`
- 认证：JWT Token（Bearer）
- 响应格式：

```json
{
  "code": 200,
  "message": "success",
  "data": {},
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 100
  }
}
```

## 认证接口

### POST /api/v1/auth/login

- 描述：用户登录
- 请求：

```json
{
  "username": "admin",
  "password": "******"
}
```

- 响应：

```json
{
  "code": 200,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "expires_in": 86400
  }
}
```

## 仪表盘接口

### GET /api/v1/dashboard/summary

- 描述：获取仪表盘概览数据
- 响应：

```json
{
  "code": 200,
  "data": {
    "weekly_notes_count": 320,
    "weekly_activities_count": 86,
    "pending_duplicates": 12,
    "pending_review": 5,
    "last_task": {
      "id": "task-20250714",
      "status": "COMPLETED",
      "started_at": "2025-07-14T02:00:00Z",
      "finished_at": "2025-07-14T03:12:00Z"
    }
  }
}
```

## 活动接口

子活动无审核状态，审核完全收敛到推文维度（`/api/v1/notes`）。

### GET /api/v1/activities

- 描述：活动列表（分页、筛选）
- Query：
  - `city`：城市 `code`（如 `city-99f1e469`、`nb`），必须从 `GET /api/v1/settings/cities` 取得，前端按 `City.code` 传参；不允许中文字面量
  - `type`：活动类型
  - `start_date` / `end_date`：举办时间范围
  - `page` / `page_size`
- 默认不含已软删除活动（`deleted_at IS NOT NULL`）。

- 响应：

```json
{
  "code": 200,
  "data": {
    "items": [
      {
        "id": "act-001",
        "name": "夏日音乐节",
        "city": "上海",
        "start_time": "2025-07-20T18:00:00Z",
        "end_time": "2025-07-20T22:00:00Z",
        "location": "徐汇滨江",
        "price": "免费",
        "type": "演出",
        "source_url": "https://www.xiaohongshu.com/...",
        "confidence": 0.85,
        "created_at": "2025-07-14T02:30:00Z",
        "deleted_at": null
      }
    ]
  },
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 86
  }
}
```

### GET /api/v1/activities/:id

- 描述：活动详情
- 响应：包含活动字段、原始笔记 `note`、来源图片 `images` 和图片 OCR 状态
- 默认不含软删除活动；可加 `?include_deleted=true` 查询已软删活动

### GET /api/v1/activities/:id/images/:image_id

- 描述：读取该活动来源笔记的本地归档图片
- 鉴权：必须携带 Bearer Token；图片必须属于活动关联笔记，且文件路径必须位于 `DATA_DIR` 内
- 响应：图片二进制；不存在、归属不符或路径越界返回 `404`

### POST /api/v1/activities/batch/approve

- 描述：**已下线**。
- 响应：`410 Gone`，`detail="活动审核已迁到推文维度，请使用 /api/v1/notes/{id}/review"`。

### PUT /api/v1/activities/:id

- 描述：更新活动（名称、地点、城市、开始/结束时间、简介、来源 URL）
- 请求：活动字段
- 不接受 `status` 字段；如传入返回 `422`，detail 提示“活动已取消审核状态字段”

### DELETE /api/v1/activities/:id

- 描述：软删除活动（`deleted_at = NOW()`）

### DELETE /api/v1/activities/batch

- 描述：批量软删除活动管理当前页勾选的数据
- 请求：`{"ids": [1, 2, 3]}`
- 响应：`{"deleted_count": 3}`；不存在或已删除的 ID 不重复计数

## 去重接口

### GET /api/v1/duplicates

- 描述：去重候选列表
- Query：`status`（pending/resolved/ignored）、`page`

- 响应：

```json
{
  "code": 200,
  "data": {
    "items": [
      {
        "id": "dup-001",
        "activity_a": { },
        "activity_b": { },
        "similarity": 0.82,
        "matched_fields": ["name", "city", "start_time"],
        "status": "pending"
      }
    ]
  }
}
```

### POST /api/v1/duplicates/:id/merge

- 描述：合并去重候选
- 请求：

```json
{
  "keep": "a",
  "merged_activity": {
    "name": "...",
    "start_time": "..."
  }
}
```

### POST /api/v1/duplicates/:id/ignore

- 描述：忽略去重候选（不是重复）

## 任务接口

### GET /api/v1/tasks

- 描述：任务列表
- Query：`status`、`page`、`page_size`

### POST /api/v1/tasks/crawl

- 描述：手动触发抓取任务
- 请求：

```json
{
  "type": "mixed",
  "city": "city-a1b2c3d4",
  "keywords": ["周末活动", "展览"],
  "recent_filter": "一周内",
  "blogger_ids": [1, 3]
}
```

- 入口：仪表盘。
- 城市必须是配置中心已启用城市；关键词和博主必须属于该城市。
- 时间范围仅允许：不限、一天内、一周内、半年内。
- `keywords` / `blogger_ids` 字段说明：
  - 字段省略或 `null` → 用城市 enabled 配置（默认行为）
  - 字段是 `[]` 空数组 → 用户主动禁用该项（不与默认合并）
  - 字段是非空列表 → 覆盖默认
- 入口校验：effective 抓取范围（关键词 ∪ 博主）不能同时为空，否则返回 422 `请至少启用一个关键词或博主`。

### GET /api/v1/tasks/:id/logs

- 描述：任务执行日志

### POST /api/v1/tasks/:id/restart

- 描述：按原参数继续失败、已停止或等待登录任务，沿用原任务 ID，并跳过已经成功提取的笔记
- 限制：`FAILED`、`STOPPED`、`PAUSED` 可调用；`PAUSED` 会先检测 OpenCLI 登录态，未登录返回 `409/AUTH_REQUIRED` 且保持暂停
- 安全验证：验证码/风控会把任务置为 `PAUSED` 并保留浏览器页；人工完成后调用本接口检测并继续原任务。
- 进度字段：`total_notes`、`downloaded_notes`、`ocr_notes`、`extracted_notes`、`failed_notes`、`skipped_notes`、`skipped_activities`、`current_stage`、`current_note`

### POST /api/v1/tasks/:id/stop

- 描述：停止等待中或运行中的抓取任务，不关闭 Celery worker 或用户整个 Chrome
- `PENDING`、`FAILED`、`PAUSED` 立即变为 `STOPPED`；`RUNNING` 先提交 `STOP_REQUESTED`，再结束已登记的 OpenCLI 子进程并由 worker 确认为 `STOPPED`
- 停止后每条业务 OpenCLI 命令在启动前、PID 登记后和子进程退出后校验执行权；目标是 5 秒内不再出现新的业务命令
- crawler session 标签页在异常路径也会执行最多 10 秒的最佳努力关闭；包含清理时最迟 15 秒进入 `STOPPED`
- 标签页清理失败写入任务 WARNING 日志，但不把已经停止的任务改为 `FAILED`
- 已成功处理、归档的数据全部保留；重复请求 `STOP_REQUESTED` 或 `STOPPED` 幂等返回

## 配置接口

### POST /api/v1/settings/opencli/open-login

- 描述：在本机 Chrome 打开 `.env` 配置的 `XHS_LOGIN_URL`，用于恢复 `PAUSED` 抓取任务。
- 接口不读取、返回或记录 Cookie；浏览器启动失败返回 `503` 和可手动访问的地址。

### GET /api/v1/settings/cities

- 描述：城市列表；返回城市名称、内部 code、关键词数组、抓取时间范围和启用状态

### POST /api/v1/settings/cities

- 描述：新增城市，同时提交 `keywords` 与 `recent_filter`；`code` 由后端自动生成

### PUT /api/v1/settings/cities/:id

- 描述：编辑城市名称、关键词、抓取时间范围和启用状态

### DELETE /api/v1/settings/cities/:id

- 描述：删除城市

关键词接口为内部兼容接口；管理端统一通过城市接口维护城市与关键词组合。

### GET /api/v1/settings/bloggers

- 描述：博主白名单列表

### POST /api/v1/settings/bloggers

- 描述：新增博主

### PUT /api/v1/settings/bloggers/:id

- 描述：编辑博主

### DELETE /api/v1/settings/bloggers/:id

- 描述：删除博主

### GET /api/v1/settings/opencli

- 描述：OpenCLI 配置

### PUT /api/v1/settings/opencli

- 描述：更新 OpenCLI 配置

### POST /api/v1/settings/opencli/test

- 描述：测试 OpenCLI 连接

## 周报接口

### GET /api/v1/reports

- 描述：周报列表

### POST /api/v1/reports/generate

- 描述：生成周报
- 请求：

```json
{
  "week": "2025-W29",
  "cities": ["shanghai"]
}
```

- 限制：阶段一只允许选择一个已启用城市，`cities` 数组长度必须为 1；周次由前端周选择器转换为 ISO week。
- 筛选：只导出所选城市、所选 ISO 周内的 `APPROVED` 活动。
- 空结果：没有已通过活动时返回 `422`，提示先在活动管理中审核通过，不生成空周报。

### GET /api/v1/reports/:id

- 描述：周报详情（Markdown 内容）

### GET /api/v1/reports/:id/download

- 描述：下载报告文件
- Query：`format`（`md` / `xlsx`）
# 2026-07-20 推文主资源补充

- `GET /api/v1/notes`：按城市、推文发布时间、审核状态分页查询，一行一篇推文。
- `GET /api/v1/notes/{id}`：返回推文正文、原文链接、图片 OCR 和全部有效子活动。
- `GET /api/v1/notes/{id}/images/{image_id}`：读取推文来源图片。
- `POST /api/v1/notes/batch/approve`：推文级批量审核。
- `DELETE /api/v1/notes/batch`：推文级批量软删除。
- `/api/v1/duplicates` 已改为推文 A/B 候选，保留一方会将另一方标记为 `MERGED`。
- 创建与重启抓取任务后，响应中的 `run_token` 会随 Celery 消息传递，用于拒绝陈旧执行。
- 周报按推文发布时间和单城市生成，响应同时返回 `note_count` 与 `activity_count`。

## 2026-07-21 推文编辑与单条审核

### PUT /api/v1/notes/:id

- 描述：编辑一篇可见推文的标题、正文、城市和发布时间。
- 请求：

```json
{
  "title": "更新后的推文标题",
  "content": "更新后的正文",
  "city_code": "shanghai",
  "published_at": "2026-07-21T10:30:00Z"
}
```

- `title` 去除首尾空白后不能为空，最大 512 字符。
- `city_code` 必须对应已启用城市。
- `published_at` 可以为 `null`，表示发布时间待确认。
- `source_url` 不属于可编辑字段；即使请求中额外携带也不会修改数据库原文链接。
- 成功返回更新后的推文详情；推文不存在、已删除或已合并返回 `404`，字段或城市无效返回 `422`。

### POST /api/v1/notes/:id/review

- 描述：审核一篇推文，不依赖列表批量勾选。
- 请求：`{"status": "APPROVED"}` 或 `{"status": "REJECTED"}`。
- 成功响应：`{"id": 1, "review_status": "APPROVED"}`。
- 其他状态返回 `422`；推文不存在、已删除或已合并返回 `404`。
- `POST /api/v1/notes/batch/approve` 保持不变，继续支持批量通过。
