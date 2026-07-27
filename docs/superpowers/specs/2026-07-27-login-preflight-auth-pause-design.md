# 未登录识别与任务启动登录预检设计

- 日期：2026-07-27
- 状态：已审核（持续授权）
- 关联 TODO：当前待办 #13

## 背景与根因

任务 #19 第三次运行时，博主「从零发现宁波」报错 `opencli 命令执行超过 60s 被强制终止: ['xiaohongshu', 'whoami', ...]`。用户指出真实原因是**未扫码登录**，系统没有识别出来。

取证结论：

1. opencli 的 `xiaohongshu whoami` 在未登录时**不会**以 exit 77（NOPERM/AuthRequiredError）快速退出，而是在浏览器层阻塞等待扫码，直到 Python 层 60s 超时把它 kill，抛 `OpenCLITimeout`。
2. `OpenCLITimeout` 在博主/笔记循环里被 `except Exception` 当作普通抓取失败记录，任务继续盲跑——每个博主/笔记都可能再白等 60s。
3. `crawl_task` 启动时的 `log(..., "login check")` 只写日志、不做真实检查，未登录状态要到第一个博主 60s 超时后才暴露，且呈现为误导性的「博主抓取失败」。

## 目标

未扫码登录时，任务**快速、明确**地进入 PAUSED 并提示用户扫码登录，而不是把 whoami 挂起超时记成普通抓取失败。

## 设计

### 1. `OpenCLIAdapter.check_login()` 超时归类为未登录

`check_login()` 捕获 whoami 的 `OpenCLITimeout`，改抛 `AuthenticationRequired`：

> 小红书登录检查超时：可能未登录或登录窗口正在等待扫码，请完成扫码登录后点击「继续抓取」

whoami 是轻量只读探测，正常 1~2s 返回；阻塞的唯一现实场景就是登录窗口等扫码。exit 77 → `AuthenticationRequired` 的既有映射保持不变。

效果：任务中途登录失效时，既有 `AuthenticationRequired` 冒泡链路直接把任务置 PAUSED，不再按博主/笔记逐个记 60s 超时失败。

### 2. 任务启动真实登录预检

`crawl_task.run` 把只写日志的 `"login check"` 替换为真实调用 `adapter.check_login()`：

- 成功：记日志「登录预检通过」，进入发现阶段。
- 抛 `AuthenticationRequired`：直接冒泡到既有 PAUSED 分支，一次博主/笔记都不会尝试。

### 3. AuthenticationRequired 统一自动打开登录页

既有 PAUSED 分支仅对 `VerificationRequired` 调 `open_xhs_login(settings)`。扩展为所有 `AuthenticationRequired`（含 whoami 超时归类的未登录）都自动打开小红书登录页，并写日志提示用户扫码后点「继续抓取」。打开失败仅记 WARNING，不影响 PAUSED 状态。

### 4. 测试替身同步

测试中 12 个 `FakeAdapter`（test_crawl_execution_ownership / test_crawl_rate_limit / test_crawl_task_resilience / test_opencli_bin）补 `check_login()` no-op，与真实适配器接口对齐。

## 验收

- 新增 `backend/tests/test_login_preflight.py`：
  1. whoami 超时 → `check_login` 抛 `AuthenticationRequired`，文案含「登录」「扫码」。
  2. whoami 正常返回 → `check_login` 透传结果。
  3. 预检抛 `AuthenticationRequired` → 任务 PAUSED、`error_message` 含「登录」、日志含「扫码」、未进入发现阶段（0 笔记）。
  4. 预检通过 → 正常进入发现阶段并产出笔记。
- 既有 `test_crawl_task_resilience.py` 等 12 个 FakeAdapter 测试更新后全过。
- 后端全量测试绿。
- 部署注意：改动涉及 `app/tasks/crawl_task.py` 与 `app/services/opencli_adapter.py`，**必须重启 worker 才生效**（等任务 #19 跑完后执行）。

## 非目标

- 不改 opencli 本身的 whoami 行为（第三方包）。
- 不改动关键词频率控制、博主发现逻辑。
- 前端无改动：PAUSED 任务已展示 `error_message`，新文案直接可见。
