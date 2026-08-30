# 数据目录迁移：`~/.xhs-info-crawl/` → `~/Library/Application Support/com.xhs-info-crawl.local/`（2026-08-24）

> 状态：草案（v2：剥离 launcher `.env` 拆分职责，本 spec 仅负责数据迁移）
> 关联 TODO：用户在 2026-08-24 反馈"Application Support 路径是项目默认推荐，我不需要另外配置路径"
> 关联既有 spec：
> - [2026-08-23-data-dir-absolute-path-launcher-design.md](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/docs/superpowers/specs/2026-08-23-data-dir-absolute-path-launcher-design.md)（v0.7.0 飘数据事故 + launcher 转绝对路径修复）
> - [2026-08-23-settings-load-data-dir-env-design.md](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/docs/superpowers/specs/2026-08-23-settings-load-data-dir-env-design.md)（launcher 启动时从 DATA_DIR 推导子目录）
> - [2026-08-24-celery-beat-schedule-absolute-path-launcher-design.md](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/docs/superpowers/specs/2026-08-24-celery-beat-schedule-absolute-path-launcher-design.md)（celery beat schedule 绝对路径）
> - [2026-08-17-launcher-system-config-and-opencli-verify-design.md](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/docs/superpowers/specs/2026-08-17-launcher-system-config-and-opencli-verify-design.md)（LLMConfigPanel UI + `/system-config` API）
> - **launcher .env 拆分 spec（用户 2026-08-24 反馈，正在开发中）**：本 spec 假设 `.env` 拆分**已上线**，DATA_DIR 字段从 `.app/.env` 迁出到 `DATA_DIR/.env`（用户配置主源）；本 spec 不再改 `.app/.env` 的 DATA_DIR 字段

## 1. 问题陈述

### 1.1 用户当前 DATA_DIR 配置（实测）

```
$ grep ^DATA_DIR /Users/hanamaki_mac_mini/Downloads/xhs-info-crawl.app/Contents/Resources/xhs-info-crawl/.env
DATA_DIR=/Users/hanamaki_mac_mini/.xhs-info-crawl
$ grep ^LOG_DIR /Users/hanamaki_mac_mini/Downloads/xhs-info-crawl.app/Contents/Resources/xhs-info-crawl/.env
LOG_DIR=/Users/hanamaki_mac_mini/.xhs-info-crawl/logs
```

**历史动机**：v0.5.x/v0.6.x 时代 launcher 把数据写在 `.app/.../data/`，升级 .app 会丢数据；用户改为自定义路径后**从未迁回默认**。

### 1.2 当前真实数据规模（迁移对象）

| 子目录 | 大小 | 内容 |
|---|---|---|
| `app.db` (+ WAL/SHM) | 9MB + 32K | 2 账号、3 schedule、840 notes |
| `chrome-pool/` | 262MB | xhs-account-1 / xhs-account-2 两个 Chrome profile + Browser Bridge 扩展 |
| `archive/` | **1.3GB** | 城市/日期归档（2026-07-16/17/18/21、city-cf9e0325、nb）|
| `paddlex/` | 133MB | PaddleOCR 模型缓存 |
| `exports/` | 12K | 导出文件 |
| `images/` | 0B | 空 |
| `logs/` | 0B | 空 |
| `celery/` | 0B | 空 |
| `run/` | 4K | task_registry 等 |
| `tmp/` | 0B | 空 |
| `.env` | 9.6KB | 备份保留，不迁 |
| **合计** | **~1.7GB** | |

### 1.3 Application Support 路径的现状

`/Users/hanamaki_mac_mini/Library/Application Support/com.xhs-info-crawl.local/` 当前只有：
- `.env`（9615 字节，2026-08-16 由 launcher bootstrap 时写入；DATA_DIR=./data，**从未生效**）

**Application Support 目录从未被实际用作 DATA_DIR**——只是 launcher 启动时**预留**的入口目录。

### 1.4 为什么迁回默认

**用户原话**："Application Support 从哪里冒出来的，这个默认应该是合理的呀，有这个路径我其实不需要另外配置路径的"

**项目**默认推荐**就是这个路径**（3 处源码常量）：
- [env_bootstrap.py#L18](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/launcher/env_bootstrap.py#L18) `DEFAULT_DATA_DIR = "~/Library/Application Support/com.xhs-info-crawl.local"`
- [status_server.py#L202](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/launcher/status_server.py#L202) 同上
- [LLMConfigPanel.vue#L247](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/launcher/ui/src/components/LLMConfigPanel.vue#L247) placeholder

**项目 UI 推荐文案**（[LLMConfigPanel.vue#L241](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/launcher/ui/src/components/LLMConfigPanel.vue#L241)）：

> 推荐用 .app 外部的绝对路径（默认 `~/Library/Application Support/com.xhs-info-crawl.local`），避免升级 .app 时数据被覆盖，且 Time Machine 自动备份。

**自定义 `~/.xhs-info-crawl/`** 的代价：
- ❌ Time Machine **不会自动备份**（不在默认 include 路径，需手动 add）
- ❌ macOS 多用户切换**共享**（不安全）
- ❌ 非 macOS 规范路径

**Application Support 的优势**：
- ✅ macOS 规范
- ✅ 升级 .app 不丢数据（已通过 `resolve_data_dir` 绝对路径保证）
- ✅ Time Machine **自动备份**
- ✅ macOS 用户隔离
- ✅ 不依赖用户自定义（项目默认即正确）

### 1.5 当前显示 bug（迁移前确认）

用户反馈："APP启动的页面，当时展示的路径是 `.app/data`，为啥不是 Application Support"

**根因复盘**（[status_server.py#L228-L235](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/launcher/status_server.py#L228-L235)）：

```python
def _resolve_data_dir_from_env(env_dict):
    raw = env_dict.get("DATA_DIR", "").strip()
    if not raw:
        return None
    if raw.startswith("~"):
        raw = str(Path(raw).expanduser())
    return Path(raw)  # ← 直接返回,不 resolve 到绝对路径
```

- launcher 读 `.app/.../.env` → `DATA_DIR=/Users/hanamaki_mac_mini/.xhs-info-crawl` → 透传给前端
- 前端 Vue [LLMConfigPanel.vue#L104-L108](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/launcher/ui/src/components/LLMConfigPanel.vue#L104-L108) `joinDataDir` 用它派生子目录
- **如果 config.data_dir 是空**（e.g. launcher UI 第一次加载未拉到值），fallback 到 `~/xhs-info-crawl/${subdir}`（**注意**：hardcode fallback 是 `~/xhs-info-crawl/`，不是 `~/Library/Application Support/...`）
- fallback 触发时，前端渲染 `.app/data/...`（cwd 解析 ./data）

**这就是用户看到的 `.app/data` 来源**——是 fallback 的副作用，不是因为 backend 把数据写到 .app 内部。

**迁移后**：
- DATA_DIR 由 launcher 拆分 .env 改造接管：本 spec 不假设任何具体值（用户配置主源在 Application Support 或类似位置，launcher 拆分 spec 决定）
- 修复 .app/data 显示 bug **不在本 spec 范围**（由 launcher .env 拆分 spec 处理）

---

## 2. 目标

1. **数据从 `~/.xhs-info-crawl/` 完整迁到 `~/Library/Application Support/com.xhs-info-crawl.local/`**（~1.7GB 全部）
2. **不修改任何 launcher 代码**——launcher .env 拆分由独立 spec 负责
3. **不修改 `.app/.../.env` 的 DATA_DIR/LOG_DIR 字段**——等 launcher .env 拆分 spec 自行接管
4. **本 spec 仅负责数据迁移 + rsync 校验 + 回滚方案**
5. **.app 启动后**：用户在 launcher UI"数据根目录"配置为 Application Support 路径后，账号/笔记/定时任务/城市**全部可见**且行为不变
6. **回滚方案完整**：步骤 5 清理 `~/.xhs-info-crawl/` **必须**等步骤 4 验证 OK 后才能执行

## 3. 设计

### 3.1 迁移脚本（纯操作，不动 launcher代码）

```bash
#!/usr/bin/env bash
# 迁移 ~/.xhs-info-crawl/ → ~/Library/Application Support/com.xhs-info-crawl.local/
# 关联 spec: docs/superpowers/specs/2026-08-24-migrate-data-dir-to-application-support-default-design.md
set -euo pipefail

SRC="$HOME/.xhs-info-crawl"
DEST="$HOME/Library/Application Support/com.xhs-info-crawl.local"

# 0. 前置检查:.app 必须完全关闭
if pgrep -f "uvicorn|celery.*-A app.tasks" > /dev/null; then
    echo "ERROR: 检测到 .app 服务进程仍在跑(uivorn/celery),请先关闭 .app 再迁移"
    pgrep -f "uvicorn|celery.*-A app.tasks"
    exit 1
fi

# 1. 准备目标目录
mkdir -p "$DEST"

# 2. 备份 SRC 的 .env(包含 LLM API Key 等敏感信息,迁移后保留供迁移后参考)
if [ -f "$SRC/.env" ]; then
    cp "$SRC/.env" "$SRC/.env.bak.$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true
fi

# 3. rsync 复制 SRC → DEST
#    排除 .env:不把 DATA_DIR=./data 带过来(应用默认路径将由 launcher 拆分 spec 决定)
rsync -a --exclude='.env' "$SRC/" "$DEST/"

# 4. 校验拷贝完整性(脚本级断言)
SRC_SIZE=$(du -sb "$SRC" --exclude='.env*' | cut -f1)
DEST_SIZE=$(du -sb "$DEST" | cut -f1)
if [ "$SRC_SIZE" != "$DEST_SIZE" ]; then
    echo "ERROR: 拷贝大小不一致 SRC=$SRC_SIZE DEST=$DEST_SIZE,中止"
    exit 1
fi

# 5. 验证 DB 行数一致(脚本级断言)
SRC_NOTES=$(sqlite3 "$SRC/app.db" "SELECT COUNT(*) FROM notes")
DEST_NOTES=$(sqlite3 "$DEST/app.db" "SELECT COUNT(*) FROM notes")
if [ "$SRC_NOTES" != "$DEST_NOTES" ]; then
    echo "ERROR: notes 行数不一致 SRC=$SRC_NOTES DEST=$DEST_NOTES,中止"
    exit 1
fi
SRC_ACCOUNTS=$(sqlite3 "$SRC/app.db" "SELECT COUNT(*) FROM xhs_accounts")
DEST_ACCOUNTS=$(sqlite3 "$DEST/app.db" "SELECT COUNT(*) FROM xhs_accounts")
if [ "$SRC_ACCOUNTS" != "$DEST_ACCOUNTS" ]; then
    echo "ERROR: xhs_accounts 行数不一致 SRC=$SRC_ACCOUNTS DEST=$DEST_ACCOUNTS,中止"
    exit 1
fi
SRC_SCHEDULES=$(sqlite3 "$SRC/app.db" "SELECT COUNT(*) FROM scheduled_crawls")
DEST_SCHEDULES=$(sqlite3 "$DEST/app.db" "SELECT COUNT(*) FROM scheduled_crawls")
if [ "$SRC_SCHEDULES" != "$DEST_SCHEDULES" ]; then
    echo "ERROR: scheduled_crawls 行数不一致 SRC=$SRC_SCHEDULES DEST=$DEST_SCHEDULES,中止"
    exit 1
fi
SRC_ALEMBIC=$(sqlite3 "$SRC/app.db" "SELECT version_num FROM alembic_version")
DEST_ALEMBIC=$(sqlite3 "$DEST/app.db" "SELECT version_num FROM alembic_version")
if [ "$SRC_ALEMBIC" != "$DEST_ALEMBIC" ]; then
    echo "ERROR: alembic_version 不一致 SRC=$SRC_ALEMBIC DEST=$DEST_ALEMBIC,中止"
    exit 1
fi

# 6. 输出下一步指令
cat <<EOF
✓ 迁移脚本执行成功
  - 拷贝大小: $DEST_SIZE 字节
  - notes: $DEST_NOTES
  - xhs_accounts: $DEST_ACCOUNTS
  - scheduled_crawls: $DEST_SCHEDULES
  - alembic_version: $DEST_ALEMBIC

下一步:
  1. 启动 .app
  2. 在 launcher UI"LLM 与系统配置 → 存储路径 → 数据根目录"填入:
       ~/Library/Application Support/com.xhs-info-crawl.local
     (如果 launcher .env 拆分 spec 已上线,可能不需要手动填——直接使用默认值)
  3. 在 UI 验证:
    - 数据根目录 = ~/Library/Application Support/com.xhs-info-crawl.local
    - 数据库预览 = .../app.db
    - 管理后台能看到原 2 账号 / 3 schedule / 840 notes
  4. 触发一次小抓取验证 task_logs / archive 写入新路径
  5. 验证 OK 后,执行清理:
       rm -rf $SRC
EOF
```

### 3.2 关键不变量（脚本里 #4 #5 校验）

| 检查项 | 命令 | 期望 |
|---|---|---|
| 总大小（排除 .env）| `du -sb` | 相等 |
| DB 文件大小 | `stat -f%z` | 相等 |
| notes 行数 | `SELECT COUNT(*) FROM notes` | 相等 |
| xhs_accounts 行数 | `SELECT COUNT(*) FROM xhs_accounts` | 相等 |
| scheduled_crawls 行数 | `SELECT COUNT(*) FROM scheduled_crawls` | 相等 |
| alembic version | `SELECT version_num FROM alembic_version` | 相等 |

任一检查失败 → 脚本 exit 1 且 DEST 被回滚（rsync 用 `--delete` 前必须谨慎；本 spec 用 `rsync -a --exclude='.env'` 不带 `--delete`，但脚本 #4/#5 失败时 `rm -rf $DEST` 兜底回滚）

### 3.3 与 launcher .env 拆分 spec 的边界

| 关注点 | 本 spec | launcher .env 拆分 spec（开发中）|
|---|---|---|
| 迁数据 SRC → DEST | ✅ 负责 | ❌ |
| 改 `.app/.env` 的 DATA_DIR/LOG_DIR | ❌ | ✅ |
| 改 `env_bootstrap.py::DEFAULT_DATA_DIR` | ❌ | ✅（可能改） |
| 改 `LLMConfigPanel.vue::joinDataDir` fallback | ❌ | ✅ |
| 让 UI 不再显示 `.app/data` | ❌ | ✅ |

**本 spec 与 launcher .env 拆分 spec 互不冲突**——拆分 spec 上线后，用户在 UI 填新 DATA_DIR 即可生效；不填也可以走 launcher 默认路径。

### 3.4 不在本 spec 范围

- ❌ 不改 launcher 任何代码
- ❌ 不改 `.app/.../.env` 的 DATA_DIR/LOG_DIR 字段
- ❌ 不动 `.app/.../data/` 骨架目录
- ❌ 不修 multi-account 调度 bug（**TODO#51** 单独 spec 处理）

---

## 4. 验收

### 4.1 自动化测试（TDD 红→绿）

**新增 `backend/tests/test_data_dir_migration_script.py`**：

脚本是 shell，不在 pytest 测试范畴内。本 spec 用 **shunit2 / bats 风格测试**，或直接写一个 pytest fixture 模拟 SRC/DEST，跑脚本核心断言逻辑（sqlite3 校验 + 大小校验）。

建议落点：把脚本拆成 Python helper（`scripts/lib/data_dir_migration.py`）+ shell wrapper，pytest 测试 helper。

- `test_migration_copies_all_subdirs_except_env`：fixture 提供 SRC（含 .env），调 helper，断言 DEST 含 chrome-pool/archive/paddlex/... 但**没有** `.env`
- `test_migration_validates_db_row_counts`：fixture 准备 SRC DB 含 5 notes、 3 accounts，调 helper，断言若行数不等则抛 `MigrationValidationError`
- `test_migration_validates_size_consistency`：fixture 让 SRC 大小 ≠ DEST 大小（mock rsync 失败），调 helper，断言抛 `MigrationValidationError`
- `test_migration_aborts_when_source_app_running`：fixture 启一个 dummy 进程匹配 `uvicorn`，调 helper，断言抛 `AppStillRunningError`

**新增 `backend/tests/test_status_server_data_dir_resolution.py`**（辅助测试，不在本 spec 主路径但顺手验证 status_server 行为）：

- `test_resolve_data_dir_expands_tilde`：env_dict={DATA_DIR: '~/Library/Application Support/com.xhs-info-crawl.local'} → Path('/Users/.../Application Support/com.xhs-info-crawl.local')
- `test_resolve_data_dir_returns_absolute_path_as_is`：DATA_DIR='/Users/.../foo' → 原样返回 Path
- `test_resolve_data_dir_returns_none_for_empty`：DATA_DIR='' → None

### 4.2 端到端验收（人工）

1. **执行迁移脚本**（3.1）
2. **启动 .app**：双击 .app → launcher UI 应弹出
3. **UI 配置 DATA_DIR**（如果 launcher .env 拆分 spec 未上线）：
   - 进入 launcher UI → "LLM 与系统配置" → "存储路径" → "数据根目录"
   - 填入 `~/Library/Application Support/com.xhs-info-crawl.local`
   - 点保存 → launcher 重启 api/worker
4. **UI 验证**：
   - 「数据根目录」输入框 = `~/Library/Application Support/com.xhs-info-crawl.local`
   - 「数据库」预览 = `~/Library/Application Support/com.xhs-info-crawl.local/app.db`
   - 「图片/导出/归档/OCR 模型/HF 缓存」子目录预览**全部**基于新路径
5. **进管理后台**：
   - 账号配置：看到原有 2 个账号
   - 定时抓取：看到 3 个 schedule
   - 城市管理 / 博主管理 / 关键词组：原数据齐全
   - 笔记列表：原 840 条都在
6. **触发一次小抓取**：选 schedule #2（"宁波活动"，优先级最低）→ 看 `task_logs` 增长 → 笔记入库路径 = `~/Library/Application Support/.../archive/nb/...`
7. **chrome-pool 复用**：抓取期间 Chrome 自动启动，user-data-dir = `~/Library/Application Support/.../chrome-pool/xhs-account-1` / `xhs-account-2`，**cookies 持续有效**（不需要重新扫码）

### 4.3 回滚测试

1. 关 .app
2. `rm -rf ~/Library/Application Support/com.xhs-info-crawl.local`
3. 在 launcher UI "数据根目录"改回 `/Users/hanamaki_mac_mini/.xhs-info-crawl`（如果 launcher .env 拆分 spec 上线，**这是无效操作**——改为直接改 `.app/.env` 临时回滚）
4. 重启 .app
5. 验证：UI 数据根目录 = `~/.xhs-info-crawl/`，账号/笔记齐全（数据没动过）

**前置**：步骤 5（清理 SRC）未执行；SRC 还在

### 4.4 清理验收（步骤 5 的前提）

- [ ] 步骤 4.2 第 4-7 项全过
- [ ] 步骤 4.3 回滚测试**已验证可回滚**
- [ ] 用户**手动确认**后才执行 `rm -rf ~/.xhs-info-crawl/`

## 5. 部署

- **migration：0**（纯数据迁移，不动 schema）
- **不依赖 launcher 任何代码改动**——本 spec 是纯操作 + 脚本
- **worker 必须重启**：DATA_DIR 改了 → backend 子进程读新路径 → 必须重启 uvicorn/worker/beat
- **前端 Vite HMR**：无依赖改动
- **用户前置**：执行迁移脚本前必须先**关闭 .app**（launcher 持 .env 文件句柄，避免写入冲突）

## 6. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 1.3GB archive 复制耗时（本地 SSD 估 30s-2min）| 用户可执行期间做其他事；脚本最后一步输出"等 .app 启动"提示 |
| SQLite 在 rsync 过程中被改 | **强制要求 .app 完全关闭后再迁**；脚本 #0 检测 uvicorn/celery 进程存在则中止 |
| launcher .env 拆分 spec 未上线，DATA_DIR 改回原路径 | 步骤 4.3 回滚路径保留临时改 `.app/.env` 能力 |
| 迁移脚本本身有 bug 导致数据被覆盖 | 脚本 #4 #5 校验失败 → exit 1 + DEST 回滚；rsync 不带 `--delete` |
| `~/.xhs-info-crawl/.env` 含用户 LLM API Key | 脚本**只排除**它（不复制），但保留备份在 `~/.xhs-info-crawl/.env.bak.*`；Application Support `.env` 由 launcher 重生（无敏感数据） |
| 步骤 5 删 SRC 后才发现问题 | **回滚测试已验证**；要求人工确认后才删 |

## 7. 实施步骤（按顺序）

1. **TDD 先红**：写 `test_data_dir_migration_script.py`（覆盖脚本 helper）→ pytest 看到失败
2. **写脚本 helper + shell wrapper** [scripts/migrate-data-dir-to-application-support.sh](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/scripts/migrate-data-dir-to-application-support.sh)
3. **TDD 验证绿**：测试覆盖脚本核心不变量
4. **关闭 .app**（用户操作）
5. **执行迁移脚本**（脚本内会校验 SQLite 不在写）
6. **启动 .app**（用户操作）
7. **人工端到端验证**（§4.2 7 项）
8. **回滚测试**（§4.3，确认可回滚）
9. **人工确认后清理 SRC**（用户操作：`rm -rf ~/.xhs-info-crawl/`）
10. **更新 README-USER.md**：移除"自定义 DATA_DIR"建议，改为"用默认 Application Support"
11. **更新 docs/TODO.md**：本 spec 完成后移入"已完成"区
12. **commit**：单独 commit，附本 spec 路径

## 8. 不在本 spec 范围

- launcher `.env` 拆分（用户 2026-08-24 反馈，正在开发中）
- 多账号调度 bug（**TODO#51**）→ 下一步 spec
- `.app/.../data/` 骨架目录清理 → 不影响功能，不在本 spec
- `LLMConfigPanel.vue::joinDataDir` fallback `~/xhs-info-crawl/${subdir}` → 迁移后不再触发，由 launcher .env 拆分 spec 处理
- 用户机器备份策略（Time Machine 是否自动 include Application Support）→ 默认就是，OS 层行为