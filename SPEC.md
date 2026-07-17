# 小红书本地活动信息抓取系统 — 详细设计文档（SPEC）

## 1. 项目概述

### 1.1 项目背景

面向本地生活/活动运营的内部工具，自动从小红书平台获取指定城市的近期活动信息，经过去重、清洗、格式化后，生成每周活动汇总 Excel 与 Markdown 文档，供运营团队审核、编辑和发布。

### 1.2 项目目标

- 每周自动抓取 1-3 个城市的本地活动相关小红书笔记
- 从笔记标题、正文、图片中提取活动时间、地点、费用、类型等关键字段
- 对活动进行去重、合并，生成结构化的周报
- 提供后台管理页面，支持配置、审核、编辑、导出

### 1.3 用户角色

| 角色 | 权限 | 使用场景 |
|------|------|----------|
| 系统管理员 | 配置城市、关键词、博主白名单、Cookie/登录态 | 初始化与维护 |
| 运营编辑 | 查看活动、审核去重、编辑字段、下载周报 | 每周内容生产 |
| 系统 | 定时执行抓取、清洗、生成周报 | 自动化流程 |

### 1.4 术语表

| 术语 | 定义 |
|------|------|
| 笔记 | 小红书单篇帖子（Post/Note） |
| 活动 | 从一篇或多篇笔记中提取出的单个具体活动；一篇合集笔记可以拆出多条活动 |
| 关键词词库 | 用于搜索的本地活动关键词集合 |
| 博主白名单 | 重点关注的本地活动博主列表 |
| 去重候选 | 系统判断可能重复的两条活动记录 |
| 周报 | 按城市和类型整理后的 Markdown 活动汇总 |

### 1.5 分阶段交付策略

项目分两个阶段交付：

- **阶段一（本地轻量版）**：保留 Vue 3、FastAPI、Celery Worker 和 Celery Beat；使用 SQLite、Celery filesystem broker 和本地文件系统；不使用 PostgreSQL、Redis、MinIO、Docker；在本机直接运行并交付 Excel 与 Markdown。
- **阶段二（完整技术栈版）**：保持前端、API 和核心业务服务不变，将基础设施升级为 PostgreSQL、Redis、MinIO 和 Docker Compose，并补充 Flower、反向代理、备份与生产监控。

数据库、任务消息和文件存储必须通过可替换边界接入，禁止在业务服务中硬编码阶段一实现。完整设计与迁移边界见 `docs/phase-roadmap.md`。

所有环境相关和可部署调整的变量统一写入根目录 `.env`，并在 `.env.example` 提供完整安全示例。后端、Celery、前端和启动脚本共享该配置入口；前端仅允许读取 `VITE_*` 变量，禁止将密钥暴露到浏览器。

---

## 2. 需求功能设计

### 2.1 功能清单

| 模块 | 功能 | 优先级 | 说明 |
|------|------|--------|------|
| 爬虫引擎 | 关键词搜索 | P0 | 按城市+关键词搜索近一周笔记 |
| 爬虫引擎 | 博主白名单抓取 | P0 | 按博主抓取近一周笔记 |
| 爬虫引擎 | 笔记详情获取 | P0 | 标题、正文、图片、互动数据 |
| 图片处理 | 图片下载 | P0 | 阶段一保存到本地目录；阶段二保存到 MinIO |
| 图片处理 | OCR 文字识别 | P0 | PaddleOCR 提取图片中的活动信息 |
| 数据清洗 | 字段提取 | P0 | 规则 + MiniMax LLM 提取活动时间/地点/费用等 |
| 数据清洗 | 活动去重 | P0 | 城市+日期+名称相似度模糊去重 |
| 数据存储 | 笔记/活动/图片存储 | P0 | 阶段一 SQLite + 本地文件；阶段二 PostgreSQL + MinIO |
| 任务调度 | 每周定时抓取 | P0 | Celery Beat 每周一执行 |
| 后台管理 | 仪表盘 | P0 | 本周数据概览 |
| 后台管理 | 活动列表 | P0 | 查看、筛选、编辑、删除活动 |
| 后台管理 | 去重审核 | P0 | 人工确认/合并去重候选 |
| 后台管理 | 配置中心 | P0 | 城市、关键词、博主白名单、OpenCLI 配置 |
| 后台管理 | 任务日志 | P0 | 查看每次任务执行状态与错误 |
| 后台管理 | 周报管理 | P0 | 预览、下载、重新生成 Excel 与 Markdown 周报 |
| 安全 | 频率控制 | P1 | 关键词搜索间隔 10-15 秒 |
| 安全 | 失败告警 | P1 | 任务失败发送通知 |
| 扩展 | 多数据源 | P2 | 后续可接入微博、豆瓣等 |

### 2.2 EARS 需求描述

#### Ubiquitous（全局约束）

- The system shall only crawl publicly visible 小红书 notes and shall not access private messages, user profiles, or comments beyond what is publicly displayed.
- The system shall store all sensitive configuration (e.g., MiniMax API key, database credentials) in environment variables or encrypted secret stores, never in source code.
- The system shall use a request interval of 10-15 seconds between consecutive keyword searches to minimize platform load and account risk.

#### Event-driven（事件触发）

- When the scheduled weekly crawl task starts at Monday 02:00, the system shall execute keyword searches for all configured cities and keywords, then download notes and images.
- When a note is successfully downloaded, the system shall trigger the OCR + field extraction pipeline within 5 minutes.
- When a note or its images describe multiple concrete activities, the system shall extract an activity array and persist every activity separately instead of collapsing the note into one record.
- When a crawl task stores source files, the system shall place the note Markdown, extracted-activity Markdown, Excel, and images under `data/archive/YYYY-MM-DD/task-{task_id}/`.
- The archived Markdown files shall use relative links to the images in the same task folder; each activity shall link only the source images identified by `source_image_indexes`.
- When an activity record is created or updated, the system shall recalculate duplicate candidates and flag high-confidence duplicates for review.
- When a user clicks "Generate Weekly Report" in the admin panel, the system shall produce Excel and Markdown files grouped by city and activity type within 30 seconds.

#### Unwanted（异常处理）

- If the 小红书 login session expires (OpenCLI returns authentication error), the system shall pause the crawl task and send an alert to the administrator.
- Before every OpenCLI search, note-detail, or download operation, the system shall run a login check and reuse the Cookie from the connected Chrome session without logging or persisting Cookie plaintext. On error code 77, it shall pause and wait for the user to log in before retrying.
- If OCR fails on an image, the system shall mark the image as "OCR_FAILED" and continue processing other images from the same note.
- If the field extraction pipeline fails to identify a required field (e.g., event time), the system shall mark the activity as "NEEDS_REVIEW" and include it in the admin review queue.
- If a duplicate candidate confidence score is between 0.4 and 0.7, the system shall place it in the manual review queue instead of auto-merging.

#### State-driven（状态行为）

- While a crawl task is running, the system shall prevent another crawl task from starting and return a "TASK_IN_PROGRESS" status.
- While a note is being processed (downloaded, OCR, extracted), its status shall be updated in real-time and visible in the task log.
- While an activity is in the "NEEDS_REVIEW" state, it shall not be included in the weekly report until reviewed and approved.

#### Optional（可选功能）

- Where the platform supports it, the system may allow searching notes by published date range (last 7 days) to reduce irrelevant results.
- Where multiple Chrome profiles are available, the system may rotate profiles to distribute crawl load across accounts.

---

## 3. 页面 UI 交互设计

### 3.0 UI 实现规范

- Vue 3 前端统一采用 Element Plus（Element UI 的 Vue 3 对应版本）。
- 图标统一使用 `@element-plus/icons-vue`，禁止使用 Emoji 充当菜单、按钮、状态、提示或装饰图标。
- 优先组合 Element Plus 官方的布局、菜单、表格、表单、分页、弹窗、抽屉、提示、空状态和上传等组件，尽量不自行实现已有的通用 UI。
- 仅当 Element Plus 明确缺少必要能力时才允许自定义组件；自定义部分必须沿用 Element Plus 的设计变量和交互方式。
- 危险操作、状态反馈和图标按钮分别使用 Element Plus 的确认、消息及 Tooltip/无障碍能力。
- 详细组件映射和约束见 `docs/ui-design.md`。

### 3.1 页面清单

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

### 3.2 仪表盘

- 顶部卡片：本周抓取笔记数、生成活动数、待审核去重、最近任务状态
- 中部图表：最近 4 周活动数量趋势（按城市）
- 底部列表：最近 5 条任务日志，点击跳转详情

### 3.3 活动列表

- 筛选条件：城市、活动类型、举办时间、状态（已审核/待审核/已忽略）
- 表格字段：活动名称、城市、举办时间、地点、费用、类型、来源笔记、状态、操作
- 操作按钮：编辑、删除、忽略、加入周报
- 分页：每页 20 条

### 3.4 活动编辑弹窗

- 字段表单：活动名称、城市、举办时间、地点、费用、活动类型、来源链接、摘要
- 原始笔记预览：标题、正文、来源链接
- 图片列表：缩略图 + OCR 文字
- 操作：保存、取消、标记为已审核

### 3.5 去重审核

- 双栏对比：左侧活动 A，右侧活动 B
- 显示相似度得分、匹配字段高亮
- 操作：合并（保留 A / 保留 B / 合并为新记录）、不是重复、稍后处理

### 3.6 配置中心

#### 3.6.1 城市管理

- 表格：城市名称、城市代码、启用状态
- 操作：新增、编辑、删除、启用/禁用

#### 3.6.2 关键词词库

- 表格：关键词、关联城市、启用状态
- 操作：新增、编辑、删除、批量导入/导出

#### 3.6.3 博主白名单

- 表格：博主主页 URL/ID、博主名称、关联城市、启用状态
- 操作：新增、编辑、删除

#### 3.6.4 OpenCLI 配置

- 字段：
  - `OPENCLI_CDP_ENDPOINT`：本地 Chrome CDP 端点（如 `http://localhost:9222`）
  - `OPENCLI_PROFILE`：默认 Chrome profile
  - 搜索间隔（秒，默认 10-15）
  - 单关键词抓取数量（默认 50-100）
- 操作：保存、测试连接

### 3.7 周报管理

- 列表：生成时间、覆盖城市、活动数量、操作（预览、下载 Excel/Markdown、删除）
- 预览页：按城市分组，按活动类型排序，显示 Markdown 渲染效果
- 下载：生成 `.xlsx` 与 `.md` 文件

---

## 4. 业务流程设计

### 4.1 整体流程

```
┌─────────────────┐
│ 配置中心        │
│ 城市/关键词/博主 │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────┐     ┌─────────────┐
│ 每周一 02:00    │───▶│ 关键词搜索  │───▶│ 博主抓取    │
│ Celery Beat 触发 │     │ (OpenCLI)   │     │ (OpenCLI)   │
└─────────────────┘     └──────┬──────┘     └──────┬──────┘
                               │                    │
                               ▼                    ▼
                        ┌─────────────┐     ┌─────────────┐
                        │ 下载笔记详情 │     │ 下载笔记详情 │
                        │ 标题/正文/图 │     │ 标题/正文/图 │
                        └──────┬──────┘     └──────┬──────┘
                               │                    │
                               └────────┬───────────┘
                                        ▼
                              ┌─────────────────┐
                              │ 图片写入统一存储  │
                              │ OCR 提取文字     │
                              └────────┬────────┘
                                       ▼
                              ┌─────────────────┐
                              │ 字段提取         │
                              │ 规则 + MiniMax   │
                              └────────┬────────┘
                                       ▼
                              ┌─────────────────┐
                              │ 活动去重         │
                              │ 模糊匹配 + 人工  │
                              └────────┬────────┘
                                       ▼
                              ┌─────────────────┐
                              │ 生成 Markdown   │
                              │ 周报             │
                              └────────┬────────┘
                                       ▼
                              ┌─────────────────┐
                              │ 运营审核/编辑    │
                              │ 下载发布         │
                              └─────────────────┘
```

### 4.2 任务状态流转

| 状态 | 说明 | 流转条件 |
|------|------|----------|
| PENDING | 任务等待执行 | 调度触发 |
| RUNNING | 任务执行中 | 开始搜索 |
| SEARCH_DONE | 搜索完成 | 所有关键词搜索结束 |
| DOWNLOADING | 下载笔记中 | 开始下载详情 |
| PROCESSING | 清洗提取中 | OCR + 字段提取 |
| DEDUPING | 去重中 | 字段提取完成 |
| COMPLETED | 完成 | 去重与周报生成完成 |
| FAILED | 失败 | 任何阶段出现不可恢复错误 |
| PAUSED | 暂停 | 登录态失效，等待人工处理 |

### 4.3 活动状态流转

| 状态 | 说明 | 流转条件 |
|------|------|----------|
| RAW | 原始提取 | 字段提取完成 |
| NEEDS_REVIEW | 需人工审核 | 关键字段缺失或去重边缘 |
| DUPLICATE_CANDIDATE | 去重候选 | 系统发现相似活动 |
| MERGED | 已合并 | 人工或自动合并 |
| APPROVED | 已审核 | 人工确认可用 |
| IGNORED | 已忽略 | 非活动或低质量 |
| PUBLISHED | 已发布 | 已加入周报 |

---

## 5. 接口文档

### 5.1 接口规范

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

### 5.2 认证接口

#### POST /api/v1/auth/login

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

### 5.3 仪表盘接口

#### GET /api/v1/dashboard/summary

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

### 5.4 活动接口

#### GET /api/v1/activities

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

#### GET /api/v1/activities/:id

- 描述：活动详情
- 响应：包含活动字段、原始笔记、图片 OCR 结果

#### PUT /api/v1/activities/:id

- 描述：更新活动
- 请求：活动字段

#### DELETE /api/v1/activities/:id

- 描述：删除活动

### 5.5 去重接口

#### GET /api/v1/duplicates

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
        "activity_a": { ... },
        "activity_b": { ... },
        "similarity": 0.82,
        "matched_fields": ["name", "city", "start_time"],
        "status": "pending"
      }
    ]
  }
}
```

#### POST /api/v1/duplicates/:id/merge

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

#### POST /api/v1/duplicates/:id/ignore

- 描述：忽略去重候选（不是重复）

### 5.6 任务接口

#### GET /api/v1/tasks

- 描述：任务列表
- Query：`status`、`page`、`page_size`

#### POST /api/v1/tasks/crawl

- 描述：手动触发抓取任务
- 请求：

```json
{
  "type": "keyword",
  "cities": ["shanghai"],
  "keywords": ["周末活动", "展览"]
}
```

#### GET /api/v1/tasks/:id/logs

- 描述：任务执行日志

### 5.7 配置接口

#### GET /api/v1/settings/cities

- 描述：城市列表

#### POST /api/v1/settings/cities

- 描述：新增城市

#### PUT /api/v1/settings/cities/:id

- 描述：编辑城市

#### DELETE /api/v1/settings/cities/:id

- 描述：删除城市

#### GET /api/v1/settings/keywords

- 描述：关键词列表

#### POST /api/v1/settings/keywords

- 描述：新增关键词

#### PUT /api/v1/settings/keywords/:id

- 描述：编辑关键词

#### DELETE /api/v1/settings/keywords/:id

- 描述：删除关键词

#### GET /api/v1/settings/bloggers

- 描述：博主白名单列表

#### POST /api/v1/settings/bloggers

- 描述：新增博主

#### PUT /api/v1/settings/bloggers/:id

- 描述：编辑博主

#### DELETE /api/v1/settings/bloggers/:id

- 描述：删除博主

#### GET /api/v1/settings/opencli

- 描述：OpenCLI 配置

#### PUT /api/v1/settings/opencli

- 描述：更新 OpenCLI 配置

#### POST /api/v1/settings/opencli/test

- 描述：测试 OpenCLI 连接

### 5.8 周报接口

#### GET /api/v1/reports

- 描述：周报列表

#### POST /api/v1/reports/generate

- 描述：生成周报
- 请求：

```json
{
  "week": "2025-W29",
  "cities": ["shanghai", "beijing"]
}
```

#### GET /api/v1/reports/:id

- 描述：周报详情（Markdown 内容）

#### GET /api/v1/reports/:id/download

- 描述：下载报告文件
- Query：`format`（`md` / `xlsx`）

---

## 6. 数据库设计

### 6.1 实体关系图

```
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│   cities     │       │   keywords   │       │  bloggers    │
└──────┬───────┘       └──────┬───────┘       └──────┬───────┘
       │                      │                      │
       │                      │                      │
       ▼                      ▼                      ▼
┌────────────────────────────────────────────────────────────┐
│                         crawl_tasks                          │
│  id, type, status, params, started_at, finished_at, error    │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            │ 1 : N
                            ▼
┌────────────────────────────────────────────────────────────┐
│                          notes                               │
│  id, task_id, platform_note_id, title, content, author_id,   │
│  author_name, source_url, likes, collects, comments,         │
│  published_at, city_code, keyword, status, raw_data,          │
│  created_at, updated_at                                      │
└──────────────────────┬─────────────────────────────────────┘
                       │
                       │ 1 : N
                       ▼
┌────────────────────────────────────────────────────────────┐
│                          note_images                         │
│  id, note_id, storage_key, ocr_text, ocr_status,             │
│  created_at                                                  │
└──────────────────────┬─────────────────────────────────────┘
                       │
                       │ N : 1
                       ▼
┌────────────────────────────────────────────────────────────┐
│                        activities                            │
│  id, note_id, name, city_code, start_time, end_time,        │
│  location, price, type, source_url, summary, status,         │
│  confidence, created_at, updated_at                          │
└──────────────────────┬─────────────────────────────────────┘
                       │
                       │ 1 : N
                       ▼
┌────────────────────────────────────────────────────────────┐
│                     duplicate_candidates                     │
│  id, activity_a_id, activity_b_id, similarity,               │
│  matched_fields, status, resolution, created_at,             │
│  resolved_at                                                 │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│                       weekly_reports                         │
│  id, week, cities, activity_count, content, status,            │
│  created_at, updated_at                                        │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│                          users                               │
│  id, username, role, password_hash, created_at,                │
│  updated_at                                                    │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│                       system_settings                        │
│  id, key, value, description, updated_at                     │
└────────────────────────────────────────────────────────────┘
```

### 6.2 表结构

#### cities

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 主键 |
| name | VARCHAR(64) | 城市名称，如"上海" |
| code | VARCHAR(32) UNIQUE | 城市代码，如"shanghai" |
| enabled | BOOLEAN DEFAULT TRUE | 是否启用 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

#### keywords

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 主键 |
| word | VARCHAR(128) | 关键词，如"周末活动" |
| city_code | VARCHAR(32) FK | 关联城市 |
| enabled | BOOLEAN DEFAULT TRUE | 是否启用 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

#### bloggers

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 主键 |
| platform_user_id | VARCHAR(128) | 平台用户 ID |
| username | VARCHAR(128) | 博主名称 |
| profile_url | VARCHAR(512) | 主页链接 |
| city_code | VARCHAR(32) FK | 关联城市 |
| enabled | BOOLEAN DEFAULT TRUE | 是否启用 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

#### crawl_tasks

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 主键 |
| type | VARCHAR(32) | 任务类型：keyword / blogger / manual |
| status | VARCHAR(32) | 状态 |
| params | JSONB | 任务参数 |
| total_notes | INT DEFAULT 0 | 抓取笔记总数 |
| success_notes | INT DEFAULT 0 | 成功处理数 |
| failed_notes | INT DEFAULT 0 | 失败数 |
| started_at | TIMESTAMP | 开始时间 |
| finished_at | TIMESTAMP | 结束时间 |
| error_message | TEXT | 错误信息 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

#### notes

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 主键 |
| task_id | INT FK | 关联任务 |
| platform_note_id | VARCHAR(128) UNIQUE | 平台笔记 ID |
| title | VARCHAR(512) | 标题 |
| content | TEXT | 正文 |
| author_id | VARCHAR(128) | 作者 ID |
| author_name | VARCHAR(128) | 作者名称 |
| source_url | VARCHAR(512) | 来源链接 |
| likes | INT | 点赞数 |
| collects | INT | 收藏数 |
| comments | INT | 评论数 |
| published_at | TIMESTAMP | 笔记发布时间 |
| city_code | VARCHAR(32) FK | 城市 |
| keyword | VARCHAR(128) | 搜索关键词 |
| status | VARCHAR(32) | 处理状态 |
| raw_data | JSONB | 原始抓取数据 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

#### note_images

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 主键 |
| note_id | INT FK | 关联笔记 |
| storage_key | VARCHAR(512) | 阶段一本地相对路径；阶段二 MinIO 对象键 |
| original_url | VARCHAR(512) | 原图 URL |
| ocr_text | TEXT | OCR 识别文字 |
| ocr_status | VARCHAR(32) | 状态：pending / success / failed |
| ocr_error | TEXT | OCR 错误信息 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

#### activities

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 主键 |
| note_id | INT FK | 主来源笔记 |
| related_note_ids | INT[] | 关联笔记 ID 列表 |
| name | VARCHAR(256) | 活动名称 |
| city_code | VARCHAR(32) FK | 城市 |
| start_time | TIMESTAMP | 活动开始时间 |
| end_time | TIMESTAMP | 活动结束时间 |
| location | VARCHAR(256) | 地点 |
| price | VARCHAR(128) | 费用 |
| type | VARCHAR(64) | 活动类型 |
| source_url | VARCHAR(512) | 来源链接 |
| summary | TEXT | 摘要 |
| tags | VARCHAR(64)[] | 标签 |
| status | VARCHAR(32) | 状态 |
| confidence | FLOAT | 字段提取置信度 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

#### duplicate_candidates

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 主键 |
| activity_a_id | INT FK | 活动 A |
| activity_b_id | INT FK | 活动 B |
| similarity | FLOAT | 相似度 |
| matched_fields | VARCHAR(64)[] | 匹配字段 |
| status | VARCHAR(32) | 状态：pending / merged / ignored |
| resolution | VARCHAR(32) | 合并结果：keep_a / keep_b / merge_new |
| merged_activity_id | INT FK | 合并后活动 ID |
| created_at | TIMESTAMP | 创建时间 |
| resolved_at | TIMESTAMP | 处理时间 |

#### weekly_reports

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 主键 |
| week | VARCHAR(16) | 周次，如"2025-W29" |
| cities | VARCHAR(32)[] | 覆盖城市 |
| activity_count | INT | 活动数量 |
| content | TEXT | Markdown 内容 |
| status | VARCHAR(32) | 状态：draft / published |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

#### users

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 主键 |
| username | VARCHAR(64) UNIQUE | 用户名 |
| password_hash | VARCHAR(256) | 密码哈希 |
| role | VARCHAR(32) | 角色：admin / editor |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

#### system_settings

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 主键 |
| key | VARCHAR(128) UNIQUE | 配置键 |
| value | JSONB | 配置值 |
| description | VARCHAR(256) | 说明 |
| updated_at | TIMESTAMP | 更新时间 |

---

## 7. 爬虫设计

### 7.1 爬虫工具

- **工具**：OpenCLI (`jackwener/OpenCLI`)
- **核心命令**：
  - `opencli xiaohongshu search --keyword "{keyword}" --limit {n}`
  - `opencli xiaohongshu note --url "{note_url}"`
  - `opencli xiaohongshu download "{note_url}" --output ./images`
- **登录态**：复用 Chrome 已登录 session，通过 CDP 连接

### 7.2 本地验证环境

#### 7.2.1 启动 Chrome 并开启 CDP

**macOS：**

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/chrome-debug-profile" \
  --remote-allow-origins="*"
```

**Linux：**

```bash
google-chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/chrome-debug-profile" \
  --remote-allow-origins="*"
```

启动后，在 Chrome 中登录小红书。

#### 7.2.2 设置环境变量并测试

```bash
export OPENCLI_CDP_ENDPOINT="http://localhost:9222"
opencli doctor
opencli xiaohongshu search --keyword "上海 周末活动" --limit 10 -f json
```

### 7.3 抓取流程

```python
def run_keyword_crawl(task_id: int, city_code: str, keyword: str):
    # 1. 调用 OpenCLI 搜索
    result = opencli.run(
        "xiaohongshu", "search",
        f"--keyword", f"{city_name} {keyword}",
        f"--limit", str(SEARCH_LIMIT),
        "-f", "json"
    )
    
    # 2. 解析搜索结果
    notes = parse_search_result(result)
    
    # 3. 过滤近 7 天笔记
    notes = filter_recent_notes(notes, days=7)
    
    # 4. 保存到 notes 表（待处理状态）
    save_notes(task_id, notes, city_code, keyword)
    
    # 5. 间隔 10-15 秒
    time.sleep(random.randint(10, 15))
```

### 7.4 笔记详情下载

```python
def download_note_details(note_id: int, note_url: str):
    # 1. 调用 OpenCLI 获取笔记详情
    detail = opencli.run("xiaohongshu", "note", "--url", note_url, "-f", "json")
    
    # 2. 保存标题、正文、互动数据
    update_note(note_id, detail)
    
    # 3. 通过统一 Storage 接口保存图片
    images = opencli.run("xiaohongshu", "download", note_url, "--output", tmp_dir)
    for img_path in images:
        storage_key = storage.save(img_path)
        save_note_image(note_id, storage_key, original_url=...)
```

### 7.5 错误处理

| 错误码 | 含义 | 处理策略 |
|--------|------|----------|
| 0 | 成功 | 继续 |
| 66 | 结果为空 | 记录并跳过 |
| 69 | Browser Bridge 未连接 | 检查 Chrome/CDP，重试 |
| 75 | 超时 | 重试，最多 3 次 |
| 77 | 需要认证 | 暂停任务，发送告警 |
| 78 | 配置错误 | 记录错误，人工检查 |
| 130 | 用户中断 | 记录任务中断 |

### 7.6 反爬策略

- 关键词搜索间隔：10-15 秒
- 单账号每周搜索总量不超过 500 次（可配置）
- 使用 OpenCLI 的真实浏览器行为，避免低级别 HTTP 请求
- 遇到验证码或登录失效，立即暂停并告警
- 不抓取评论、私信等敏感内容

---

## 8. 技术栈与工程架构

### 8.1 技术栈

| 层级 | 技术选型 | 说明 |
|------|----------|------|
| 前端 | Vue 3 + Element Plus | 后台管理页面 |
| 后端 | Python 3.11 + FastAPI | REST API |
| 爬虫 | OpenCLI (Node.js) | 小红书数据抓取 |
| 任务队列 | Celery | 阶段一 filesystem broker；阶段二 Redis |
| 数据库 | SQLAlchemy + Alembic | 阶段一 SQLite；阶段二 PostgreSQL 15 |
| 对象存储 | Storage 接口 | 阶段一本地文件；阶段二 MinIO |
| OCR | PaddleOCR | 图片文字识别 |
| LLM | MiniMax-M3 API | 结合正文与 PaddleOCR 文本进行字段提取 |
| 部署 | 本机进程 / Docker Compose | 阶段一本机直接运行；阶段二容器化 |
| 监控 | 日志 / Flower | 阶段一任务日志；阶段二增加 Flower |

### 8.2 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                         用户层                               │
│              Vue 3 + Element Plus 管理后台                    │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTP / JWT
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                         API 层                               │
│              Python 3.11 + FastAPI                          │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                       任务调度层                             │
│              Celery Beat + Celery Workers                    │
│              filesystem broker（阶段一）                     │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                       处理管道                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ OpenCLI     │  │ PaddleOCR   │  │ MiniMax API         │ │
│  │ 爬虫        │  │ 图片 OCR    │  │ 字段提取            │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                        数据层                                │
│  ┌─────────────────┐  ┌─────────────────┐                    │
│  │ SQLite          │  │ 本地文件系统    │                    │
│  │ 结构化数据      │  │ 图片与报告      │                    │
│  └─────────────────┘  └─────────────────┘                    │
└─────────────────────────────────────────────────────────────┘
```

### 8.3 工程目录结构

```
xhs-info-crawl/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── v1/
│   │   │   │   ├── auth.py
│   │   │   │   ├── activities.py
│   │   │   │   ├── duplicates.py
│   │   │   │   ├── tasks.py
│   │   │   │   ├── settings.py
│   │   │   │   └── reports.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   └── database.py
│   │   ├── models/
│   │   │   ├── city.py
│   │   │   ├── keyword.py
│   │   │   ├── blogger.py
│   │   │   ├── note.py
│   │   │   ├── activity.py
│   │   │   └── task.py
│   │   ├── schemas/
│   │   ├── repositories/
│   │   ├── services/
│   │   │   ├── crawler.py
│   │   │   ├── ocr.py
│   │   │   ├── extraction.py
│   │   │   ├── dedup.py
│   │   │   └── report.py
│   │   ├── storage/
│   │   ├── tasks/
│   │   │   └── crawl_task.py
│   │   └── main.py
│   ├── migrations/
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── views/
│   │   ├── components/
│   │   ├── router/
│   │   ├── store/
│   │   └── App.vue
│   └── package.json
├── data/
│   ├── app.db
│   ├── images/
│   ├── exports/
│   └── celery/
├── scripts/
├── .env.example
├── README.md
└── docs/
    └── SPEC.md
```

### 8.4 阶段二 Docker Compose 参考配置

以下配置仅属于阶段二，不是阶段一运行依赖。

```yaml
version: '3.8'

services:
  db:
    image: postgres:15
    environment:
      POSTGRES_USER: xhs
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: xhs_crawler
    volumes:
      - pg_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
    volumes:
      - minio_data:/data
    ports:
      - "9000:9000"
      - "9001:9001"

  backend:
    build: ./backend
    environment:
      DATABASE_URL: postgresql://xhs:${DB_PASSWORD}@db:5432/xhs_crawler
      REDIS_URL: redis://redis:6379/0
      MINIO_ENDPOINT: minio:9000
      MINIO_ACCESS_KEY: ${MINIO_ROOT_USER}
      MINIO_SECRET_KEY: ${MINIO_ROOT_PASSWORD}
      MINIO_BUCKET: xhs-images
      OPENCLI_CDP_ENDPOINT: ${OPENCLI_CDP_ENDPOINT}
      MINIMAX_API_KEY: ${MINIMAX_API_KEY}
    depends_on:
      - db
      - redis
      - minio
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app

  celery-worker:
    build: ./backend
    command: celery -A app.tasks worker -l info
    environment:
      DATABASE_URL: postgresql://xhs:${DB_PASSWORD}@db:5432/xhs_crawler
      REDIS_URL: redis://redis:6379/0
      MINIO_ENDPOINT: minio:9000
      MINIO_ACCESS_KEY: ${MINIO_ROOT_USER}
      MINIO_SECRET_KEY: ${MINIO_ROOT_PASSWORD}
      MINIO_BUCKET: xhs-images
      OPENCLI_CDP_ENDPOINT: ${OPENCLI_CDP_ENDPOINT}
      MINIMAX_API_KEY: ${MINIMAX_API_KEY}
    depends_on:
      - db
      - redis
      - minio

  celery-beat:
    build: ./backend
    command: celery -A app.tasks beat -l info
    environment:
      DATABASE_URL: postgresql://xhs:${DB_PASSWORD}@db:5432/xhs_crawler
      REDIS_URL: redis://redis:6379/0
    depends_on:
      - db
      - redis

  flower:
    build: ./backend
    command: celery -A app.tasks flower --port=5555
    environment:
      REDIS_URL: redis://redis:6379/0
    ports:
      - "5555:5555"
    depends_on:
      - redis

  frontend:
    build: ./frontend
    ports:
      - "80:80"
    depends_on:
      - backend

volumes:
  pg_data:
  redis_data:
  minio_data:
```

---

## 9. 安全与高并发设计

### 9.1 安全设计

#### 9.1.1 认证与授权

- 后台使用 JWT Token 认证
- 区分管理员和运营编辑角色
- 密码使用 bcrypt 哈希存储

#### 9.1.2 敏感信息保护

- 所有 API Key、数据库密码及阶段二 MinIO 密钥存放于 `.env` 文件
- 生产环境使用 Docker secrets 或环境变量注入
- 禁止在代码仓库中提交真实密钥

#### 9.1.3 爬虫合规

- 仅抓取公开可见笔记信息
- 不抓取用户手机号、微信号、地址等个人隐私
- 不抓取评论中可能涉及的个人信息
- 数据保留期限：原始图片/笔记 90 天，清洗后活动信息长期保留

#### 9.1.4 网络安全

- 后端 API 默认不暴露公网，通过 Nginx 反向代理
- 生产环境启用 HTTPS
- 限制 Flower 等管理面板的访问来源 IP

### 9.2 高并发设计

本项目为**低频批处理任务**，不需要高并发架构。

| 场景 | 策略 |
|------|------|
| 每周一次抓取 | 单机 Celery Worker 足够 |
| 图片 OCR | 异步任务队列，单线程或少量并发 |
| 后台页面访问 | 单实例 FastAPI 可支持数十并发 |
| 未来扩展 | 可水平扩展 Celery Worker 和 FastAPI 实例 |

### 9.3 稳定性设计

- 任务失败自动重试 3 次，间隔 5 分钟
- 数据库连接池管理
- 阶一本地数据目录定期备份；阶段二 MinIO 开启数据卷持久化
- 关键任务（抓取、OCR、提取）记录详细日志
- 阶一备份 SQLite；阶段二定期备份 PostgreSQL

---

## 10. 部署方案

### 10.1 阶段一本地开发环境

```bash
make init
make dev-api
make dev-worker
make dev-beat
make dev-web
```

阶段一不安装 Docker、PostgreSQL、Redis 或 MinIO。SQLite、图片、导出和 broker 数据分别位于 `data/app.db`、`data/images/`、`data/exports/` 和 `data/celery/`。

### 10.2 阶段二完整技术栈部署

- 使用 Docker Compose 编排 PostgreSQL、Redis、MinIO、FastAPI、Celery Worker、Celery Beat、Flower 和前端。
- OpenCLI 与 Chrome 可继续在个人电脑运行，通过 CDP 与后端连接。
- 服务器化 Chrome、反向代理、HTTPS、备份和监控属于阶段二部署优化。

### 10.3 环境变量示例

```bash
APP_ENV=development
SECRET_KEY=replace_me
JWT_EXPIRE_HOURS=24
DATABASE_URL=sqlite:///./data/app.db
CELERY_BROKER_URL=filesystem://
CELERY_BROKER_FOLDER=./data/celery
LOCAL_IMAGE_DIR=./data/images
EXPORT_DIR=./data/exports
OPENCLI_CDP_ENDPOINT=http://localhost:9222
MINIMAX_API_KEY=
```

---

## 11. 验收标准

### 11.1 功能验收

| 验收项 | 标准 |
|--------|------|
| 关键词搜索 | 每周一自动执行，能按城市+关键词返回笔记列表 |
| 图片下载 | 阶一保存到本地目录并可通过 API 访问；阶段二保存到 MinIO |
| OCR 识别 | 图片中的文字被正确提取并存入数据库 |
| 字段提取 | 活动时间、地点、费用等字段被正确提取 |
| 活动去重 | 相似活动被识别并进入审核队列 |
| 后台页面 | 所有页面可正常访问、操作 |
| 报告生成 | 每周可生成内容一致的 Excel 与 Markdown 文件并下载 |
| 本地运行 | 阶一无需 Docker、PostgreSQL、Redis 或 MinIO，可直接启动前端、API、Worker、Beat |

### 11.2 性能验收

| 验收项 | 标准 |
|--------|------|
| 单次抓取完成时间 | 3 个城市 × 20 关键词 ≤ 6 小时（按 10-15 秒间隔） |
| 单篇笔记处理时间 | 下载 + OCR + 提取 ≤ 5 分钟 |
| 后台页面加载时间 | 列表页 ≤ 2 秒 |
| 周报生成时间 | ≤ 30 秒 |

### 11.3 稳定性验收

| 验收项 | 标准 |
|--------|------|
| 任务失败率 | 低于 5% |
| 登录态失效告警 | 30 分钟内通知管理员 |
| 数据备份 | 数据库每日自动备份 |

阶段二验收要求是在上述功能不回退的前提下完成 PostgreSQL、Redis、MinIO 和 Docker Compose 替换。

---

## 12. 风险与待办

### 12.1 风险清单

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| 小红书账号被封/风控 | 高 | 控制频率、使用 OpenCLI 真实浏览器、登录态失效告警 |
| OpenCLI 命令变更或失效 | 高 | 定期更新 OpenCLI、保留备用抓取方案评估 |
| MiniMax API 不稳定或成本过高 | 中 | 优化规则提取比例、设置 API 调用上限 |
| PaddleOCR 图片文字识别准确率低 | 中 | 对图片 OCR 结果做后处理、人工抽检 |
| 活动时间/地点提取错误 | 中 | 置信度低的进入人工审核队列 |
| 服务器部署 Chrome 复杂 | 中 | 先本地验证，后续再研究服务器化方案 |

### 12.2 待办事项

项目待办事项统一维护在 [`docs/TODO.md`](docs/TODO.md)，该文件是当前待办、后续优化、阶段二事项和完成记录的唯一维护入口。

---

## 13. 附录

### 13.1 周报 Markdown 模板示例

```markdown
# 上海本周活动精选（2025.07.14 - 2025.07.20）

## 演出

### 夏日音乐节
- **时间**：2025.07.20 18:00 - 22:00
- **地点**：徐汇滨江
- **费用**：免费
- **来源**：[小红书笔记](https://www.xiaohongshu.com/...)
- **简介**：户外音乐节，现场有多个乐队表演...

## 展览

### 当代艺术展
- **时间**：2025.07.15 - 2025.08.15
- **地点**：上海当代艺术博物馆
- **费用**：60 元
- **来源**：[小红书笔记](https://www.xiaohongshu.com/...)
- **简介**：...

---

*本内容由系统自动抓取，仅供内部参考，请以主办方信息为准。*
```

### 13.2 参考链接

- OpenCLI 仓库：https://github.com/jackwener/OpenCLI
- OpenCLI CDP 文档：https://github.com/jackwener/OpenCLI/blob/main/docs/advanced/cdp.md
- FastAPI 文档：https://fastapi.tiangolo.com/
- Celery 文档：https://docs.celeryq.dev/
- PaddleOCR 文档：https://github.com/PaddlePaddle/PaddleOCR
- MiniMax 文档：https://www.minimaxi.com/

---

文档版本：v1.0
最后更新：2025-07-16
