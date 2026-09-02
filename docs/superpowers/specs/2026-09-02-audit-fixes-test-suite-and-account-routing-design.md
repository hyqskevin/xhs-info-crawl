# 代码评估问题批量修复（测试套件阻断 + 账号路由 + 测试隔离）

> 2026-09-02 全量代码评估产出的 6 类问题，按优先级依次修复。
> 评估基线 commit：5ead318（后端 18 failed / 1115 passed，make test 被收集错误阻断；前端 202 passed 全绿）。

## 目标

1. 恢复 `make test` 可用（消除 collection error 与 11 个引用已删脚本的测试失败）
2. 修复 xhs-accounts 三个端点的 profile/CDP 路由不一致（logout 登出错误 profile、open_login 用 stale 端口）
3. 消除 test_database_init 的 `importlib.reload` 全局引擎污染（连带 keyword PATCH 测试顺序依赖 + 生产库污染风险）
4. ChromePool 端口分配加实际占用检测（跨进程端口冲突）
5. 契约测试与 base-dir 重构后的 .env.example 同步
6. data_dir_migration 端到端测试 mock 进程检测（不依赖本机 .app 进程状态）
7. 清理冗余 import 与仓库垃圾文件

## 设计

### C1. 删除引用已删脚本的测试（commit 07fcc86 删了 backend/scripts/ 但测试残留）

| 文件 | 动作 |
|---|---|
| tests/test_dedupe_cities_script.py | 整文件删除（全部用例测 scripts.dedupe_cities） |
| tests/test_fix_activity_city_code.py | 整文件删除（全部用例测 scripts.migrations.fix_activity_city_code） |
| tests/test_split_blogger_cities.py | 整文件删除（全部用例测 scripts.migrations.split_blogger_cities） |
| tests/test_duplicate_candidates_stop.py | 删 test_cleanup_script_zeroes_duplicate_candidates_idempotent（引用 scripts.cleanup_duplicate_candidates）；保留前 2 个 AST 断言 |
| tests/test_dead_code_cleanup.py | parametrize 移除 ("scripts/dedupe_cities.py", ...) 条目 |

一次性迁移脚本的测试随脚本一起删除——脚本已删，测试无保护对象。

### I2. xhs_accounts.py 路由修复

**logout（L374）**：构造 adapter 补 `profile_alias=account.session_name`，与 check-login 通道对齐。
否则 opencli 走 settings.opencli_default_profile → 清的是默认 profile 的 cookie，账号 cookie 仍在，登出无效。

**open_login（L326-347）**：cdp_endpoint 在 `chrome_pool.acquire()` 之前计算是 stale 的。
改为 acquire 之后用 `_resolve_cdp_endpoint_for_account(account, chrome_pool)`（优先 pool 实例动态端口，
fallback 账号行 cdp_port），与 crawl_task/accounts.py 同口径。DB 端口同步逻辑保留。

**TDD**：新增 tests/test_xhs_accounts_profile_routing.py
- logout 构造 adapter 时 profile_alias == account.session_name（monkeypatch OpenCLIAdapter 捕获参数）
- open_login 在 pool 分配端口 ≠ account.cdp_port 时，adapter 拿到 pool 实例端点

### I1. 测试隔离修复

**根因**：test_database_init.py 的 `importlib.reload(db_mod)` 在 module namespace 原地重执行
database.py，把全局 `engine/SessionLocal` 永久替换为 tmp_path 引擎；monkeypatch 无法恢复 reload
造成的重绑定。keyword PATCH 测试模块在收集期 `from app.core.database import SessionLocal` 拿到的
是原 sessionmaker（./data/app.db），而 app.get_db 调用时查模块全局拿到污染后的 tmp 引擎 →
写与读不同库 → 404 + 生产库被写入测试数据。

**修复**：
- test_database_init.py 删除全部 `importlib.reload(db_mod)` 与配套 `monkeypatch.setattr("app.core.database.settings", ...)`。
  依据：`init_database(settings)` 显式传 settings 时自建 engine（database.py L206），从不依赖模块全局；
  reload/setattr 对被测行为无贡献，纯粹是污染源。
- test_keyword_group_patch_and_legacy_cleanup.py 删除自带的 module-scoped `client` fixture，
  改用 conftest 的 `client`（内含 get_db→db_session override + seed admin）；测试内所有 `SessionLocal()`
  读写改为 `db_session`。断言失败也不再遗留数据到 ./data/app.db。

### I3. ChromePool 端口占用检测

现状：`acquire()` 纯顺序分配（offset%100+9223），不检测端口实际占用；uvicorn 与 celery worker
各持独立全局池，跨进程必然撞端口，且 `_make_chrome_pool_for_task` 会把错误端口持久化到 DB。

修复：分配时用 `socket.bind` 探测端口空闲，占用则跳过取下一个；池耗尽抛 `ChromeLaunchError`。
保留顺序分配语义（多数场景第一个就空闲）。TOCTOU 窗口仍存在（bind 探测与 Chrome 启动之间），
由 `_wait_cdp_ready` 超时警告兜底——本项不改语义只收敛撞端口概率。

TDD：tests/test_chrome_pool.py 补用例——预占 9223 后 acquire 应分配 9224。

### I4. 契约测试同步

test_scaffold_contract.py 期望 `"DATABASE_URL=sqlite:///./data/app.db"` 改为 `"DATABASE_URL="`
（base-dir 模式下 .env.example L90 为 `DATABASE_URL=` 留空自动推导）。语义从"固定路径"变"键存在"。

### I5. data_dir_migration 端到端测试 mock 进程检测

TestDataDirMigrationRunEndToEnd 两个用例直接调 `ddm.run_migration()`，本机正在跑 .app
（uvicorn/celery）时 `is_app_running()` 返 True → AppStillRunningError。
与同文件 `test_migration_aborts_when_app_running`（mock 为 True）对偶：这两个用例
`monkeypatch.setattr(ddm, "is_app_running", lambda: False)`——它们测的是迁移流程本身，
进程检测语义已由专门的类覆盖。

### Minor

- opencli_adapter.py：`import os as _os` → 用顶部 `os`；两处 `import json as _json` → 顶部 `json`
- 删除仓库根垃圾文件：.commit-msg-2.txt / .commit_msg_task7.txt / .commit_msg_p2_6.txt

## 验收

1. `cd backend && pytest -q` 收集零错误；上述 18 个失败全部转绿（failover 3 个红灯除外——那是 TODO#53 进行中的 TDD 红灯，属预期，不在本批范围）
2. `pytest tests/test_database.py tests/test_database_init.py tests/test_keyword_group_patch_and_legacy_cleanup.py`（按此顺序）全绿——顺序依赖消除的回归证据
3. `./data/app.db` 在测试后无 keyword_groups 新增行（生产库不污染）
4. 新增 test_xhs_accounts_profile_routing.py 2 用例先红后绿
5. test_chrome_pool.py 新占用检测用例先红后绿，存量用例不回归
6. 前端 `npm run test -- --run` 保持 202 passed
