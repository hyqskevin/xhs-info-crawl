# 城市复用 + 关键词组一对多设计

> 状态：审核中。

## 1. 目标

### 1.1 城市去重 + 复用

现状：`City.name` 是 `String`，**没有 unique 约束**；DB 中可能有重复（截图：宁波 出现两次）。
要求：
- `City.name` 在 DB 层加 `unique` 约束；
- `City.code` 已经是 `String` 字段，保留——**代码是稳定标识（导入/导出/链接用），name 是用户语义名**；
- DB 已有的重复"宁波"由一次性脚本 `scripts/dedupe_cities.py` 合并：选最新启用项为 canonical，把其它 `City.id` 关联的数据迁移过去（`notes.city_code` / `blogger_city.city_code` / `crawl_tasks.params`），最后删多余。

### 1.2 关键词组（多对一）

现状：`Keyword` 是 `{city_code, word}` 单字段。
要求升级为：
- **关键词组（KeywordGroup）** 实体：`id, name (unique), description, created_at`；
- **关键词组挂到城市** 用中间表 `keyword_group_cities`：`(keyword_group_id, city_code)`；
- **关键词组的关键词** 用中间表 `keyword_group_words`：`(keyword_group_id, word)`；
- 一个关键词组可挂多个城市（一对多关系从"城市 → 关键词组"反向）；
- 一个城市下可以有多个关键词组（一对多关系正常成立）。

仪表盘：

```
[城市]         → 宁波 / 上海
[关键词组]    → [宁波-展览, 宁波-亲子, 宁波-咖啡]    ← 多选
[博主]          → 该城市下的博主（不变）
```

## 2. 设计

### 2.1 数据模型

```
cities                keyword_groups
  id (PK)               id (PK)
  name (UNIQUE, idx)    name (UNIQUE)
  code (UNIQUE)         description
  enabled               created_at
                        ↓
                  keyword_group_cities
                    keyword_group_id (FK)
                    city_code (FK -> cities.code)
                  keyword_group_words
                    keyword_group_id (FK)
                    word
```

### 2.2 仪表盘 `crawl_scope` 重写

`crawl_scope.resolve_crawl_scope(db, city, payload)`：
- `payload.keyword_group_ids: list[int]` 取代 `payload.keywords: list[str]`；
- 解析 = 找出"city + 这些 keyword_group_ids 的并集 word"；
- 旧字段 `keywords` 保留（兼容性，弃用）+ 文档提示迁移。

### 2.3 API 改造

| 路径 | 方法 | 说明 |
|---|---|---|
| `/api/v1/settings/keyword-groups` | GET | 按城市筛选返回 keyword_groups |
| `/api/v1/settings/keyword-groups` | POST | 新建 |
| `/api/v1/settings/keyword-groups/{id}` | PUT/DELETE | 改/删 |
| `/api/v1/settings/keyword-groups/{id}/words` | PUT | 替换 word 列表 |
| `/api/v1/settings/keyword-groups/{id}/cities` | PUT | 替换挂载的城市列表 |
| `/api/v1/tasks/crawl` | POST | 接 `{city, keyword_group_ids, blogger_ids, recent_filter}` |

### 2.4 DB migration `0013_keyword_groups.py`

1. 新增 `keyword_groups / keyword_group_cities / keyword_group_words` 三表；
2. 数据迁移：从现有 `keywords (city_code, word)` 自动生成 `keyword_group`（按"城市名-关键词集"命名规则，例如：`宁波-默认`，组内含宁波下所有启用关键词），让旧调用方有默认组可用；
3. `cities.name` 加 `unique=True`（已有重复先跑 `dedupe_cities.py` 处理）。

## 3. 前端

- `DashboardView.vue` 工具栏：`<ElSelect v-model="form.keyword_group_ids" multiple>` 取代 `<ElSelect v-model="form.keywords">`；
- `SettingsView.vue` 增加 tab「关键词组」与子页：表格 list 组、新增/编辑、组详情面板里挂「关键词」与「挂载城市」。

## 4. 测试

| 文件 | 案例 |
|---|---|
| `tests/test_keyword_group_api.py` | 5 案例：列表 / 新建 / 改 words / 改 cities / 删除 |
| `tests/test_crawl_scope_with_groups.py` | 3 案例：单组命中 / 多组并集 / 跨城市组 |
| `tests/test_dedupe_cities_script.py` | 3 案例：合并重复 city / 迁移 notes / 幂等 |
| `frontend/src/views/SettingsView.spec.ts` | 关键词组 tab 切换 case |
| `frontend/src/views/DashboardView.spec.ts` | keyword_group_ids 透传 |

## 5. 验收

- 后端 308+ 测试；
- 前端 49+ 测试；
- build 通过；
- 实操：
  1. 跑 `python -m scripts.dedupe_cities --execute` → 重名 city 合并；
  2. 跑 `alembic upgrade head` → keyword_groups 表建好并迁移旧 keywords；
  3. 配置中心 → "关键词组" → 把"展览"组同时挂到宁波 + 上海；
  4. 仪表盘 → 城市选宁波 → 关键词组看到"展览 / 亲子 / 咖啡"；同时上海选的"展览"组也会复用到上海城市选项下。
