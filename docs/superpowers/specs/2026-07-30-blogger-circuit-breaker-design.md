# 博主/会话级错误纳入抓取熔断

## 背景

用户在抓取博主「宁波文旅」时遇到错误：

```
ok: false error: code: UNKNOWN message: 'Page not found: B058D28BE0FCCA3FAB8108F0EAA988DA — stale page identity' exitCode: 1
```

任务没有自动停止。当前 [app/tasks/crawl_task.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/app/tasks/crawl_task.py) 第 486-503 行博主循环只 `continue`，把 `discovery_failures += 1` 但**不参与**熔断：

```python
except Exception as exc:
    discovery_failures += 1
    task.error_message = f"博主 {username!r} 抓取失败：{exc}"
    db.commit()
    log(db, task.id, "ERROR", task.error_message)
    continue
```

而 `CrawlHalted` 熔断只算笔记处理失败的 `consecutive_failures`（默认 3）。后续博主成功又把计数清零 → 永远不会熔断。

## 目标

1. 博主循环与笔记循环**共用** `consecutive_failures` 计数器。
2. 博主抓取出现任意异常（非 `AuthenticationRequired`/`ExecutionStopped`/`ExecutionSuperseded`）都视为 1 次失败；连续失败达 `consecutive_note_failure_limit` 即熔断。
3. 熔断后任务 `status=PAUSED`，`error_message` 写明最后一次失败（提示「CDP session 可能过期，请重开浏览器后点击『检测登录并继续』」）。
4. 测试：`backend/tests/test_blogger_circuit_breaker.py` 加 3-4 个 case 覆盖：博主连续失败熔断、博主失败计数被后续成功清零、`AuthenticationRequired` 不计入失败。

## 设计

`crawl_task.py:486-503`：

```python
for blogger in scope.bloggers:
    username = (blogger.username or "").strip()
    if not username:
        log(db, task.id, "WARNING", f"跳过博主：username 为空 id={blogger.id}")
        continue
    try:
        items = adapter.blogger_notes(username, blogger.profile_url or "")
    except (AuthenticationRequired, ExecutionStopped, ExecutionSuperseded):
        raise
    except Exception as exc:
        discovery_failures += 1
        task.error_message = f"博主 {username!r} 抓取失败：{exc}"
        db.commit()
        log(db, task.id, "ERROR", task.error_message)
        consecutive_failures += 1          # 新增：计入熔断
        if consecutive_failures >= settings.consecutive_note_failure_limit:
            raise CrawlHalted(
                f"已连续 {consecutive_failures} 次抓取失败（最近一次：博主 {username!r}）。"
                f"CDP session / 浏览器标签页可能已过期，请在 Chrome 重新打开小红书后"
                f"点击「检测登录并继续」，或「结束抓取」。最后一次错误：{exc}"
            )
        continue
    consecutive_failures = 0                # 新增：博主成功也清零
    assert_execution_active(db, task.id, run_token)
    log(db, task.id, "INFO", f"博主 {username!r} 命中 {len(items)} 篇（带 xsec_token 的）")
    results.extend((city.code, item) for item in items)
```

## 验收

- `tests/test_blogger_circuit_breaker.py` 4 个 case 全过：博主连续 N 次失败熔断、单次失败+后续成功不熔断、`AuthenticationRequired` 不计入失败、连续失败 `error_message` 含用户名与最后一次错误。
- 全量 `uv run --project backend pytest backend/tests -q` 全过。
- 实操：在仪表盘触发抓取博主「宁波文旅」（profile_url 不可访问或 stale），观察到任务 ~3 个博主后自动 PAUSED，error_message 提示「CDP session 可能过期」。
- worker/beat 必须重启才能加载新代码（按 AGENTS.md）。

## 关联

- 已有熔断器：[backend/app/services/crawler.py CrawlHalted](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/app/services/crawler.py)
- 已有连续失败 spec：[docs/superpowers/specs/2026-07-28-log-timezone-and-consecutive-failure-halt-design.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/docs/superpowers/specs/2026-07-28-log-timezone-and-consecutive-failure-halt-design.md)
- 服务进程：[backend/app/tasks/crawl_task.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/app/tasks/crawl_task.py)