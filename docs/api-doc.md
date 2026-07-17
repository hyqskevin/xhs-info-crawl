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

### GET /api/v1/activities

- 描述：活动列表（分页、筛选）
- Query：
  - `city`：城市代码
  - `type`：活动类型
  - `start_date` / `end_date`：举办时间范围
  - `status`：活动状态
  - `page` / `page_size`

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
        "status": "APPROVED",
        "created_at": "2025-07-14T02:30:00Z"
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

### GET /api/v1/activities/:id/images/:image_id

- 描述：读取该活动来源笔记的本地归档图片
- 鉴权：必须携带 Bearer Token；图片必须属于活动关联笔记，且文件路径必须位于 `DATA_DIR` 内
- 响应：图片二进制；不存在、归属不符或路径越界返回 `404`

### PUT /api/v1/activities/:id

- 描述：更新活动
- 请求：活动字段

### DELETE /api/v1/activities/:id

- 描述：删除活动

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

### GET /api/v1/tasks/:id/logs

- 描述：任务执行日志

### POST /api/v1/tasks/:id/restart

- 描述：按原参数继续失败或已停止任务，沿用原任务 ID，并跳过已经成功提取的笔记
- 限制：仅 `FAILED`、`STOPPED` 状态可调用；存在其他运行中或正在停止任务时返回 `409`
- 进度字段：`total_notes`、`downloaded_notes`、`ocr_notes`、`extracted_notes`、`failed_notes`、`skipped_notes`、`current_stage`、`current_note`

### POST /api/v1/tasks/:id/stop

- 描述：安全停止等待中或运行中的任务
- `PENDING` 立即变为 `STOPPED`；`RUNNING` 先变为 `STOP_REQUESTED`，当前笔记结束后变为 `STOPPED`
- 已成功处理、归档的数据全部保留；重复请求 `STOP_REQUESTED` 幂等返回

## 配置接口

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

### GET /api/v1/reports/:id

- 描述：周报详情（Markdown 内容）

### GET /api/v1/reports/:id/download

- 描述：下载报告文件
- Query：`format`（`md` / `xlsx`）
