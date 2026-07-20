# 小红书验证码/风控暂停与保留页面设计

> 状态：已通过持续授权审核并实现。

## 1. 目标

抓取过程中出现小红书验证码、扫码或安全验证时，任务不应失败或关闭验证页。系统应进入现有 `PAUSED` 状态，在仪表盘明确提示人工验证，保留当前 crawler 标签页，并自动唤醒 Chrome 小红书页面；用户完成验证后点击现有“检测登录并继续”恢复原任务。

## 2. 根因

当前仅把退出码 `77` 识别为 `AuthenticationRequired`。验证码/风控通常以 stderr 文案、结构化错误消息或内部超时表现，现有代码把它们归为普通 `OpenCLIError/OpenCLITimeout`。同时 `search_recent()` 和 `note()` 的 `finally` 无条件执行 `browser close`，导致人工需要操作的页面也被关闭。

## 3. 方案

新增 `VerificationRequired(AuthenticationRequired)`，集中分类明确验证信号：`captcha`、`安全验证`、`请完成验证`、`扫码验证`、`异常访问验证`、`risk verification`。不使用单独的宽泛“验证”关键词，避免普通文案误判。

OpenCLI 非零退出或结构化错误先检查验证信号，再执行现有退出码/超时分类。命中后：

1. adapter 标记本 session 需要保留；
2. 抛出 `VerificationRequired`；
3. 搜索/详情 `finally` 跳过 crawler tab 清理；
4. `run_crawl` 复用 `AuthenticationRequired` 外层分支写入 `PAUSED`，错误信息为“检测到小红书安全验证，请在 Chrome 完成后点击检测登录并继续”；
5. worker 最佳努力调用现有 `open_xhs_login()` 唤醒 Chrome；打开失败只写 WARNING，不覆盖暂停状态。

普通登录失效仍进入 `PAUSED`，但没有已打开的验证码页时沿用现有清理；普通网络超时仍为超时失败。用户主动停止或执行权失效优先于验证分类，仍执行已有停止清理规则。

## 4. UI

不新增任务状态和页面。仪表盘 PAUSED 卡片复用现有两个 Element Plus 按钮，但当错误信息为验证提示时：

- 状态仍显示“等待登录”；
- Alert 显示需要完成安全验证；
- “打开小红书登录”可再次唤醒 Chrome；
- “检测登录并继续”登录校验成功后复用原任务 ID、进度和开始时间。

## 5. TDD 与验收

- 明确验证文案映射为 `VerificationRequired`，普通 timeout/普通“验证结果”不误判；
- 验证异常时搜索与详情不调用 `browser close`；普通错误、停止仍清理；
- worker 将任务置为 PAUSED，自动打开页面失败不覆盖状态；
- 前端 PAUSED 验证提示、打开页面、检测后继续的组件与 E2E 回归通过；
- 更新 crawler/API/UI 文档，合并两条重复 TODO；全量测试通过。

## 6. 安全边界

系统不自动填写账号、密码、验证码，不自动点击确认，不轮询绕过风控。人工验证完成前不会自动恢复抓取。

## 7. 验收结果

- 验证分类、页面保留、任务暂停、自动唤醒失败降级与用户结束清理的定向回归 `46 passed`。
- 全量后端 `240 passed, 1 skipped`；前端组件 `32 passed`；生产构建成功；Playwright `39 passed`。
- 明确验证码/安全验证信号进入 `PAUSED`；普通 timeout 与无关“验证结果”不误判。
- 验证页保留并自动唤醒 Chrome；人工结束 PAUSED 验证任务会关闭保留 session。
