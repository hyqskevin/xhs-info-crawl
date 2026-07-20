# 抓取范围由配置驱动设计

## 1. 背景与已确认规则

当前抓取任务 `run_crawl` 始终按关键词搜索；只有当任务参数 `task.params["blogger_ids"]` 显式非空时才会抓博主。这导致用户在前端"博主管理"启用博主后，仍然只看到按关键词搜索的结果——用户已经配置了博主但仍按关键字抓，与预期"按我配置的来"不符。

本次已确认的产品规则：

- 用户在配置中心启用哪些关键词，抓取任务就按这些关键词搜索；不再用城市表的全部 enabled 关键词做隐式回退。
- 用户在博主管理启用哪些博主，抓取任务就按这些博主的 `profile_url` 定点抓取其笔记；不再要求任务参数显式传 `blogger_ids`。
- 关键词抓取和博主抓取是**互补**关系（不是互斥），同时启用则合并去重后入库。
- 任务参数 `keywords` / `blogger_ids` 仍保留，作为"覆盖"语义：显式传则只抓这些，不传则按全局 enabled 配置全量抓。
- 阶段一仍保持本地运行，不引入 Redis、MinIO 或 Docker。

## 2. 方案选择

采用"任务级显式覆盖 + 配置默认"方案：

- 默认行为（任务参数为空）：抓取范围 = 城市内 enabled 的关键词 ∪ 城市内 enabled 的博主。
- 覆盖行为（任务参数非空）：抓取范围 = 任务参数指定的关键词 ∪ 任务参数指定的博主。
- 入口校验（`POST /api/v1/tasks/crawl`）：最终生效的关键词列表和博主列表不能同时为空，否则返回 422。

不采用"只按关键词抓、博主完全失效"的方案，因为用户明确要求博主生效；也不采用"完全按任务参数抓、忽略配置中心"的方案，因为任务参数应当是覆盖项而非主项。

## 3. 抓取范围设计

### 3.1 关键词抓取

- 任务参数 `task.params["keywords"]` 非空 → 仅用任务参数。
- 任务参数 `task.params["keywords"]` 为空 → 用城市下 `Keyword.enabled=true` 的全部关键词。
- 任务参数显式传 `[]`（空列表）→ 视作用户主动禁用关键词，仅抓博主。

### 3.2 博主抓取

- 任务参数 `task.params["blogger_ids"]` 非空 → 按 ID 过滤并校验 `city_code == city.code` 且 `enabled=true`。
- 任务参数 `task.params["blogger_ids"]` 为空 → 自动获取当前城市 `Blogger.enabled=true` 的全部博主。
- 任务参数显式传 `[]`（空列表）→ 视作用户主动禁用博主，仅抓关键词。
- 博主 `profile_url` 为空 → 跳过该博主，记录 WARNING，不影响其他博主。

### 3.3 入口校验

`POST /api/v1/tasks/crawl` 在创建任务前计算最终生效的关键词数量和博主数量，二者都为 0 时返回 422：

```text
"请至少启用一个关键词或博主"
```

校验发生在 `app/api/v1/tasks.py:crawl` 创建 `CrawlTask` 之前。已存在的任务（`POST /tasks/{id}/restart`）不重新校验，保留原参数。

### 3.4 任务日志

任务进入 `SEARCHING` 阶段后，记录一条 INFO 日志：

```text
抓取范围生效：keywords=N1 blogger_ids=N2 (override=任务参数|配置默认)
```

N1 = 最终生效的关键词数量，N2 = 最终生效的博主数量。`override` 用于表明本次行为来自任务参数还是配置默认，便于排障。

## 4. 数据流与错误隔离

```text
读取任务参数
  -> 计算 effective_keywords（任务参数优先，否则取城市 enabled 关键词）
  -> 计算 effective_bloggers（任务参数 ID 优先，否则取城市 enabled 博主）
  -> 记录抓取范围日志
  -> 按关键词搜索近一周笔记
  -> 按博主 profile_url 抓博主笔记
  -> 合并去重后入库
```

- 单个博主 `profile_url` 为空 → 跳过该博主，记 WARNING。
- 单个关键词搜索失败 → 沿用现有 `process_note` 隔离机制，不影响其他关键词。
- 博主表无任何 enabled 记录 → 不再回退到"全部关键词搜索"；若关键词也为空则任务在入口处即被拒绝。

## 5. 接口契约

`POST /api/v1/tasks/crawl` 入参 `CrawlIn` 保持现状：

```python
class CrawlIn(BaseModel):
    type: str = 'mixed'
    city: str
    keywords: list[str] = []            # 空列表表示禁用关键词
    recent_filter: Literal[...] = '一周内'
    blogger_ids: list[int] = []         # 空列表表示禁用博主
```

行为：

- `keywords=[]`、`blogger_ids=[]` → 422。
- `keywords=[A]`、`blogger_ids=[]` → 入口处计算 effective_keywords=[A]、effective_bloggers=[] → 422。
- `keywords=[A]`、`blogger_ids=[B]` → 通过，最终生效 A 和 B。
- `keywords=[]`、`blogger_ids=[B]` → 通过，最终生效 B。
- `keywords=未传（默认 []）`、`blogger_ids=未传` → 取城市 enabled 全量。

## 6. 测试设计

### 6.1 后端单元与集成

- 关键词默认生效：城市 enabled 关键词为 [A, B]、任务参数无 keywords → effective_keywords=[A, B]。
- 关键词覆盖：城市 enabled 为 [A, B]、任务参数 keywords=[A] → effective_keywords=[A]。
- 关键词禁用：任务参数 keywords=[] → effective_keywords=[]。
- 博主默认生效：城市 enabled 博主为 [B1, B2]、任务参数无 blogger_ids → effective_bloggers=[B1, B2]。
- 博主覆盖：任务参数 blogger_ids=[B1] → effective_bloggers=[B1]。
- 博主禁用：任务参数 blogger_ids=[] → effective_bloggers=[]。
- 博主 profile_url 为空 → 跳过 + WARNING 日志。
- 入口校验：keywords=[] 且 blogger_ids=[] → 422。
- 入口校验：keywords=[A] 且 blogger_ids=[] → 422。
- 任务日志包含 "抓取范围生效"。

### 6.2 前端组件与浏览器功能测试

- 仪表盘"开始抓取"按钮在博主管理和关键词配置都为空时显示禁用态或 Toast 提示。
- 任务详情页能看到抓取范围日志。

### 6.3 真实本地验证

- 在博主管理启用一个博主、关键词配置为空 → 任务只抓该博主笔记。
- 在关键词配置启用一个关键词、博主管理为空 → 任务只按该关键词搜索。
- 同时启用 → 任务既按关键词搜索又抓博主笔记，合并去重。

## 7. 文档同步范围

实施时同步更新：

- `docs/business-flow.md`：在抓取流程图里增加"抓取范围计算"节点。
- `docs/crawler-design.md`：明确 effective_keywords / effective_bloggers 计算逻辑。
- `docs/api-doc.md`：补充 `CrawlIn` 空数组的语义说明。
- `docs/ui-design.md`：仪表盘禁用态或 Toast 提示。
- `tests/test-crawler-engine.md`：覆盖 effective 计算与日志断言。
- `tests/test-task-scheduling.md`：覆盖入口校验。

## 8. 非目标

- 不修改城市表结构，不引入博主多对多关联。
- 不改变博主抓取的实现细节（仍走 `OpenCLIAdapter.blogger_notes`）。
- 不引入任务参数以外的覆盖维度（如时间窗口、笔记数量上限）。
- 不引入第二阶段的 Redis、MinIO、Docker 或分布式任务基础设施。