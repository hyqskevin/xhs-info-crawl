# 2026-08-23 launcher DATA_DIR 相对路径 → 绝对路径

> 用户反馈(v0.7.1 重打后再次出现):"日志没了,定时任务没了,LLM 配置也没了,都是老问题,怎么回事,写 md 和 tdd 验证了吗?"

## 1. 背景

v0.7.0 引入 base dir 模式,用户 .env 写 `DATA_DIR=/Users/hanamaki_mac_mini/.xhs-info-crawl`。设计意图:backend 启动时所有数据(日志 / 定时任务 / LLM 配置 / Chrome 用户数据)都写到 `~/.xhs-info-crawl/`。

### 1.1 现场(2026-08-23 重打 v0.7.1 后再次复现)

```
$ ls -la /Users/hanamaki_mac_mini/.xhs-info-crawl/
drwxr-xr-x  app.db           840 notes / 3762 task_logs / 36 crawl_tasks / 3 scheduled_crawls ✓
drwxr-xr-x  logs/            64 字节,空 ✗
drwxr-xr-x  celery/          8月19日后无变化 ✗
drwxr-xr-x  run/             8月19日后无变化 ✗
drwxr-xr-x  tmp/             8月18日后无变化 ✗
```

DB 里 notes/task_logs/crawl_tasks/scheduled_crawls **数据全在**(用户现场一致),但 logs/run/celery/tmp **几乎是空的** — 这条 .env 是用户**手动 dev 模式时**改过的状态,`./data` 相对路径没被 launcher 修正。

### 1.2 真因(根因)

用户 `~/.xhs-info-crawl/.env`:
```
DATABASE_URL=sqlite:///./data/app.db
DATA_DIR=./data
CHROME_USER_DATA_DIR=data/chrome-pool
```

`./data` 是**相对路径**。dev 模式下 backend 从 `backend/` 子目录启动 → `./data` 解析为 `backend/data/`,数据写在 backend 旁边。

launcher / .app 模式下:
1. `launcher/main.py::bootstrap_env` 调 `set_cache_env_vars` + `update_env_value("API_PORT", ...)` + `update_env_value("WEB_PORT", ...)`,**没有一步把 DATA_DIR 转绝对路径**
2. `launcher/process_manager.py::start_service` 用 `cwd=str(self.project_root)` 启 backend / worker / beat
3. backend 启动后 pydantic-settings 读 .env 看到 `DATA_DIR=./data`,从**当前 cwd** 解析 → `.app/Contents/Resources/xhs-info-crawl/data/`
4. 所有 `data/logs/`, `data/celery/`, `data/run/`, `data/tmp/` 都写到 .app 内

**结果**:
- `notes/task_logs/crawl_tasks/scheduled_crawls` **没丢**是因为你**之前手动 alembic upgrade**时显式传了 `DATABASE_URL=sqlite:////Users/hanamaki_mac_mini/.xhs-info-crawl/app.db`,这条路径走绝对
- `logs/run/celery/tmp` 全丢是因为这些目录 backend 从 cwd 解析,落到 .app 内

为什么用户感受"数据反复丢":
- v0.5.x / v0.6.x:launcher 把 DATA_DIR 强行覆盖为绝对路径(那时候是 `~/Library/Application Support/com.xhs-info-crawl.local`)
- v0.7.0 重写时把 launcher 改成"用户自己设 DATA_DIR",但忘了**在 launcher 启动时把相对路径转绝对路径**,也没 TDD 测试覆盖

## 2. 目标

1. **launcher 启动时**,如果 .env 里的 DATA_DIR 是相对路径(`./data` / `data`),**自动展开为绝对路径**(基于 project_root 或 macOS Application Support 默认)
2. 写入 .env 后再起 backend/worker/beat,让 backend 看到的 DATA_DIR 一定是绝对路径
3. TDD 测试覆盖:相对路径 → 绝对路径的转换逻辑,以及 backend 实际写入路径不丢

## 3. 设计

### 3.1 launcher `bootstrap_env` 修整

`launcher/main.py::bootstrap_env` 在写完端口之后,加一步:

```python
# 6. 把 DATA_DIR 转为绝对路径(防止 .app 内 cwd 解析)
data_dir_raw = _read_env_value(env_path, "DATA_DIR", "")
if data_dir_raw and not Path(data_dir_raw).is_absolute():
    # 相对路径:默认展到 macOS Application Support
    # 保留用户已经设的非空 DATA_DIR 内容,只是修前缀
    absolute = (project_root / data_dir_raw).resolve()
    update_env_value(env_path, "DATA_DIR", str(absolute))
    logger.info("DATA_DIR 相对路径 %s → 绝对路径 %s", data_dir_raw, absolute)
```

### 3.2 backend `Settings` 兜底

`backend/app/core/config.py::Settings` 已有 `Settings.ensure_runtime_directories()`,但**前提**是 DATA_DIR 已经是绝对路径。在 launcher 转绝对路径后,这层就不需要兜底了。

如果 launcher 漏改(DATA_DIR 空),backend 用 Pydantic 默认值 `./data`,**也是相对路径** — 需要在 backend 加 fallback:如果解析后不是绝对路径,fallback 到 `~/Library/Application Support/com.xhs-info-crawl.local/`。

### 3.3 关联修改

`launcher/env_bootstrap.py::update_env_value` 已经支持写 .env,不需要改。`_read_env_value` 已经能读 .env。

## 4. TDD 测试

| Case | 目标 |
|---|---|
| `test_bootstrap_env_converts_relative_data_dir_to_absolute` | launcher `bootstrap_env` 把 `DATA_DIR=./data` 转成 `<project_root>/data` 绝对路径写到 .env |
| `test_bootstrap_env_keeps_absolute_data_dir` | launcher `bootstrap_env` 看到 `DATA_DIR=/Users/foo` 绝对路径不修改 |
| `test_bootstrap_env_handles_empty_data_dir` | launcher `bootstrap_env` DATA_DIR 空时设置成 `~/Library/Application Support/com.xhs-info-crawl.local/` 默认 |
| `test_backend_writes_to_absolute_data_dir` | backend 进程**实际写**的日志/celery/run/tmp 路径等于 launcher 转后的绝对路径,不等于 .app 内 cwd |

文件:
- `launcher/tests/test_main_bootstrap.py`(新)— 前 3 个 case
- `backend/tests/test_data_dir_path_resolution.py`(新)— 第 4 个 case(用 subprocess 拉 uvicorn 测实际写入路径)

## 5. 验收

- [ ] `pytest launcher/tests/test_main_bootstrap.py backend/tests/test_data_dir_path_resolution.py -v` 全过
- [ ] 用户 `~/.xhs-info-crawl/.env` 的 `DATA_DIR=./data` 改为 `<绝对路径>`,重启 .app 后:
  - [ ] `data/logs/api.log` 出现在 `~/.xhs-info-crawl/logs/`,**不**在 `.app/data/logs/`
  - [ ] 新任务入库走 `~/.xhs-info-crawl/app.db`,**不**在 `.app/data/app.db`
  - [ ] 浏览器业务前端能看到历史 scheduled_crawls
- [ ] 重打 .app: `dist/build/xhs-info-crawl-0.7.1-macos-arm64.zip`,拷贝到 `~/Downloads/`

## 6. 关联

- `docs/superpowers/specs/2026-08-17-launcher-storage-base-dir-design.md` — base dir 模式原始设计
- `docs/superpowers/specs/2026-08-22-settings-cities-preload-design.md` — Settings 字段
- `docs/superpowers/specs/2026-08-21-package-startup-auto-migrate-design.md` — alembic upgrade head
- `docs/superpowers/specs/2026-08-23-migration-0028-sqlite-current-timestamp-binding-design.md` — v0.7.0+5(同一发版周期)

## 7. 教训

"用户路径要绝对路径"这条**必须 TDD 覆盖**:
- dev 模式 cwd = backend/ → 相对路径 ok
- launcher 模式 cwd = .app/ → 相对路径 fail
- 两种模式的 cwd 不同,但 .env 共用 → 不在 launcher 转绝对路径,就一定丢数据

**规则**(写到 AGENTS.md):
- 任何 launcher 写 .env 的字段,如果 value 是路径,都必须是绝对路径
- 任何 backend / worker / beat 子进程看到的路径,都必须是 launcher 处理过的绝对路径
- 不允许 .env 里有 `./` 或 `~/` 未展开的相对路径传给子进程