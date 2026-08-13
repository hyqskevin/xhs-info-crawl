# 活动管理（推文列表）按关键词组 / 博主组筛选

## 1. 背景

用户 2026-08-13 提出：
- 已有"关键词组"和"博主组"配置，但活动管理（ActivitiesView 推文列表）只能按"单个关键词"+"单个博主"筛选，**不能按组筛选**
- 抓取时配置是按组/自定义关键词二选一，但落库的推文没有记录"本次是用哪个关键词、哪个博主抓到的"
- 推文落库时也没记录点赞/收藏/评论数，只能在详情查看时才临时抓取

预期业务流：

```
配置 → 抓取（按组或自定义）→ 入库（携带来源关键词/博主/赞藏评）→ 列表筛选
```

目前列表只能按入库后的 title/content/blogger profile_url 反查，与抓取配置脱钩，需要新方案。

## 2. 目标

1. 推文入库时落库以下字段：
   - `matched_keywords: list[str]` — 本次抓取命中的关键词
   - `matched_blogger_id: int?` — 本次抓取命中的博主 ID（仅博主维度）
   - `matched_blogger_username: str?` — 博主用户名快照
   - `like_count / collect_count / comment_count: int?` — 详情抓取阶段拿到的互动数
2. 后端 `GET /api/v1/notes` 新增 4 个筛选参数：
   - `keyword_group_ids: list[int]` — 与 `keyword` 互斥；多选 OR
   - `blogger_group_ids: list[int]` — 与 `blogger_id` 互斥；多选 OR
3. 前端 ActivitiesView 把现有"关键词"+"博主"两个筛选器改为 Radio 切换组（自定义 vs 组），互斥
4. 列表展示新增"点赞 / 收藏 / 评论"3 列

## 3. 设计

### 3.1 数据模型

[note.py](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/backend/app/models/note.py) 新增字段：

| 字段 | 类型 | nullable | 说明 |
|------|------|----------|------|
| `matched_keywords` | `JSON` | 是 | 命中关键词列表（关键词维度使用） |
| `matched_blogger_id` | `Integer` | 是 | 命中博主 ID（博主维度使用） |
| `matched_blogger_username` | `String(64)` | 是 | 博主用户名快照（避免博主删除后失效） |
| `like_count` | `Integer` | 是 | 点赞数 |
| `collect_count` | `Integer` | 是 | 收藏数 |
| `comment_count` | `Integer` | 是 | 评论数 |

### 3.2 迁移

新建 `backend/migrations/versions/0022_note_match_and_engagement.py`：

- 全部加列 nullable=True
- 不做历史回填（成本太高；筛选 OR 匹配时自然忽略 null）
- 在迁移头部加注释说明回填策略

迁移后 **必须重启 celery worker**，否则 worker 持旧 ORM 模型访问新列会触发 `no such column` 等异常。

### 3.3 抓取阶段透传

[crawl_task.py](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/backend/app/tasks/crawl_task.py) 改动：

1. **关键词搜索结果 item** 已有 `tagged['_matched_keywords'] = [keyword]`（line 459/417） → 透传到 `Note.matched_keywords`
2. **博主搜索结果 item**（line 420-448）→ 给每个 item 加 tag：
   ```python
   tagged['_matched_blogger_id'] = blogger.id
   tagged['_matched_blogger_username'] = blogger.username
   ```
3. **下载与详情阶段 `download_and_ocr`**（line 484+）→ `Note(...)` 构造时填：
   - `matched_keywords = item.get('_matched_keywords', [])`
   - `matched_blogger_id = item.get('_matched_blogger_id')`
   - `matched_blogger_username = item.get('_matched_blogger_username')`
4. **详情抓取后从 `detail` 提取互动数**：
   - 字段名待 dump 确认（候选：`liked_count`/`like_count`、`collected_count`/`collect_count`、`comment_count`）
   - 实施前先跑一次 `crawler/detail --debug` 拿到 detail 结构，落库前写一段 `assert_fields_or_warn(detail, ...)` 的提示代码；若字段全缺则三个互动数列存 null 但不影响主流程
   - 写入 `Note.like_count/collect_count/comment_count`

### 3.4 后端 API

[notes.py](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/backend/app/api/v1/notes.py) `list_notes` 新增参数：

| 参数 | 类型 | 默认 |
|------|------|------|
| `keyword_group_ids` | `list[int]` | None |
| `blogger_group_ids` | `list[int]` | None |

**互斥规则**（后端校验）：
- `keyword` 与 `keyword_group_ids` 同传 → 422 `"参数冲突：keyword 与 keyword_group_ids 不能同时传"`
- `blogger_id` 与 `blogger_group_ids` 同传 → 422 `"参数冲突：blogger_id 与 blogger_group_ids 不能同时传"`

**匹配规则**：

keyword_group_ids 筛选：
```sql
SELECT note.id FROM note
WHERE note.id IN (
  SELECT n.id FROM notes n
  WHERE EXISTS (
    SELECT 1 FROM json_each(n.matched_keywords) je
    WHERE je.value IN (-- 所有选中组 enabled 的 words 并集 --)
  )
)
```

实现：用 Python 求"所有选中 enabled 关键词组的 words 并集" → 与 `Note.matched_keywords` JSON 数组求交集（用 SQLAlchemy `JSON_TABLE` / sqlite JSON1 函数，或 Python 端过滤，二者择一简单者）。

- 选 SQLite：使用 `EXISTS (SELECT 1 FROM json_each(Note.matched_keywords) WHERE json_each.value IN (:word_set))`
- 选 Python 端：分页前先用 SQL 过滤掉 `matched_keywords IS NULL`，在 Python 里二次过滤（性能差，弃）

> 决策：使用 SQLite JSON1 `json_each` 在 SQL 层一次性过滤。SQLAlchemy 实现：
> ```python
> from sqlalchemy import text
> stmt = stmt.where(
>     text("EXISTS (SELECT 1 FROM json_each(notes.matched_keywords) WHERE json_each.value IN :word_set)")
>     .bindparams(word_set=tuple(word_set))
> )
> ```
> 若匹配组下无 enabled words，则 word_set 为空 → 直接过滤掉所有 note（命中 0 行），符合"选中组没词则无结果"。

blogger_group_ids 筛选：
```sql
SELECT blogger_id FROM blogger_group_members
WHERE group_id IN (:group_ids) AND enabled = true
```
求并集 → `Note.matched_blogger_id IN (:blogger_id_set)`

多选 OR：每组分别求并集后再合并（实际就是单个 `IN` 列表）。

### 3.5 前端 UI

[ActivitiesView.vue](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/frontend/src/views/ActivitiesView.vue)：

**筛选器改造**：

把现有 4 个筛选字段（`city / review_status / keyword / blogger_id`）拆为：

| 列 | 控件 |
|---|---|
| 内容来源 | RadioButton `[自定义关键词, 关键词组]` |
| （互斥） | 自定义关键词：`ElInput` ；关键词组：`ElSelect multiple` |
| 博主来源 | RadioButton `[博主列表, 博主组]` |
| （互斥） | 博主列表：`ElSelect` ；博主组：`ElSelect multiple` |

切换 Radio 时清空对方字段值。`resetFilters` 同时清空 4 个字段（`keyword / keyword_group_ids / blogger_id / blogger_group_ids`）。

**列新增**：在表格列里追加：

| 标题 | 字段 | 宽度 |
|------|------|------|
| 点赞 | `like_count` | 90 |
| 收藏 | `collect_count` | 90 |
| 评论 | `comment_count` | 90 |

字段为 null 显示 `—`，否则 `toLocaleString()`。

### 3.6 API 客户端

[client.ts](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/frontend/src/api/client.ts) `notes()` 新增参数：

```ts
notes(params: {
  ...,
  keyword_group_ids?: number[]
  blogger_group_ids?: number[]
})
```

序列化：`keyword_group_ids` 用逗号分隔（`1,2,3`），FastAPI Query list[int] 支持。

### 3.7 端口管理

`uvicorn --reload` 自动重载 API 层。但涉及 ORM 字段新增 → **必须手动重启 celery worker**，否则 worker 持旧模型访问新 schema 触发 `no such column` 等错误。

## 4. 测试

### 4.1 后端

新增 `backend/tests/test_note_match_fields.py`：

1. `test_note_matched_keywords_persisted` — 入库时 `_matched_keywords` 写入 `Note.matched_keywords`
2. `test_note_matched_blogger_persisted` — 博主搜索结果入库带 blogger id/username
3. `test_note_engagement_fields_persisted` — 详情抓取后从 detail 提取 like/collect/comment
4. `test_list_notes_keyword_group_filter` — 单 keyword_group_id 命中交集
5. `test_list_notes_keyword_group_filter_multi_or` — 多选 OR
6. `test_list_notes_blogger_group_filter` — 按 blogger_group 命中成员博主
7. `test_list_notes_keyword_group_empty_words` — 选中组无 enabled words → 命中 0
8. `test_list_notes_keyword_and_group_mutex` — keyword + keyword_group_ids 同传 422
9. `test_list_notes_blogger_id_and_group_mutex` — blogger_id + blogger_group_ids 同传 422
10. `test_list_notes_engagement_in_summary` — 详情接口与列表接口均返回互动数列

### 4.2 前端

[ActivitiesView.spec.ts](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/frontend/src/views/ActivitiesView.spec.ts) 新增：

1. `switches between custom keyword and keyword group filter` — Radio 切换 + 控件显隐
2. `switches between blogger list and blogger group filter`
3. `applies keyword_group_ids when filter mode is groups`
4. `renders like/collect/comment columns with fallback for null`
5. `resets all four filter fields on reset click`

### 4.3 验证

- 后端 `pytest -q` 全绿
- 前端 `npm run test -- --run` 全绿
- 手工：起一次抓取（含关键词组 + 博主组），入库后列表用关键词组 / 博主组筛选能命中

## 5. 验收

- [ ] 0022 迁移文件可 `alembic upgrade head` 成功
- [ ] 重启 celery worker 后 worker 进程无 `no such column` 报错
- [ ] 推文入库后 `notes.matched_keywords` / `matched_blogger_*` / `like_count` / `collect_count` / `comment_count` 列有值
- [ ] `GET /api/v1/notes?keyword_group_ids=1&page=1` 按组命中推文
- [ ] `GET /api/v1/notes?blogger_group_ids=1&page=1` 按组命中推文
- [ ] `GET /api/v1/notes?keyword=咖啡&keyword_group_ids=1` 返回 422
- [ ] ActivitiesView UI Radio 切换生效，互斥；表格新增 3 列
- [ ] 历史数据（迁移前入库）`matched_*` 为 null，列表可正常显示，赞藏评列显示 `—`
- [ ] 现有"按关键词 / 按博主"筛选仍然工作（向后兼容）

## 6. 风险与备注

1. **赞藏评字段名未实测**：实施前必须跑一次 `crawler/detail` 拿到 detail JSON，确定 `like_count` 等字段真实命名。若字段缺失，三个互动数存 null，**不影响主流程**
2. **历史数据无回填**：迁移后 `matched_keywords` 等列对历史数据为 null，筛选时被自然忽略
3. **迁移后必重启 worker**：验收项显式列出
4. **不影响抓取性能**：JSON1 `json_each` 在 SQLite 单机场景下足够快；如未来迁 Postgres 可改 `jsonb ?` 操作符

## 7. 范围外（不做）

- 历史数据回填（matched_keywords / matched_blogger / 互动数）
- 详情页面赞藏评刷新的后台任务
- 抓取阶段 UI 改动
- 关键词 / 博主组"AND"语义（保留 OR；AND 是后续需求）