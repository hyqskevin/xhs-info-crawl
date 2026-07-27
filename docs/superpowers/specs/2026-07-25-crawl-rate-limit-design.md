# 抓取频率控制落地 — 设计

日期：2026-07-25
关联 TODO：当前待办第 4 条（SPEC P1：`search_interval_min/max` 与 `weekly_search_limit` 配置存在但零引用）

## 1. 需求

- 关键词搜索之间按 `search_interval_min`~`search_interval_max`（默认 10-15s）的随机间隔 sleep，降低小红书风控概率；
- 周搜索量上限 `weekly_search_limit`（默认 500/周）：超限后记录 WARNING 并跳过剩余关键词搜索；
- sleep 必须可注入（测试用 fake，不拖慢测试），且停止任务时能及时响应（不阻塞 stop）。

## 2. 设计

### 2.1 间隔控制：`app/services/search_rate_limit.py`

```python
class SearchRateLimiter:
    def __init__(self, interval_min, interval_max, uniform=random.uniform): ...
    def next_delay(self) -> float | None:
        """任务内第一次搜索返回 None（不等待），之后返回 uniform(min, max)。"""
```

- 每个 CrawlTask 构造一个 limiter（任务内"搜索之间"计数）；
- `uniform` 可注入，测试固定返回值做到确定性。

### 2.2 可中断 sleep：`crawl_task.rate_limit_sleep`

```python
def rate_limit_sleep(seconds: float, guard: Callable[[], None] | None = None) -> None:
    """按 0.5s 分片 sleep，每片执行 guard（assert_execution_active），stop 请求 0.5s 内响应。"""
```

- `run_crawl` 以模块级函数引用 `rate_limit_sleep`，测试可 monkeypatch；
- **conftest 新增 autouse fixture**：默认把 `crawl_task.rate_limit_sleep` 替换为 no-op（与现有 `forbid_undeclared_celery_dispatch` 同风格），需要断言 sleep 行为的测试显式重 patch。避免既有 run_crawl 测试被 10-15s 真实 sleep 拖慢。

### 2.3 周配额：新表 `search_usage`（migration `0016_search_usage`）

```text
search_usage  id, week_key VARCHAR(8) UNIQUE（"2026-W30"，ISO 周，Asia/Shanghai）,
              count INT DEFAULT 0, updated_at
```

- `iso_week_key(now=None)`：Asia/Shanghai 时区的 ISO 年-周；
- `weekly_search_count(db, week_key)` / `increment_weekly_search(db, week_key)`；
- 配额是全局跨任务的（周累计），间隔是任务内的——两者正交；
- 计数时机：每次 `adapter.search_recent` **调用成功后** +1（调用即消耗配额，与结果数无关）。

### 2.4 run_crawl 关键词循环改造（两个分支同规则）

```python
limiter = SearchRateLimiter(settings.search_interval_min, settings.search_interval_max)
week_key = iso_week_key()
for keyword in scope.keywords:
    if weekly_search_count(db, week_key) >= settings.weekly_search_limit:
        log WARNING f"本周搜索量已达上限（{limit}），跳过关键词 {keyword!r} 及后续搜索"
        break
    delay = limiter.next_delay()
    if delay:
        rate_limit_sleep(delay, guard=lambda: assert_execution_active(db, task.id, run_token))
    for item in adapter.search_recent(f"{city.name} {keyword}", recent_filter): ...
    increment_weekly_search(db, week_key)
```

- 超限只跳过关键词搜索，**博主抓取不受影响**（配额语义是"搜索"维度）；
- 超限导致 0 结果时任务正常 COMPLETED，不算失败；
- 无城市回退分支（`requested_cities` 无匹配 City 行）同样接入 limiter + 配额。

## 3. TDD 计划（先红）

- `tests/test_search_rate_limit.py`：
  1. 首次 `next_delay()` 返回 None，之后返回注入 uniform 的固定值；
  2. `iso_week_key` 固定时间断言（2026-01-01 → "2026-W01"，周四属当年第 1 周）；
  3. `increment_weekly_search` / `weekly_search_count` 读写与跨周隔离；
- `tests/test_crawl_rate_limit.py`（仿 test_crawl_task_resilience 搭建）：
  4. 3 个关键词 → `rate_limit_sleep` 调用 2 次（首次不等），`search_recent` 3 次，配额 +3；
  5. 配额已达上限 → `search_recent` 零调用、WARNING 日志、任务 COMPLETED；
  6. 配额跨任务累计（第一次任务 +2，第二次任务从 2 继续）。

## 4. 验收

- 上述测试先红后绿；后端全量测试绿（既有测试不因真实 sleep 变慢，由 conftest autouse 保证）；
- migration `0016` 临时库 upgrade/downgrade 通过；生产库 upgrade/stamp；
- `docs/crawler-design.md` 同步频率与配额语义；
- **改动 `app/tasks/*.py`、`app/services/*.py` 与 models：必须重启 celery worker 与 beat**。

## 5. 非目标

- 不限制博主抓取的频率与配额（`blogger_notes` 走 search 命令但语义上属"博主"维度，后续需要再议）；
- 不做跨 worker 并发锁（当前 solo 单 worker，单写者安全）；
- 不做前端配额展示（analytics 后续可加）。
