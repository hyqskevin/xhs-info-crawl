# 活动列表城市筛选数据一致性设计

## 1. 背景与已确认规则

活动管理列表（`GET /api/v1/activities`）支持按 `city` 查询。当选择"上海"时，列表返回 0 条；用户期望能看到已入库的上海活动。

排查结果：

- 城市表中上海的 code 为 `'city-99f1e469'`（由 `generate_city_code` 按 `sha1(name).hexdigest()[:8]` 生成）。
- 数据库中部分活动记录的 `city_code` 字段值为字面字符串 `'上海'`（中文），与城市表 code 不匹配。
- 前端按城市 code（`'city-99f1e469'`）传参，API `city='city-99f1e469'` 过滤后命中 0 条。

本次已确认的产品规则：

- `activities.city_code` 必须始终存储城市表的 `City.code`，不再允许出现中文字面量或其他非 code 值。
- API 继续按 `City.code` 过滤，前端不做"按 name 模糊匹配"的特殊处理。
- 一次性数据迁移：把历史脏数据的 `city_code` 改为对应 `City.code`，无匹配城市的脏数据归档到 `NA` 城市并标记来源。
- 阶段一仍保持本地运行，不引入 Redis、MinIO 或 Docker。

## 2. 方案选择

采用"数据迁移 + 入库硬校验"双层方案：

- 迁移层：一次性脚本把脏数据的 `city_code` 改成匹配城市的 code。
- 校验层：抓取入库时显式校验 city_code 必须存在于 `cities` 表，否则任务日志记 ERROR 且不入库。

不采用"前端按 name 模糊匹配"的方案，因为长期会让 code/name 双轨制带来更多 bug；也不采用"保留脏数据不动"的方案，因为筛选问题会持续存在。

## 3. 数据迁移设计

### 3.1 匹配规则

对 `activities.city_code` 取值遍历：

- 已经是 `cities.code` → 保留。
- 等于某 `cities.name` → 改为该城市的 `cities.code`。

不引入"NA 归档城市"——当前脏数据只有"中文字面量"这一类，且都能匹配到 cities.name，没有需要"无匹配归档"的场景。如果未来真的出现无法匹配的脏数据，由"入库硬校验"在抓取阶段拦截，不在迁移脚本里归档。

### 3.2 迁移脚本

新增 `backend/scripts/migrations/fix_activity_city_code.py`：

- 入口：`python -m scripts.migrations.fix_activity_city_code`。
- 读取环境 `DATABASE_URL`，默认 `./data/app.db`。
- 输出：`扫描 N / 已修正 M`。
- 重复执行幂等。
- 不删除原始数据；只更新 `activities.city_code` 字段。

### 3.3 入库硬校验

`backend/app/tasks/crawl_task.py:run_crawl` 在写入 `Note` / `Activity` 前查询 `cities.code`，未命中时：

- 任务日志记 ERROR `city_code not found: <value>`。
- 该条活动跳过（计入 `skipped_activities`）。
- 不抛出任务级异常。

## 4. 数据流与错误隔离

```text
抓取搜索结果
  -> 提取活动
  -> 校验 city_code 在 cities 表存在
     -> 存在：正常入库
     -> 不存在：ERROR 日志 + 跳过该活动
  -> 列表查询按 City.code 过滤
```

## 5. 接口契约

`GET /api/v1/activities?city=<City.code>` 行为保持：

- `city=city-99f1e469` → 返回上海的活动。
- 不传 city → 返回全量。
- 不存在 `city=NA` 这种归档值（无 NA 归档城市）。

## 6. 测试设计

### 6.1 后端单元与集成

- 迁移脚本：含 `'上海'` 的脏数据被改为 `'city-99f1e469'`。
- 迁移脚本：重复执行无副作用。
- 入库硬校验：`city_code='上海'` 在新任务中不入库，记 ERROR。
- API：`GET /activities?city=city-99f1e469` 返回 code 一致的活动。

### 6.2 前端组件与浏览器功能测试

- 活动列表选择"上海"返回非空结果。
- 活动列表选择"归档"看到 code='NA' 的活动。

### 6.3 真实本地验证

- 执行迁移脚本后，活动管理列表选择"上海"能展示历史入库的上海活动。
- 重新跑一次抓取，新活动的 `city_code` 与城市表一致。

## 7. 文档同步范围

- `docs/database-design.md`：明确 `activities.city_code` 必须引用 `cities.code`，新增 `NA` 归档城市说明。
- `docs/api-doc.md`：补充归档城市查询。
- `docs/business-flow.md`：抓取流程增加"city_code 校验"节点。
- `tests/test-frontend-ui-e2e.md`：覆盖上海列表展示。
- `tests/test-database-migration.md`：新增迁移脚本用例。

## 8. 非目标

- 不删除历史脏数据；只迁移 `city_code` 字段。
- 不修改 `City.code` 的生成规则。
- 不引入城市的启用/禁用过滤变更；该话题另起 spec。
- 不引入第二阶段的 Redis、MinIO、Docker。
