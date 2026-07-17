# 数据库设计

## 实体关系图

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
│  source_image_indexes, source_url,                           │
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

## 表结构

### cities

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 主键 |
| name | VARCHAR(64) | 城市名称，如"上海" |
| code | VARCHAR(32) UNIQUE | 后端自动生成的内部关联键，前端不展示 |
| recent_filter | VARCHAR(16) DEFAULT "一周内" | 小红书原生时间筛选：不限/一天内/一周内/半年内 |
| enabled | BOOLEAN DEFAULT TRUE | 是否启用 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### keywords

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 主键 |
| word | VARCHAR(128) | 关键词，如"周末活动" |
| city_code | VARCHAR(32) FK | 关联城市 |
| enabled | BOOLEAN DEFAULT TRUE | 是否启用 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### bloggers

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

### crawl_tasks

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 主键 |
| type | VARCHAR(32) | 任务类型：keyword / blogger / manual |
| status | VARCHAR(32) | 状态 |
| params | JSONB | 任务参数 |
| total_notes | INT DEFAULT 0 | 抓取笔记总数 |
| downloaded_notes | INT DEFAULT 0 | 已完成详情及图片下载的笔记数 |
| ocr_notes | INT DEFAULT 0 | 已完成 OCR 阶段的笔记数（OCR 关闭时表示已跳过） |
| extracted_notes | INT DEFAULT 0 | 已完成活动提取与归档的笔记数 |
| success_notes | INT DEFAULT 0 | 成功处理数 |
| failed_notes | INT DEFAULT 0 | 失败数 |
| current_stage | VARCHAR(32) NULL | 当前阶段：SEARCHING / DOWNLOADING / OCR / EXTRACTING / ARCHIVING |
| current_note | TEXT NULL | 当前处理的笔记标题或来源链接 |
| started_at | TIMESTAMP | 开始时间 |
| finished_at | TIMESTAMP | 结束时间 |
| error_message | TEXT | 错误信息 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### notes

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

### note_images

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 主键 |
| note_id | INT FK | 关联笔记 |
| storage_key | VARCHAR(512) | 存储对象键；阶段一本地相对路径，阶段二 MinIO 对象键 |
| original_url | VARCHAR(512) | 原图 URL |
| ocr_text | TEXT | OCR 识别文字 |
| ocr_status | VARCHAR(32) | 状态：pending / success / failed |
| ocr_error | TEXT | OCR 错误信息 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### activities

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 主键 |
| note_id | INT FK | 主来源笔记 |
| related_note_ids | INT[] | 关联笔记 ID 列表 |
| source_image_indexes | JSON/INT[] | 提供该活动信息的归档图片序号 |
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

### duplicate_candidates

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

### weekly_reports

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

### users

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 主键 |
| username | VARCHAR(64) UNIQUE | 用户名 |
| password_hash | VARCHAR(256) | 密码哈希 |
| role | VARCHAR(32) | 角色：admin / editor |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### system_settings

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 主键 |
| key | VARCHAR(128) UNIQUE | 配置键 |
| value | JSONB | 配置值 |
| description | VARCHAR(256) | 说明 |
| updated_at | TIMESTAMP | 更新时间 |
