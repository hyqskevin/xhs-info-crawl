# 日志时间东八区显示 + 笔记连续失败熔断设计

> 状态：已审核（持续授权）。来源：2026-07-28 用户反馈（截图：任务 #19 日志时间为 UTC、笔记连续失败无用户决策入口）。

## 1. 问题与根因

### 1.1 日志时间不是东八区

- 现象：仪表盘「最近任务日志」显示 `2026-07-28 00:46:14`，用户本地（东八区）实际为 `08:46:14`。
- 根因：按 `docs/database-design.md` 时间口径，`TaskLog.created_at` / `CrawlTask.created_at/started_at` 均为 **UTC naive**（SQLite 丢 tzinfo）。前端三处直接渲染原始字符串：
  - `DashboardView.vue` 最近任务日志：`(log.created_at || '').replace('T',' ').slice(0,19)`；
  - `TasksView.vue` 任务列表「创建时间」列：`prop="created_at"`；
  - `TasksView.vue` 日志抽屉：`ElTimelineItem :timestamp="item.created_at"`；
  - `CrawlTrendChart.vue` x 轴：`new Date("2026-07-28T00:46:14")`（无 `Z`，JS 按**本地时区**解析 UTC 数字，同样差 8h）。

### 1.2 笔记处理失败无用户决策入口

- 现象：任务 #19 多篇笔记连续处理失败，系统只记 ERROR 日志并继续，用户只能事后在日志里看到，无法及时决定「扫码 / 中止」。
- 根因：`crawl_task.on_failure` 对每篇失败仅 `failed_notes += 1` 并继续；只有 `AuthenticationRequired`（未登录）与验证类错误会 PAUSED。opencli 详情/下载阶段的系统性失败（登录态掉线未被 whoami 识别、风控、opencli 异常）不会被归类，导致整批笔记逐篇失败。

## 2. 设计

### 2.1 前端时间统一转东八区（显示层修复，不动 DB 口径）

新增 `frontend/src/utils/datetime.ts`：

```ts
// 后端 created_at/started_at 为 UTC naive（无 Z），需按 UTC 解析后转东八区显示。
export function formatUtcAsShanghai(value: string | null | undefined): string
```

- 实现：`value` 为空返回 `'-'`；无 `Z`/offset 后缀时补 `Z` 按 UTC 解析；用 `Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false, ... })` 输出 `YYYY-MM-DD HH:mm:ss`；非法输入原样返回。
- 应用点（4 处）：DashboardView 最近任务日志、TasksView 创建时间列、TasksView 日志抽屉 timestamp、CrawlTrendChart x 轴 `formatTime`。
- 后端口径不变（UTC naive 存储），仅显示层转换；`docs/database-design.md` 时间口径章节补一句"前端显示统一经 `formatUtcAsShanghai` 转东八区"。

### 2.2 笔记连续失败熔断（HALT → PAUSED，用户决策）

**语义**：零星单篇失败维持现状（跳过继续）；**连续**失败达到阈值视为系统性问题，任务置 PAUSED，把决策权交给用户。

- 新异常 `CrawlHalted(Exception)`，放 `app/services/crawler.py`（与 `AuthenticationRequired` 等并列）。
- `run_crawl` 主循环维护局部计数 `consecutive_failures`：
  - `on_failure` 中 `+1`；达到阈值 `settings.consecutive_note_failure_limit` 时 raise `CrawlHalted(f"已连续 {n} 篇笔记处理失败，疑似登录态失效或触发风控。最近一次错误：{exc}。请检查浏览器登录/验证状态后点「检测登录并继续」，或「结束抓取」。")`；
  - `processor` 成功（`process_note` 正常返回，含标题不匹配/已存在等跳过）→ 清零。跳过不是失败，也不放大计数。
  - 阈值配置：`Settings.consecutive_note_failure_limit`（env `CONSECUTIVE_NOTE_FAILURE_LIMIT`，默认 `3`），`.env.example` 同步。
- 外层 `except CrawlHalted as exc`：与 `AuthenticationRequired` 同样置 `PAUSED` + `error_message` + ERROR 日志，并复用「自动打开小红书登录页」逻辑（最常见原因就是登录/验证，用户打开浏览器即可检查）。
- 前端 `DashboardView.vue`：PAUSED 状态在「打开小红书登录」「检测登录并继续」之外**新增「结束抓取」按钮**（复用 `finish()`，stop API 已支持 PAUSED → STOPPED）。
- 任务列表/日志里 PAUSED 的 `error_message` 即为用户指引，无需额外 UI。

**明确不做**：
- 博主发现失败（discovery_failures）暂不纳入熔断计数（已有独立 error_message 与启动预检覆盖 opencli 缺失场景）；
- 不做错误消息的 NLP 分类；熔断判定只用连续计数，message 透传最近一次异常原文。

## 3. 测试（TDD 先红后绿）

### 3.1 后端 `tests/test_consecutive_failure_halt.py`（新增）

| 用例 | 断言 |
|---|---|
| 连续 3 篇 process_note 抛异常 | 任务 PAUSED；error_message 含「已连续 3 篇」「检测登录并继续」；ERROR 日志写入；剩余笔记不再处理 |
| 失败→成功→失败×2（阈值 3） | 计数清零不熔断，任务 COMPLETED_WITH_ERRORS |
| 阈值配置为 2 | 连续 2 篇失败即 PAUSED |
| 熔断 PAUSED 后调用 stop | 任务 STOPPED（复用现有 stop 语义回归） |

### 3.2 前端

- `src/utils/datetime.spec.ts`（新增）：UTC naive → 东八区 `+8h`；带 `Z` 输入；空值/非法值。
- `DashboardView.spec.ts` 增补：PAUSED 任务显示「结束抓取」按钮，点击调 `stopTask`；日志时间显示为东八区转换后值（mock `2026-07-28T00:46:14` → 页面含 `08:46:14`）。
- `TasksView.spec.ts` 增补：创建时间列与日志 timestamp 经转换（`+8h`）。
- `CrawlTrendChart` 若有独立 spec 同步；否则经 DashboardView 集成断言。

## 4. 验收

- 后端全量通过（新增 4 用例先红后绿）；前端全量通过、build 通过；
- 真实页面：仪表盘/抓取日志页时间显示为东八区（与本机时钟一致）；
- 改动涉及 `app/tasks/*.py` 与 `app/services/*.py` → **完成后重启 worker/beat**；
- TODO.md 登记并打勾，独立 commit。

## 5. 风险

- 熔断阈值默认 3 对「整批评理都失败」的场景可能在第 3 篇才停，会浪费 2 篇的 opencli 调用——可接受（阈值可配）；
- `CrawlHalted` 继承 `Exception`，必须确保不被 `on_failure` 的 `except Exception` 吞掉——`CrawlHalted` 在 `on_failure` 内部 raise，调用点循环的 `except Exception` 会先捕获！**实现注意**：raise 必须发生在 `on_failure` 返回后由主循环检查，或循环体 `except CrawlHalted: raise` 先于 `except Exception`。采用后者（与 `AuthenticationRequired` 同模式）。
