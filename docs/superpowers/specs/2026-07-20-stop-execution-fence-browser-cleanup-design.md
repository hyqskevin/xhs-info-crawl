# 停止执行栅栏与浏览器清理设计

> 状态：待用户审核。

## 1. 目标

保证用户点击“停止抓取”后，当前执行不能再启动新的 OpenCLI 命令，已经启动的 OpenCLI 子进程会被结束，抓取过程中打开的小红书标签页会被尽力关闭，最终任务进入 `STOPPED`。

Celery worker 进程继续保持运行并等待后续任务。停止一条抓取任务不得依赖关闭整个 worker，也不得影响新任务正常启动。

## 2. 已确认的现状与根因

### 2.1 worker 保活不是继续爬取的直接原因

`run_crawl` 是 Celery worker 执行的一条任务。当前任务函数返回后，worker 只会空闲等待新消息，不会自动继续执行旧任务。现有执行令牌和原子领取机制也会拒绝旧 `run_token`、陈旧队列消息及非 `PENDING` 任务。

因此，“任务停止”和“worker 退出”是两个不同概念。关闭 worker 不能作为单任务停止机制，否则会阻断后续任务，并与一期常驻 worker 的部署方式冲突。

### 2.2 OpenCLI 命令之间存在竞态窗口

当前 `OpenCLIAdapter.run()` 的顺序是：启动子进程、登记 PID、等待结束、注销 PID。`search_recent()` 和 `note()` 会连续调用多个 `run()`。

如果停止请求恰好发生在两个命令之间，PID 注册表暂时为空：

1. API 将数据库任务置为 `STOP_REQUESTED`；
2. API 查不到当前 PID，因此没有进程可杀；
3. 已经运行中的 adapter 方法继续执行下一行；
4. 下一条 OpenCLI 命令仍可能被启动；
5. 直到 adapter 方法返回并回到任务阶段检查点，worker 才看到停止状态。

现有阶段级 `assert_execution_active()` 能阻止下一处理阶段和下一篇笔记，但不能完全阻止同一 adapter 方法内部的后续命令。

### 2.3 浏览器标签页清理不是异常安全的

`search_recent()` 和 `note()` 在正常路径末尾调用 `browser close`。如果停止操作杀死了位于 `browser open` 与 `browser close` 之间的 OpenCLI 子进程，方法通过异常提前退出，正常路径的 `browser close` 不会执行。

Chrome 是独立进程，即使 Celery worker 退出，已经打开的标签页也不会因此自动关闭。残留页面不等同于 worker 仍在爬取，但会造成“停止后浏览器还开着”的现象，也可能保留未完成的页面加载。

### 2.4 当前测试覆盖缺口

现有测试验证了：

- stop API 能结束已登记的普通子进程；
- worker 在阶段边界停止且不处理下一篇笔记；
- 停止后的旧任务和旧令牌不会重新领取执行权。

尚未覆盖：

- 停止发生在两个 OpenCLI 命令之间；
- 子进程启动后、PID 登记前收到停止；
- 浏览器打开后异常退出时仍执行标签页清理；
- 停止完成后没有新的 `open`、`eval`、`scroll` 或业务抓取命令。

## 3. 方案比较与决策

### 3.1 采用：命令级执行栅栏 + 异常安全清理

把数据库执行权检查传入 `OpenCLIAdapter`。每条受控 OpenCLI 命令在启动前检查一次，在启动并登记 PID 后再检查一次：

- 启动前检查阻止已知停止状态创建新进程；
- 登记后的第二次检查覆盖“检查通过后、进程登记前”发生停止的竞态；
- 第二次检查失败时，adapter 立即结束刚启动的子进程、等待回收并原样抛出停止或执行权失效异常；
- API 与 adapter 两侧任一方观察到停止，都能让当前命令退出。

浏览器操作使用 `try/finally`。一旦成功打开抓取标签页，无论正常完成、超时、停止、登录失效还是其他异常，都会执行一次有界的最佳努力关闭。

### 3.2 不采用：停止时关闭整个 Celery worker

worker 与 Chrome、OpenCLI 是不同进程。关闭 worker 不能可靠清理 Chrome 标签页，而且会让后续任务无人消费，因此不采用。

### 3.3 不采用：仅缩短 OpenCLI 超时

缩短超时只能降低等待上限，无法关闭命令间的竞态窗口，也不能保证标签页清理，因此不能作为根因修复。

### 3.4 不采用：只依赖阶段检查点

阶段检查点仍保留用于保护数据库写入和处理流程，但粒度不足以约束 adapter 方法内部的连续浏览器命令。

## 4. 详细设计

### 4.1 执行检查回调

`OpenCLIAdapter.bind_task()` 在现有 `task_id` 和 `run_token` 之外接收一个无参数执行检查回调。回调成功时返回 `None`；任务停止或令牌失效时抛出现有的 `ExecutionStopped` 或 `ExecutionSuperseded`。同时接收一个可选的 WARNING 回调，用于把浏览器清理失败写入当前任务日志。

两个回调都由 `run_crawl` 创建：执行检查复用现有 `assert_execution_active(db, task_id, run_token)`；WARNING 回调复用当前任务日志函数。adapter 不直接依赖 SQLAlchemy、数据库模型或任务状态枚举。

未绑定抓取任务的配置中心 OpenCLI 登录测试、博主补全等调用不设置回调，保持现有行为。

### 4.2 命令启动栅栏

普通业务命令按以下顺序执行：

1. 调用执行检查回调；
2. 启动 OpenCLI 子进程；
3. 按 `task_id + run_token` 登记 PID；
4. 再次调用执行检查回调；
5. 如果第二次检查失败，立即结束并回收刚启动的子进程，然后抛出原异常；
6. 等待命令正常结束或超时；
7. 在 `finally` 中按令牌注销 PID。

这套顺序覆盖以下并发情况：

- 停止早于第一次检查：不启动进程；
- 停止发生在第一次检查与 PID 登记之间：第二次检查结束新进程；
- 停止晚于 PID 登记：stop API 从注册表找到并结束进程；
- 旧执行被新 `run_token` 取代：与停止相同，不能继续发起命令。

### 4.3 浏览器标签页清理

`search_recent()` 和 `note()` 在成功执行 `browser open` 后记录“标签页已打开”，并用 `try/finally` 包裹等待、滚动、解析和详情命令。

`finally` 中调用专用的最佳努力关闭逻辑：

- 关闭命令不受业务执行栅栏阻止，否则 `STOP_REQUESTED` 会让清理命令自身无法执行；
- 清理仍使用同一个 OpenCLI session，只关闭本次抓取打开的活动标签页，不退出用户的 Chrome；
- 清理设置不超过 10 秒的独立超时；
- 清理失败通过绑定的 WARNING 回调写入当前任务日志；未绑定任务时退回模块 logger，但不得把已经停止的任务改成 `FAILED`；
- 无论清理成功或失败，PID 注册项最终必须被移除。

如果 `browser open` 本身失败，不执行多余关闭。

### 4.4 worker 和任务状态

停止后的目标状态仍是 `STOPPED`，并清空 `current_stage`、`current_note`，写入 `finished_at` 和停止日志。

`run_crawl` 返回后 Celery worker 保持运行。验收必须证明同一个 worker 能继续领取下一条新任务；不得新增“一条任务结束后关闭 worker”的行为。

### 4.5 可观测性

停止日志区分以下结果：

- 已请求停止；
- 当前 OpenCLI 子进程是否被结束；
- worker 已确认停止；
- 浏览器标签页清理失败时的 WARNING。

日志不得记录登录 Cookie、JWT、`xsec_token` 完整值或其他敏感信息。

## 5. TDD 范围

先补失败测试并观察红灯，再修改实现：

1. adapter 已绑定停止回调时，第一次检查失败，不允许调用 `subprocess.Popen`；
2. 第一次检查成功、PID 登记后第二次检查失败时，刚启动的子进程被结束并回收；
3. stop 发生在两个连续 OpenCLI 命令之间时，第二条业务命令不会启动；
4. `search_recent()` 在打开标签页后任一中间命令失败，仍调用一次关闭；
5. `note()` 在打开标签页后收到 `ExecutionStopped`，仍调用一次关闭；
6. 清理关闭失败只记录 WARNING，不覆盖 `STOPPED`；
7. 停止后注册表不存在该 `task_id + run_token` 的活动 PID；
8. worker 返回当前任务后仍能领取使用新令牌的新任务；
9. 配置中心未绑定任务的 OpenCLI 调用保持兼容。

后端测试放在 `backend/tests/test_opencli_execution_fence.py` 及相关现有任务测试中；E2E 案例记录在 `tests/test-stop-execution-fence-browser-cleanup.md`。

## 6. 文档改动

实现时同步更新：

- `docs/crawler-design.md`：明确“退出”指退出当前 Celery 任务函数，worker 保活；补充命令级执行栅栏和标签页清理；
- `docs/api-doc.md`：说明停止请求的最终确认和日志语义；
- `docs/TODO.md`：完成后把本事项移入“已完成”；
- `tests/test-stop-execution-fence-browser-cleanup.md`：记录自动化与真实浏览器验收步骤。

## 7. 验收标准

- 点击停止后，不再启动新的业务 OpenCLI 命令；
- 已登记的当前 OpenCLI 子进程在 5 秒内结束；
- 点击停止后 5 秒内不再启动新的业务命令；包含最多 10 秒最佳努力标签页清理时，任务最迟在 15 秒内进入 `STOPPED`；
- 停止完成后 PID 注册表无该任务和令牌的活动记录；
- 抓取打开的活动标签页被关闭，用户其他 Chrome 标签页和登录态不受影响；
- Celery worker 不退出，并能正常执行下一条新任务；
- 旧任务、旧令牌及陈旧队列消息不能再发起 OpenCLI 命令或写入数据；
- 后端全量测试通过，且真实本地 worker 验收“启动抓取 → 中途停止 → 再启动新抓取”通过；
- Git 变更不包含 Cookie、Token、`.env` 或其他本地敏感信息。

## 8. 不在本次范围

- 不关闭或自动重启 Celery worker；
- 不关闭用户整个 Chrome；
- 不清理非本次抓取创建的普通用户标签页；
- 不迁移 Redis 或使用 Celery revoke；
- 不改变活动提取、OCR、去重和周报业务逻辑。
