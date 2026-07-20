# 博主发现阶段失败隔离设计

> 状态：已通过持续授权审核，待实现。

## 1. 目标

单个博主主页解析失败时，只跳过该博主并记录错误，继续抓取其他博主已经发现的签名笔记；不得让一个博主的页面结构异常导致整批任务在下载前直接失败。

登录失效、用户停止任务或执行令牌失效仍然立即中止整批，不纳入普通失败隔离。

## 2. 真实证据与根因

2026-07-20 重新执行任务 `#7` 时，任务范围为 `keywords=0 bloggers=5`，没有回退到关键词搜索。前三个博主均成功记录“命中 15 篇（带 xsec_token 的）”，证明签名 URL 获取已经生效。

第 4 个博主的 OpenCLI `user` 结果报 `Malformed Xiaohongshu user snapshot: user store was not found`。当前 `run_crawl` 在博主循环内直接调用 `adapter.blogger_notes()`，没有普通异常隔离，因此异常越过整个发现阶段，任务直接进入 `FAILED`，前三个博主已收集的结果也没有进入下载，`downloaded_notes` 保持为 0。

## 3. 方案比较

### 3.1 采用：按博主隔离普通发现错误

每个博主单独执行 `blogger_notes()`。普通解析、页面结构或单账号数据错误记录为 ERROR，保存最后一次发现错误并继续下一个博主。已成功发现的结果照常去重和进入笔记处理。

优点是符合现有“单篇笔记失败不影响整批”的鲁棒性原则，也能最大化利用已经取得的签名 URL。

### 3.2 不采用：整批重试全部博主

整批重试会重复访问已经成功的账号，增加耗时和反爬风险，而且某个账号持续结构异常时仍会拖垮整批。

### 3.3 不采用：保持 fail-fast

当前行为会丢弃已收集结果，与 TODO 的真实验收目标冲突。

## 4. 详细设计

### 4.1 异常边界

博主循环按以下规则处理：

1. `username` 为空：保持现有 WARNING 并跳过；
2. `blogger_notes()` 成功：记录命中数量并追加结果；
3. `AuthenticationRequired`：原样抛出，由任务外层进入 `PAUSED`；
4. `ExecutionStopped`、`ExecutionSuperseded`：原样抛出，保持停止与执行权语义；
5. 其他异常：记录 `博主 <username> 抓取失败` ERROR，保存最后一次发现错误并继续下一个博主。

日志不得包含 Cookie、完整 `xsec_token` 或其他登录凭据。

### 4.2 最终状态

新增任务内局部计数 `discovery_failures`，不复用 `failed_notes`，避免把账号发现错误误报为笔记失败数。

- 没有发现错误且笔记处理无失败：`COMPLETED`；
- 存在博主发现错误或笔记处理失败，但流程正常跑完：`COMPLETED_WITH_ERRORS`；
- 最后一次博主发现错误写入 `error_message`，便于仪表盘和任务日志追踪；
- 登录失效仍为 `PAUSED`，执行停止仍为 `STOPPED`，不被错误隔离覆盖。

### 4.3 已收集结果

一个博主失败不得清空此前 `results`。循环结束后仍执行现有 URL 去重、标题筛选、下载、OCR、提取和归档流程。若成功博主返回了可处理笔记，`downloaded_notes` 应能增长。

## 5. TDD

先补失败测试：

1. 第一个博主抛普通异常、第二个博主返回签名笔记时，第二个博主仍被调用且笔记进入处理；
2. 最终状态为 `COMPLETED_WITH_ERRORS`，错误日志包含失败博主，不泄露签名参数；
3. 博主返回 `AuthenticationRequired` 时仍进入 `PAUSED`，不会继续其他博主；
4. 现有关键词抓取、停止执行权和单笔记隔离测试保持通过。

测试放在 `backend/tests/test_crawl_task_resilience.py`，验收记录放在 `tests/test-blogger-discovery-resilience.md`。

## 6. 验收标准

- 任务 `#7` 日志确认 `keywords=0 bloggers=5`；
- 日志包含 `博主 '从零发现宁波' 命中 N 篇（带 xsec_token 的）`，且 `N > 0`；
- 单个博主 `user store was not found` 不再让整批直接 `FAILED`；
- 至少一篇已发现笔记进入下载，`downloaded_notes > 0`；
- 本次运行日志没有 `Missing url` 或“requires a full signed URL”；
- 后端全量测试通过；完成后更新 `docs/TODO.md` 并提交。

## 7. 不在本次范围

- 不修改 OpenCLI 对小红书页面快照的解析实现；
- 不为博主发现增加整批自动重试；
- 不改变 OCR、活动提取、去重或周报逻辑；
- 不把登录、验证码或停止异常降级为可忽略错误。
