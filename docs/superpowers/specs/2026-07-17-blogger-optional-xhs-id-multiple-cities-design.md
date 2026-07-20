# 博主白名单放宽与多城市关联设计

## 1. 背景与已确认规则

当前博主管理存在两个体验问题：

1. 新增/编辑博主时 `platform_user_id`（小红书 ID）是必填项，无法保存只有 `username` 和 `profile_url` 的博主。
2. `Blogger.city_code` 是单字段 `String(32)`，一个博主只能绑定一个城市，无法复用同一博主到多个城市。

本次已确认的产品规则：

- `platform_user_id` 改为可选；为空时由 `username` 或 `profile_url` 反查出的平台 ID 兜底，但仍允许留空保存。
- 同一博主可绑定到多个城市；通过新增的多对多关联表 `blogger_cities` 实现。
- `Blogger.city_code` 字段在迁移完成后废弃（保留列以兼容旧代码读路径，写路径不再使用）。
- 阶段一仍保持本地运行，不引入 Redis、MinIO 或 Docker。

## 2. 方案选择

采用"博主实体 + 多对多关联表"方案：

- 博主实体只保留通用字段：`id`、`platform_user_id`（可选）、`username`、`profile_url`、`enabled`、`created_at`。
- 新增 `BloggerCity(blogger_id, city_code, enabled, created_at)` 表，记录博主与城市的多对多关系。
- 抓取任务按 `blogger_cities` 过滤博主，而不是按 `Blogger.city_code`。

不采用"博主 `city_codes` 存逗号分隔字符串"的方案，因为后续多对多查询、按城市聚合、统计都更难实现；也不采用"为每个城市复制一份博主记录"的方案，会导致数据冗余和编辑不同步。

## 3. 数据模型设计

### 3.1 新表 `blogger_cities`

```sql
CREATE TABLE blogger_cities (
    id INTEGER PRIMARY KEY,
    blogger_id INTEGER NOT NULL REFERENCES bloggers(id) ON DELETE CASCADE,
    city_code VARCHAR(32) NOT NULL REFERENCES cities(code) ON DELETE CASCADE,
    enabled BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    UNIQUE(blogger_id, city_code)
);
CREATE INDEX idx_blogger_cities_city ON blogger_cities(city_code);
```

### 3.2 `Blogger` 模型调整

```python
class Blogger(Base):
    __tablename__ = "bloggers"
    id: Mapped[int] = mapped_column(primary_key=True)
    platform_user_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True, default=None)
    username: Mapped[str] = mapped_column(String(128))
    profile_url: Mapped[str] = mapped_column(String(512))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    city_code: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)  # 兼容旧读路径
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
```

`platform_user_id` 改为可空；唯一索引保留但允许多个 NULL。

### 3.3 迁移脚本

`backend/scripts/migrations/split_blogger_cities.py`：

- 读取每条 `Blogger.city_code`，迁移到 `blogger_cities(blogger_id, city_code, enabled=blogger.enabled)`。
- `Blogger.city_code` 为空 → 不创建 `blogger_cities` 记录（视为全城市未启用）。
- 重复执行幂等：通过 `UNIQUE(blogger_id, city_code)` 保证。
- 输出：`已迁移 N 条博主关联`。

### 3.4 Alembic 迁移

新增 `alembic/versions/2026_07_17_split_blogger_cities.py`：

- `op.create_table('blogger_cities', ...)`
- `op.alter_column('bloggers', 'platform_user_id', existing_type=..., nullable=True)`
- 数据迁移调用上述脚本。

## 4. API 设计

### 4.1 博主管理 API

`POST /api/v1/settings/bloggers` 入参 `BloggerIn`：

```python
class BloggerIn(BaseModel):
    platform_user_id: str | None = None   # 可选
    username: str
    profile_url: str | None = None         # 允许暂留空，后续补
    city_codes: list[str] = []             # 多城市
    enabled: bool = True
```

行为：

- `platform_user_id` 为空时允许保存。
- `city_codes` 可为空列表：博主存在但未绑定任何城市，抓取任务不会使用。
- 至少需要 `username`，否则 422。

`PUT /api/v1/settings/bloggers/{id}` 行为：全量替换 `city_codes`，未传则清空。

`GET /api/v1/settings/bloggers` 返回结构增加 `city_codes: list[str]` 字段，供前端渲染多选。

### 4.2 抓取任务 API

`POST /api/v1/tasks/crawl` 入参 `CrawlIn.blogger_ids: list[int]` 保持现状，校验逻辑改为基于 `blogger_cities`：

- 校验每个 `blogger_id` 在 `blogger_cities` 中至少有一条 `city_code == payload.city` 且 `enabled=true` 的记录。
- 抓取时取 `Blogger.enabled=true` 且 `blogger_cities.enabled=true` 且 `blogger_cities.city_code == city.code` 的博主。

## 5. 抓取逻辑

`backend/app/tasks/crawl_task.py:run_crawl` 替换 `Blogger` 查询：

```python
stmt = (
    select(Blogger)
    .join(BloggerCity, BloggerCity.blogger_id == Blogger.id)
    .where(
        Blogger.enabled.is_(True),
        BloggerCity.enabled.is_(True),
        BloggerCity.city_code == city.code,
    )
)
```

### 5.1 默认抓取范围联动

与 spec 1 联动：未传 `blogger_ids` 时，按上述 SQL 自动取该城市下 `blogger_cities` 启用的博主。

## 6. 测试设计

### 6.1 后端单元与集成

- BloggerIn 缺 `platform_user_id` 仍可保存。
- BloggerIn 缺 `username` 返回 422。
- `blogger_cities` 写入：同一博主绑定两个城市成功；重复绑定返回唯一约束错误。
- 抓取任务按 `blogger_cities` 过滤，未绑定城市的博主不被抓取。
- 同一博主绑定到城市 A 与 B：在两个城市的抓取任务中都能命中。
- `Blogger.city_code` 留空时，`blogger_cities` 无对应记录，不被抓取。
- 迁移脚本幂等：第二次执行不创建重复记录。

### 6.2 前端组件与浏览器功能测试

- 博主管理新增表单 `platform_user_id` 字段非必填。
- 博主管理新增表单支持城市多选。
- 博主列表行展示所绑定的城市标签。

### 6.3 真实本地验证

- 新增博主只填 `username` 能保存。
- 同一博主在两个城市下启用，跑两次抓取都能抓到该博主的笔记。

## 7. 文档同步范围

- `docs/database-design.md`：更新 `Blogger` 模型，新增 `blogger_cities` 表。
- `docs/api-doc.md`：`BloggerIn` 入参改为可选字段、`city_codes` 多城市。
- `docs/business-flow.md`：抓取流程按 `blogger_cities` 过滤。
- `tests/test-config-center-api.md`：覆盖新增/更新/列表用例。
- `tests/test-crawler-engine.md`：覆盖抓取范围按 `blogger_cities` 过滤。
- `tests/test-database-migration.md`：覆盖迁移幂等性。

## 8. 非目标

- 不实现博主批量导入/导出。
- 不引入博主标签、分类、备注等扩展属性。
- 不修改 `platform_user_id` 的唯一性约束语义（多个 NULL 仍允许）。
- 不引入第二阶段的 Redis、MinIO、Docker。