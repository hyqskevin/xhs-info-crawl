# crawl_task 主循环接入 run_with_failover adapter 版（TODO#53）

## 1. 背景

`app.services.opencli_failover.run_with_failover` 已是 subprocess 层的主备链式重试原语，
但其抽象层（拼 `opencli --profile alias xxx` 子命令）与 crawl_task 主循环的 OpenCLIAdapter
高层抽象不匹配——crawl_task 需要管 ChromePool 资源、扫码等待、bind_task、状态保存、
token 池刷新等副作用，无法直接套用现有 `run_with_failover`。

crawl_task 当前的账号切换实现是 2026-08-19 引入的 **while-loop + open_account_login +
wait_for_login** 同步扫码机制（见 [2026-08-19-xhs-account-switch-auto-login-design.md](2026-08-19-xhs-account-switch-auto-login-design.md)）。
这一路径已通过 24 个测试（`test_crawl_account_switch_autologin.py` 3 条 + `test_xhs_accounts.py`
账号相关若干条）。

用户 2026-09-01 决策：**C 方案——重写 while 循环，让 crawl_task 主循环接入统一的 failover
抽象**。抽象目标是：**复用现有 `run_with_failover` 思路（链式重试 + AllAccountsFailed），
但接受 adapter 实例作为 command 的载体**。

## 2. 目标

1. 新增 `app.services.adapter_failover.run_with_adapter_failover(command, primary,
   fallback_accounts, ...)`：接受一个 `command: Callable[[OpenCLIAdapter, XhsAccount], T]`
   callable，按账号链式执行：primary → fallback[0] → fallback[1] → ... → 全失败抛
   `AdapterAllFailed(attempts)`。
2. crawl_task `_run_crawl_body` 的 `(Auth, Verify) except` 分支：
   - 把 while-loop **替换为** `run_with_adapter_failover(...)` 一次调用
   - command 内：构造新 adapter（接 profile_alias）、bind_task、检查登录、若未登录则
     open_account_login + wait_for_login、最后执行原 download_and_ocr
   - 任一步骤失败即视为该账号失败，链式换下一个
   - **保留**原 "首成功账号重试当前笔记一次" 语义
   - 全部失败 → `AdapterAllFailed` → 被 except 捕获后翻译为 `CrawlHalted(PAUSED)`
3. 既有 24 个测试：仅调整断言形态，**不**改语义。

## 3. 设计

### 3.1 adapter_failover 原语

```python
# app/services/adapter_failover.py

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class AdapterAttempt:
    session_name: str
    error: Exception  # 该账号 command 抛出的异常


class AdapterAllFailed(RuntimeError):
    def __init__(self, attempts: list[AdapterAttempt]):
        self.attempts = attempts
        lines = [f"主备 {len(attempts)} 个账号全部失败："]
        for a in attempts:
            lines.append(f"  - {a.session_name}: {type(a.error).__name__}: {a.error}")
        super().__init__("\n".join(lines))


def run_with_adapter_failover(
    command: Callable[[OpenCLIAdapter, Any], T],
    primary_account: Any,
    fallback_accounts: Sequence[Any] | None,
    *,
    adapter_factory: Callable[[Any, Any], OpenCLIAdapter],
    bind_task: Callable[[OpenCLIAdapter], None] | None = None,
) -> tuple[T, Any]:
    """主 → 备链式：每个账号跑一次 command(adapter, account)。

    - adapter_factory(account, settings) 负责构造带 profile_alias 的新 adapter
    - bind_task(adapter) 在 adapter 构造后绑定 task 上下文
    - 任一账号 command 成功 → 返回 (结果, used_account)
    - 全部失败 → 抛 AdapterAllFailed(attempts)
    """
```

### 3.2 crawl_task 改动

`_run_crawl_body` 的 `(AuthenticationRequired, VerificationRequired) except` 分支：

**Before**（当前 while-loop，约 75 行）：
```python
except (AuthenticationRequired, VerificationRequired) as exc:
    db.rollback()
    cleanup_incomplete_note(...)
    try: adapter.logout()
    except: pass
    if chrome_pool: try: chrome_pool.release(...)
    switched = False
    while account_index + 1 < len(accounts):
        ... # 复杂 while 循环逐个账号探测登录
    if not switched:
        raise CrawlHalted(f"所有账号均已失效...")
```

**After**（重写）：
```python
except (AuthenticationRequired, VerificationRequired) as exc:
    db.rollback()
    cleanup_incomplete_note(db, entry[1]["url"])
    # ① 主动登出当前失效账号（与现状一致）
    try: adapter.logout()
    except: pass
    if chrome_pool is not None:
        try: chrome_pool.release(accounts[account_index].session_name)
        except: pass
    # ② 链式 failover：primary → fallbacks
    primary = accounts[account_index]
    fallbacks = accounts[account_index + 1:]
    switched = False
    try:
        def _cmd(adapter, account) -> None:
            # bind_task
            if hasattr(adapter, "bind_task"):
                adapter.bind_task(
                    task.id, run_token,
                    execution_guard=lambda: assert_execution_active(db, task.id, run_token, stop_event),
                    warning_sink=lambda m: log(db, task.id, "WARNING", m),
                )
            # 已登录？否则开登录页并等扫码
            logged = False
            try:
                raw = adapter.check_login()
                logged = bool(raw and raw.get("logged_in"))
            except Exception:
                logged = False
            if not logged:
                log(db, task.id, "INFO", f"账号 {account.name!r} 未登录，打开登录页等待扫码")
                try: open_account_login(adapter, settings)
                except: pass
                try: wait_for_login(adapter, settings)
                except (AuthenticationRequired, VerificationRequired):
                    raise  # 让 failover 视为该账号失败，试下一个
            # 探测下一个账号前先把 account_index 滚到对应位置
            # （account_index 由闭包在外层维护）
            # 用新账号重试当前笔记一次
            log(db, task.id, "INFO", f"账号 {primary.name!r} 失效（{exc}），切换到 {account.name!r}")
            staged = download_and_ocr(db, task, run_token, entry[0], entry[1], adapter, settings)
            if staged is not None:
                staged_notes.append(staged)
                consecutive_failures = 0
            # 成功 → 跳出 failover

        def _factory(account, _settings):
            return OpenCLIAdapter(
                settings,
                session=account.session_name,
                cdp_endpoint=_resolve_cdp_endpoint_for_account(account, chrome_pool),
                profile_alias=getattr(account, "session_name", None),
            )

        def _on_success(used_account):
            nonlocal account_index, switched
            account_index = accounts.index(used_account)
            switched = True

        run_with_adapter_failover(
            command=_cmd,
            primary_account=primary,
            fallback_accounts=fallbacks,
            adapter_factory=_factory,
            on_success=_on_success,
        )
    except AdapterAllFailed as fexc:
        if not switched:
            raise CrawlHalted(f"所有账号均已失效，请扫码登录后继续。最近错误：{exc}")
```

### 3.3 不变量 / 必须保留的行为

| 行为 | 现状位置 | 重写后位置 |
|---|---|---|
| 失效账号 logout | 663-665 | 663-665（不变） |
| 失效账号 release ChromePool | 666-670 | 666-670（不变） |
| 新账号未登录 → open_account_login | 705-708 | _cmd 内 |
| wait_for_login 超时 → 试下一个 | 709-714 | _cmd 内 raise 让 failover 接管 |
| 切账号 log | 715 | _cmd 内 |
| 新账号重试 download_and_ocr | 718-741 | _cmd 内 |
| 新账号仍失效 → 跳过本篇 | 720-725 | _cmd 内 raise |
| 全部失败 → CrawlHalted | 743 | 外层 except AdapterAllFailed |
| account_index 维护 | 674-676, 624-625 | _on_success 内 accounts.index |

### 3.4 测试策略

#### 3.4.1 不动语义测试（行为兼容）

- `test_switch_logs_out_failed_and_autologins_next`：
  - A 失效 → logout(A) → failover chain primary=A, fallbacks=[B] → B command：check_login=False → open_account_login(B) → wait_for_login=True → download_and_ocr 成功
  - **预期**：adapter 实例含 A 和 B；A.logout_called=True；B 未 logout；opened=["xhs-backup"]；任务 COMPLETED
- `test_all_accounts_fail_raises_crawl_halted`：
  - A、B 都失效且 B wait_for_login 超时
  - **预期**：failover chain primary=A, fallbacks=[B] → A command 成功（重试成功就跳出 failover，不需要走 B）—— **等等，这里语义有冲突**
  - 实际现状：A 用 download_and_ocr 在第一次主循环 catch 时已经失败（adapter.session in fail_sessions）；
    进入 failover 后 primary 还是 A，`_cmd(A_adapter, A)` 跑 download_and_ocr —— A 还是失败 → 链式试 B
    → B command：wait_for_login 超时 → raise → failover 试下一个（无）→ 全部失败 → AdapterAllFailed → CrawlHalted
  - **预期**：opened=["xhs-backup"]；status=PAUSED；error_message 含 "所有账号均已失效"
- `test_second_account_login_timeout_tries_third`：
  - A 失效 → failover primary=A, fallbacks=[B,C] → A command 失败 → B command: wait_for_login 超时 → C command: check_login=True → download_and_ocr 成功
  - **预期**：opened=["xhs-backup"]；C 未 logout；任务 COMPLETED

**关键**：`_fail_on_sessions` 在 download_and_ocr 内针对 fail_sessions 抛 Auth，与 failover 命令内部一致——failover 的 _cmd 也调 download_and_ocr，所以 A command 同样会因 _fail_on_sessions 失败。

#### 3.4.2 新增测试

- `test_failover_runs_command_for_each_account` —— 验证 failover 调用次数 = primary + len(fallbacks)
- `test_failover_first_success_stops_chain` —— primary 成功时 fallback 不被调用
- `test_failover_raises_adapter_all_failed_when_all_fail`

#### 3.4.3 失效测试（需更新）

`test_crawl_account_switch_autologin.py` 3 条：因 while-loop 改为 failover，原断言
`obs["instances"]` 仍有效（adapter 仍被构造多次），但断言路径需审视"command_builder
失败 vs command_builder 抛 (Auth, Verify) 在 failover 内是否一致"。

## 4. 验收

- [x] `app/services/adapter_failover.py` 存在，含 `run_with_adapter_failover` + `AdapterAllFailed`
- [x] `app/tasks/crawl_task.py` 的 (Auth, Verify) except 分支已重写为基于
      `run_with_adapter_failover` 的调用
- [x] `test_crawl_account_switch_autologin.py` 3 条 PASS
- [x] `test_xhs_accounts.py` 账号相关测试 PASS
- [x] `test_crawl_task_profile_failover.py` 5 条 PASS
- [x] backend 全量 pytest PASS（2026-09-02：1136 passed / 1 skipped / 0 failed）
- [x] worker 重启提示：因改 service 层（crawl_task 调度逻辑），按 AGENTS.md 提示用户
      `cd backend && pkill -f 'celery.*-A app.tasks.celery_app.*worker' ; bash scripts/dev-worker.sh`

### 4.1 实施补记（2026-09-02，相对 §3 设计的增量）

1. **`no_retry_exceptions` 参数**（§3.1 增量）：`run_with_adapter_failover` 增加
   `no_retry_exceptions: Sequence[type[BaseException]] = ()`。crawl_task 传入
   `(ExecutionStopped, ExecutionSuperseded)`——停止/被取代是控制流异常，不是账号失败，
   直通上层交由 `except ExecutionStopped` / `except ExecutionSuperseded` 处理，
   不触发链式换号。TDD：`test_run_with_adapter_failover_no_retry_exceptions_propagate_immediately`。
2. **默认 session（id=None）兼容**（§3.2 增量）：`_failover_adapter_factory` 与
   `reset_adapter_session` 两处 adapter 构造改为
   `profile_alias=... if account.id is not None else None`——无账号配置的默认 session
   在 failover 自愈重试 / 周期性重置时不得注入 `--profile` 路由（opencli 会路由到
   不存在的默认 profile）。TDD：`test_default_session_failover_retry_keeps_profile_alias_none`。
   轮询切换处因有 `len(accounts) >= 2 且全部有 cdp_port` 守卫（默认 session 单账号、
   无 cdp_port 不可达），无需同改。
3. **bind_task 提为独立回调**：原设计把 bind_task 写在 _cmd 内；实现拆为
   `_failover_bind_task` 闭包经原语 `bind_task=` 参数注入（每个 adapter 构造后立即绑定，
   check_login 抛 ExecutionStopped 时也能被 task 日志观测）。
4. **非账号性失败停止链式**：_failover_command 内 download_and_ocr 抛出非 (Auth, Verify)
   异常（opencli 超时等）时按笔记失败处理（on_failure）并返回 None 停止链式，
   不再无意义遍历后续账号。

## 5. 非目标 / 边界

- **不**改 `opencli_failover.run_with_failover`（subprocess 原语不变）
- **不**改 OpenCLIAdapter 接口
- **不**改 ChromePool 生命周期
- **不**改账号优先级排序逻辑
- **不**改 discovery / MiniMax / 阶段 2 行为

## 6. 风险与回滚

- **风险**：failover 抽象引入新边界（_cmd 内 raise 让外层捕获），可能漏 raise (Auth, Verify)
  导致 failover chain 异常终止而非链式继续
- **缓解**：spec §3.3 "不变量" 表逐条核对；3.4.1 三条行为兼容测试覆盖关键路径
- **回滚**：若 24 个测试大量回归，回退到 git 上一个 commit；spec 与 TODO 保留

## 7. 关联 spec

- [2026-08-24-opencli-profile-multi-account-design.md](2026-08-24-opencli-profile-multi-account-design.md) §3.3 主备 failover 设计（本 spec 落地 §3.3 的 adapter 版）
- [2026-08-19-xhs-account-switch-auto-login-design.md](2026-08-19-xhs-account-switch-auto-login-design.md) 原 while-loop 设计（本 spec 替换为 failover 版）