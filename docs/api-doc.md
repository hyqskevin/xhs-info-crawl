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
- 响应：包含活动字段、原始笔记、图片 OCR 结果

### PUT /api/v1/activities/:id

- 描述：更新活动
- 请求：活动字段

### DELETE /api/v1/activities/:id

- 描述：删除活动

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
  "type": "keyword",
  "cities": ["shanghai"],
  "keywords": ["周末活动", "展览"]
}
```

### GET /api/v1/tasks/:id/logs

- 描述：任务执行日志

## 配置接口

### GET /api/v1/settings/cities

- 描述：城市列表

### POST /api/v1/settings/cities

- 描述：新增城市

### PUT /api/v1/settings/cities/:id

- 描述：编辑城市

### DELETE /api/v1/settings/cities/:id

- 描述：删除城市

### GET /api/v1/settings/keywords

- 描述：关键词列表

### POST /api/v1/settings/keywords

- 描述：新增关键词

### PUT /api/v1/settings/keywords/:id

- 描述：编辑关键词

### DELETE /api/v1/settings/keywords/:id

- 描述：删除关键词

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
  "cities": ["shanghai", "beijing"]
}
```

### GET /api/v1/reports/:id

- 描述：周报详情（Markdown 内容）

### GET /api/v1/reports/:id/download

- 描述：下载报告文件
- Query：`format`（`md` / `xlsx`）
