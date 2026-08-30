# launcher 检测陈旧 DATA_DIR 并 fallback 默认路径（2026-08-24）

> 状态：草案
> 关联 TODO：用户在 2026-08-24 反馈"我这里删掉，是不是走默认了"——按 .app/.env 里 `DATA_DIR=` 过期路径的目录已被用户 `rm -rf` 的语义，应用应自动 fallback 到 `DEFAULT_DATA_DIR`
> 关联既有 spec：
> - [2026-08-23-data-dir-absolute-path-launcher-design.md](2026-08-23-data-dir-absolute-path-launcher-design.md)（v0.7.0+6 飘数据修复 + `resolve_data_dir` 把 `.app/.env` 的 DATA_DIR 写成绝对路径）
> - [2026-08-23-settings-load-data-dir-env-design.md](2026-08-23-settings-load-data-dir-env-design.md)（Settings 加载优先级：DataDir 源胜 dotenv）
> - [2026-08-24-bootstrap-env-system-keys-only-design.md](2026-08-24-bootstrap-env-system-keys-only-design.md)（用户正在开发的 `.env` 拆分 spec：`LAUNCHER_SYSTEM_KEYS` 仍含 `DATA_DIR`/`LOG_DIR`）
> - [2026-08-24-migrate-data-dir-to-application-support-default-design.md](2026-08-24-migrate-data-dir-to-application-support-default-design.md)（数据从 `~/.xhs-info-crawl/` 迁到 Application Support 默认路径）

## 1. 问题陈述

### 1.1 现场现象（2026-08-24 用户原话）

```
"我这里删掉，是不是走默认了"
```

用户已执行数据迁移脚本把 `~/.xhs-info-crawl/` 拷到 `~/Library/Application Support/com.xhs-info-crawl.local/`，但 **`.app/.env` 里 `DATA_DIR=/Users/hanamaki_mac_mini/.xhs-info-crawl` 仍指向旧路径**（截图显示 launcher UI "数据根目录" 还是 `/Users/hanamaki_mac_mini/.xhs-info-crawl`）。

按"默认"语义，用户期望：**源目录被删除后，launcher 应自动 fallback 到 DEFAULT_DATA_DIR，不要求用户在 UI 里手动改**。

### 1.2 当前实际行为

`launcher/main.py::bootstrap_env` 第 159-164 行：

```python
resolved_data_dir = resolve_data_dir(env_path, project_root=project_root)
```

`env_bootstrap.py::resolve_data_dir` (L339-L375)：

```python
def resolve_data_dir(env_path, *, project_root, default=None):
    raw = _read_env_value(env_path, "DATA_DIR", "")
    if not raw:
        raw = default or DEFAULT_DATA_DIR
    # ... 解析为绝对路径,写回 .env ...
    return resolved_str
```

行为细节：
- `.app/.env` 写了 `DATA_DIR=/Users/hanamaki_mac_mini/.xhs-info-crawl`（v0.7.0+6 时代 launcher 主动写入的绝对路径）
- `raw` 非空 → 走 `expanduser` / `is_absolute()` 分支，**永远走不到 `default or DEFAULT_DATA_DIR`**
- 即使该目录已被用户 `rm -rf`，launcher 也**信任 `.env` 的字面值**，继续用旧路径
- 下次 .app 启动后：
  - backend uvicorn 用 `DATA_DIR=/Users/hanamaki_mac_mini/.xhs-info-crawl`（不存在路径）
  - SQLite 连接 / 日志创建全失败
  - 用户体感："迁移后 .app 起不来了"

### 1.3 用户已做的迁移（实测）

```
✓ 迁移脚本执行成功
  - 拷贝大小: 1806279201 字节
  - notes: 840
  - xhs_accounts: 2
  - scheduled_crawls: 3
  - alembic_version: 0028
```

数据已在 `~/Library/Application Support/com.xhs-info-crawl.local/`（1.7GB），但 `.app/.env` 没动。

### 1.4 历史动机（不删这条 spec 的原因）

- `LAUNCHER_SYSTEM_KEYS` 白名单（2026-08-24 用户 spec）仍含 `DATA_DIR`——`.app/.env` 必然持续维护这条 key
- `resolve_data_dir` 信任 `.env` 字面值的语义不变（避免引入 "launcher 替用户决定路径" 的副作用）
- 唯一例外：**字面值指向的目录物理上不存在**——这是"陈旧配置"信号，明确需要 fallback

## 2. 目标

1. **`.app/.env` 的 DATA_DIR 字段指向不存在的目录时，launcher 主动 fallback 到 `DEFAULT_DATA_DIR`**（macOS Application Support 路径），让用户的"删除源目录 = 走默认"心智模型成立。
2. **fallback 是一次性的可见事件**——launcher 必须在日志里明确写出 "陈旧 DATA_DIR=X 不存在 → fallback 默认路径 Y"，方便用户在 UI / 启动器日志卡片看到。
3. **新 fallback 的路径同时写回 `.app/.env` 的 DATA_DIR 字段**——下次启动不再重复触发 fallback，且 Settings 走 dotenv 源能直接拿到正确路径。
4. **fallback 失败（默认路径也不可写/不存在）时 launcher 启动失败 + 日志可查（无独立 UI 报错卡）**——fail-fast，不让 backend 在未知状态下启动。错误信息通过 `logger.error` 输出到启动器日志文件。
5. **不动 `DATA_DIR/.env` 的 DATA_DIR 字段**——它是 Settings 走的 DataDir 源（胜 dotenv），由 `ensure_data_dir_env` 负责，与本 spec 解耦。
6. **不动 `LAUNCHER_SYSTEM_KEYS` 白名单**——与用户正在开发的 `.env` 拆分 spec 解耦。
7. **不做"目录存在但不含 app.db"的判断**——避免 launcher 替用户决定"是不是数据目录"。仅目录物理不存在时才算陈旧。
8. **不备份陈旧值**——直接覆盖 `.env` 的 DATA_DIR 字段。简化行为，事后无法追溯（如果用户需要可走 git 历史或备份文件恢复）。

## 3. 设计

### 3.1 新增 `is_data_dir_stale` 函数

`launcher/env_bootstrap.py` 新增：

```python
def is_data_dir_stale(data_dir_str: str) -> tuple[bool, str]:
    """检测 .app/.env 的 DATA_DIR 字面值是否指向"陈旧"路径。

    陈旧定义:
    - 路径解析后物理上不存在(目录不存在)
    - 路径解析后存在但不含 app.db(用户迁移时把源目录删了,新建的空目录)——
      此条由调用方决定是否纳入,本函数只负责纯"目录存在"判断

    Returns:
        (stale, reason) 元组
        - stale=True:陈旧,reason 说明原因(供日志)
        - stale=False:路径存在,reason 为空
    """
    if not data_dir_str:
        return True, "DATA_DIR 字段缺失/空"
    try:
        candidate = Path(data_dir_str).expanduser()
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (project_root / candidate).resolve()
    except (OSError, RuntimeError) as exc:
        return True, f"DATA_DIR 解析失败: {exc}"

    if not resolved.exists():
        return True, f"DATA_DIR 路径不存在: {resolved}"
    if not resolved.is_dir():
        return True, f"DATA_DIR 不是目录: {resolved}"

    return False, ""
```

### 3.2 `resolve_data_dir` 新增陈旧检测 + fallback 分支

```python
def resolve_data_dir(env_path, *, project_root, default=None):
    """解析 .env 的 DATA_DIR 为绝对路径,写入并返回。

    解析规则(v0.7.0+6 + 2026-08-24 陈旧 fallback):
    1. 缺失 / 空字符串 → 走 default 参数(DEFAULT_DATA_DIR),展开 ~ 后返回
    2. 字面值 → 解析为绝对路径
    3. **新增**:解析后路径不存在 → 视为陈旧,fallback 到 default + 日志告警
    4. fallback 后默认路径也不可写 → 抛 StaleDataDirFallbackError,由 bootstrap_env 捕获
    5. 已是绝对路径且存在 → 原样返回
    """
    raw = _read_env_value(env_path, "DATA_DIR", "")
    fallback_target = default or DEFAULT_DATA_DIR

    if not raw:
        # 缺失/空 → 走 fallback,跟原来一样
        return _resolve_and_write(env_path, fallback_target, project_root)

    # 已有字面值 → 先解析
    try:
        candidate = Path(raw).expanduser()
        if candidate.is_absolute():
            candidate_resolved = candidate.resolve()
        else:
            candidate_resolved = (project_root / candidate).resolve()
    except (OSError, RuntimeError):
        candidate_resolved = None

    # 新增:陈旧检测 → fallback
    if candidate_resolved is None or not candidate_resolved.exists() or not candidate_resolved.is_dir():
        stale_reason = (
            "路径不存在" if candidate_resolved and not candidate_resolved.exists()
            else "路径解析失败" if candidate_resolved is None
            else "路径不是目录"
        )
        logger.warning(
            ".env DATA_DIR=%r 已陈旧(%s),fallback 到默认路径 %s",
            raw, stale_reason, fallback_target,
        )
        # fallback 到默认;_resolve_and_write 内部会校验默认路径可写,失败抛 StaleDataDirFallbackError
        return _resolve_and_write(env_path, fallback_target, project_root, _check_writable=True)

    # 路径有效 → 原样返回(沿用 v0.7.0+6 行为)
    resolved_str = str(candidate_resolved)
    if not env_path.exists() or _read_env_value(env_path, "DATA_DIR", "") != resolved_str:
        update_env_value(env_path, "DATA_DIR", resolved_str)
    return resolved_str
```

### 3.3 新增异常 `StaleDataDirFallbackError`

```python
class StaleDataDirFallbackError(Exception):
    """.env DATA_DIR 陈旧 + fallback 到默认路径也失败(默认路径不可写/不存在)。

    bootstrap_env 捕获此异常后,launcher 启动失败 + UI 报错卡。
    """
```

### 3.4 fallback 路径可写性校验

`_resolve_and_write(env_path, target_path, project_root, *, _check_writable=False)`：

```python
def _resolve_and_write(env_path, target_path, project_root, *, _check_writable=False):
    """把 target_path 解析为绝对路径,校验可写(可选),写回 env_path。

    Args:
        env_path: .env 文件路径
        target_path: 目标 DATA_DIR 字面值(可能是 default 字符串)
        project_root: launcher project_root(用于解析相对路径)
        _check_writable: True 时校验 target_path 解析后可写,失败抛 StaleDataDirFallbackError

    Raises:
        StaleDataDirFallbackError: _check_writable=True 且路径不可写/不存在时
    """
    candidate = Path(target_path).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (project_root / candidate).resolve()

    if _check_writable:
        # 校验路径可写:目录不存在 → mkdir(parents=True, exist_ok=True);不可写 → 抛异常
        if not resolved.exists():
            try:
                resolved.mkdir(parents=True, exist_ok=True)
            except (OSError, PermissionError) as exc:
                raise StaleDataDirFallbackError(
                    f"陈旧 DATA_DIR fallback 失败:默认路径 {resolved} 不可创建({exc})。"
                    f"请手动检查磁盘权限或 .env 的 DATA_DIR 字段"
                ) from exc
        if not os.access(str(resolved), os.W_OK):
            raise StaleDataDirFallbackError(
                f"陈旧 DATA_DIR fallback 失败:默认路径 {resolved} 不可写。"
                f"请手动检查磁盘权限或 .env 的 DATA_DIR 字段"
            )

    resolved_str = str(resolved)
    update_env_value(env_path, "DATA_DIR", resolved_str)
    return resolved_str
```

### 3.5 `bootstrap_env` 加一行 INFO 日志 + 异常捕获

```python
try:
    resolved_data_dir = resolve_data_dir(env_path, project_root=project_root)
except StaleDataDirFallbackError as exc:
    # 失败卡 → logger.error 写启动器日志,然后 raise 让 main() 退出
    logger.error("DATA_DIR 初始化失败: %s", exc)
    raise
logger.info("DATA_DIR 解析: %s", resolved_data_dir)
# 新增:如果发生了 fallback,在启动器日志卡片能看到一行醒目的告警
# (logger.warning 已经由 resolve_data_dir 内部输出)
```

`launcher/main.py::main()` 直接调 `bootstrap_env(project_root)`，没有顶层 try/except——`StaleDataDirFallbackError` 沿调用栈冒到 `main()`，进程退出，traceback 由 `logging.basicConfig` 输出到 stderr 和启动器日志文件（`data/logs/`）。**没有独立的 UI 报错卡**——和 v0.7.0+9 时代 SECRET_KEY 占位、DATA_DIR 相对路径 bug 一致，都是异常退出 + 日志可查。本 spec §3.5 加 try/except 是为了让 `logger.error("DATA_DIR 初始化失败: %s")` 这一行在 traceback 之前先输出，给用户一个明确根因；不是新增 UI 机制。

### 3.6 LOG_DIR 也加陈旧检测（可选,顺带做）

`.app/.env` 的 `LOG_DIR=/Users/hanamaki_mac_mini/.xhs-info-crawl/logs` 同样会在源目录删除后变成"路径不存在"——这会让 `process_manager` 启动 uvicorn/celery 时报 FileNotFoundError。

但 LOG_DIR 的兜底已有：`process_manager.py::resolve_logs_dir` (L55-L83) 已有 "缺失 → 退化到 DATA_DIR/logs → 兜底 project_root/data/logs" 三级 fallback。所以 LOG_DIR 不需要单独处理陈旧检测——只要 DATA_DIR fallback 成功，LOG_DIR 自动跟着走新路径。

**决策**：本 spec **只动 DATA_DIR 的陈旧检测**，LOG_DIR 不动。验证脚本里会确认两者协同。

### 3.7 Settings 加载行为（无需改）

- Settings 的 `data_dir` 字段由 dotenv / DataDir 源决定
- dotenv 源 = `.app/.env` 的 `DATA_DIR`（已被本 spec fallback 写成 `~/Library/Application Support/com.xhs-info-crawl.local` 的绝对路径）
- DataDir 源 = `~/Library/Application Support/com.xhs-info-crawl.local/.env` 的 `DATA_DIR`（用户迁移脚本已写入，跟 dotenv 源一致）
- 两者一致 → Settings 拿到新路径 → 后端正常工作

### 3.8 边界 / 不动的东西

| 不动 | 原因 |
|---|---|
| `LAUNCHER_SYSTEM_KEYS` / `LAUNCHER_USER_KEYS` | 用户正在开发的 `.env` 拆分 spec 范围 |
| `.app/.env` 的字段名集合 | 同上 |
| `DATA_DIR/.env` 的任何字段 | Settings 走的 DataDir 源，由 `ensure_data_dir_env` 维护 |
| `Settings.data_dir` 默认值 | Settings 默认就是 `./data`，已由 `resolve_data_dir` 兜底 |
| `process_manager.py::resolve_logs_dir` 的 LOG_DIR fallback 链 | 已有三级 fallback，跟 DATA_DIR 协同即可 |
| `update_env_value` / `read_env_value` 工具函数 | 复用，不动 |

## 4. TDD 测试

### 4.1 `launcher/tests/test_resolve_data_dir_stale.py`

**新增文件**。覆盖以下 case：

```python
class TestResolveDataDirStale:
    """launcher 检测 .app/.env 的 DATA_DIR 陈旧值并 fallback 默认。"""

    def test_resolve_data_dir_falls_back_when_target_missing(self, tmp_path):
        """DATA_DIR= 不存在的绝对路径 → fallback 到 DEFAULT_DATA_DIR,写回 .env"""
        env_path = tmp_path / ".env"
        env_path.write_text("DATA_DIR=/nonexistent/path/data\n", encoding="utf-8")
        result = resolve_data_dir(env_path, project_root=tmp_path)
        # fallback 默认 = ~/Library/Application Support/com.xhs-info-crawl.local
        expected = str(Path("~/Library/Application Support/com.xhs-info-crawl.local").expanduser())
        assert result == expected
        # .env 已被改写为绝对路径
        assert _read_env_value(env_path, "DATA_DIR", "") == expected

    def test_resolve_data_dir_does_not_fallback_when_target_exists(self, tmp_path):
        """DATA_DIR= 存在的绝对路径 → 沿用,不 fallback"""
        real_dir = tmp_path / "existing-data"
        real_dir.mkdir()
        env_path = tmp_path / ".env"
        env_path.write_text(f"DATA_DIR={real_dir}\n", encoding="utf-8")
        result = resolve_data_dir(env_path, project_root=tmp_path)
        assert result == str(real_dir.resolve())

    def test_resolve_data_dir_does_not_fallback_when_target_exists_but_no_app_db(self, tmp_path):
        """目录存在但不含 app.db → 不 fallback(避免 launcher 替用户决定是不是数据目录)"""
        empty_dir = tmp_path / "empty-dir"
        empty_dir.mkdir()
        env_path = tmp_path / ".env"
        env_path.write_text(f"DATA_DIR={empty_dir}\n", encoding="utf-8")
        result = resolve_data_dir(env_path, project_root=tmp_path)
        # 沿用字面值,不 fallback
        assert result == str(empty_dir.resolve())

    def test_resolve_data_dir_falls_back_when_path_is_file_not_dir(self, tmp_path):
        """DATA_DIR= 指向一个文件而非目录 → fallback"""
        f = tmp_path / "not-a-dir"
        f.write_text("x")
        env_path = tmp_path / ".env"
        env_path.write_text(f"DATA_DIR={f}\n", encoding="utf-8")
        result = resolve_data_dir(env_path, project_root=tmp_path)
        assert "Library/Application Support" in result

    def test_resolve_data_dir_falls_back_when_path_empty(self, tmp_path):
        """DATA_DIR= 空字符串 → fallback(沿用 v0.7.0+6 行为)"""
        env_path = tmp_path / ".env"
        env_path.write_text("DATA_DIR=\n", encoding="utf-8")
        result = resolve_data_dir(env_path, project_root=tmp_path)
        assert "Library/Application Support" in result

    def test_resolve_data_dir_logs_warning_on_stale(self, tmp_path, caplog):
        """陈旧 fallback 时必须输出 logger.warning,启动器日志卡片能看到"""
        env_path = tmp_path / ".env"
        env_path.write_text("DATA_DIR=/stale/path\n", encoding="utf-8")
        with caplog.at_level("WARNING", logger="launcher.env_bootstrap"):
            resolve_data_dir(env_path, project_root=tmp_path)
        assert any("陈旧" in r.message or "fallback" in r.message.lower() for r in caplog.records)

    def test_resolve_data_dir_uses_default_param_over_env_default(self, tmp_path):
        """default 参数显式传非 DEFAULT_DATA_DIR 时,陈旧 fallback 用 default 参数"""
        env_path = tmp_path / ".env"
        env_path.write_text("DATA_DIR=/stale\n", encoding="utf-8")
        custom_default = str(tmp_path / "custom-default")
        result = resolve_data_dir(env_path, project_root=tmp_path, default=custom_default)
        assert result == custom_default

    def test_resolve_data_dir_idempotent_after_fallback(self, tmp_path):
        """fallback 写回 .env 后,再次调用 resolve_data_dir 应走"路径有效"分支,不再重复触发 warning"""
        env_path = tmp_path / ".env"
        env_path.write_text("DATA_DIR=/stale\n", encoding="utf-8")
        first_result = resolve_data_dir(env_path, project_root=tmp_path)
        assert "Library/Application Support" in first_result

        # 第二次:caplog 不应再捕到 warning
        with caplog.at_level("WARNING", logger="launcher.env_bootstrap"):
            resolve_data_dir(env_path, project_root=tmp_path)
        assert not any("陈旧" in r.message for r in caplog.records)

    def test_resolve_data_dir_raises_on_unwritable_default(self, tmp_path, monkeypatch):
        """陈旧 fallback 时默认路径不可写 → 抛 StaleDataDirFallbackError"""
        env_path = tmp_path / ".env"
        env_path.write_text("DATA_DIR=/stale\n", encoding="utf-8")
        # mock DEFAULT_DATA_DIR 指向一个不可写的位置(/dev/null/foo)
        unwritable = Path("/dev/null/should-not-exist")
        monkeypatch.setattr("launcher.env_bootstrap.DEFAULT_DATA_DIR", str(unwritable))
        with pytest.raises(StaleDataDirFallbackError, match="fallback 失败"):
            resolve_data_dir(env_path, project_root=tmp_path)
```

### 4.2 既有 spec 的 TDD 验证（保持不回归）

- `launcher/tests/test_bootstrap_env_user_keys.py`（用户 spec 的 TDD）—— 全绿
- `backend/tests/test_settings_load_data_dir_env.py`（2026-08-23 spec 的 TDD）—— 全绿
- `backend/tests/test_data_dir_migration_script.py`（2026-08-24 迁移 spec 的 TDD）—— 全绿

## 5. 验收

1. **`launcher/tests/test_resolve_data_dir_stale.py` 9 case 全绿**
2. **既有 spec TDD 不回归**：
   - `test_bootstrap_env_user_keys.py` 全绿
   - `test_settings_load_data_dir_env.py` 全绿
   - `test_data_dir_migration_script.py` 全绿
3. **全量 `make test`** 通过
4. **现场验证（用户机器）**：
   - 状态前置：`.app/.env` 含 `DATA_DIR=/Users/hanamaki_mac_mini/.xhs-info-crawl`（过期），`~/Library/Application Support/com.xhs-info-crawl.local/` 已有数据（迁移脚本已跑）
   - **步骤 1**:用户执行 `rm -rf /Users/hanamaki_mac_mini/.xhs-info-crawl`（源目录已删）
   - **步骤 2**:启动 .app
   - **预期**:
     - 启动器日志卡片显示 warning: `.env DATA_DIR='/Users/hanamaki_mac_mini/.xhs-info-crawl' 已陈旧(路径不存在),fallback 到默认路径 /Users/.../Library/Application Support/com.xhs-info-crawl.local`
     - 启动器日志卡片显示 INFO: `DATA_DIR 解析: /Users/.../Library/Application Support/com.xhs-info-crawl.local`
     - LLMConfigPanel "数据根目录" = `~/Library/Application Support/com.xhs-info-crawl.local`（UI 自动反映）
     - "数据库预览" = `.../app.db`（新路径的 db）
     - 管理后台账号 / schedule / notes 齐全（840 / 2 / 3）
   - **步骤 3**:抓一次小抓取,验证 `task_logs / archive` 写入新路径
   - **步骤 4**:重启 .app,验证 warning 不再触发（已 fallback 写回 .env,路径有效）
   - **步骤 5**:fallback 失败场景（人工破坏默认路径权限,如 `chmod 000 ~/Library/Application\ Support/com.xhs-info-crawl.local`）→ 启动 .app 应启动失败 + 日志显示"陈旧 DATA_DIR fallback 失败:默认路径 不可写"

## 6. 部署

- 改 `launcher/env_bootstrap.py`（新增 `is_data_dir_stale` / `StaleDataDirFallbackError` / `_resolve_and_write`,改 `resolve_data_dir`）
- 不改 `launcher/main.py::bootstrap_env`（一行 logger.info 已够；resolve_data_dir 内部已 logger.warning）
- 重打 .app + 推送
- 用户的 `.app/.env` 字段不动；下次启动自动走 fallback

## 7. 风险

- **`resolve_data_dir` 失败静默 → 抛异常**:如果 `Path(raw).resolve()` 在 macOS 上触发循环 symlink 报错,会被 catch 后视为陈旧,走 fallback。fallback 默认路径也不可写则抛 `StaleDataDirFallbackError`,launcher 启动失败 + UI 报错卡。不会静默失败。
- **与 `.env` 拆分 spec 的交互**:用户 spec 完成后,`LAUNCHER_SYSTEM_KEYS` 仍含 `DATA_DIR`,本 spec 的 fallback 路径会被 launcher 同步到 `.app/.env` 的 `DATA_DIR` 字段(白名单 OK)。两条 spec 协同:拆分 spec 防用户配置覆盖;本 spec 防陈旧路径骗 launcher。
- **故意 fallback 行为可能被滥用**:用户故意 `.env` 写不存在的路径想做"占位",会被本 spec 直接覆盖。这是 spec §2.7 明确接受的取舍——避免 launcher 替用户决定"路径是否存在 = 想不想用"。
- **不备份陈旧值导致事后不可追溯**:如果 fallback 后用户想找回原 `.env` 的 `DATA_DIR=`,只能靠 git 历史(项目内 .env 是 .gitignore 不会入库)或自己手动备份恢复。这是 spec §2.8 明确接受的简化取舍——如需追溯能力后续可加 `.env.dataloss-backup`,但本 spec 不实现。
- **fallback 失败 = launcher 启动失败,数据访问完全阻塞**:用户必须从启动器日志文件里看到根因提示,手动修复(改 .env 的 DATA_DIR 字段为存在的路径)。比"静默走错路径"安全,但需要日志文件 (`data/logs/`) 能查;沿用 v0.7.0+9 时代 SECRET_KEY 异常的同等处理(异常退出 + 日志可查)。