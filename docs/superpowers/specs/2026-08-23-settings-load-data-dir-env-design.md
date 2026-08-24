# v0.7.0+7: backend Settings 同时读 cwd .env + DATA_DIR/.env

> 状态: 已写完待实施
> 关联: v0.7.0+6 commit 98c665e(DATA_DIR 转绝对路径)、status_server.py 改动 2 commit (双 .env 读取)

## 背景

用户反馈 v0.7.2(commit 98c665e)修复后仍有问题:
- 启动 .app,日志/celery/run 看起来"没了"
- LLM 配置(在 launcher UI 填过 MINIMAX_API_KEY)UI 上看不到
- 定时任务 API 500,前端列表为空

排查证据:

```
$ curl http://127.0.0.1:8001/api/v1/settings/system-config  # admin 登录后
{ "data": {
    "data_dir": "/Users/hanamaki_mac_mini/.xhs-info-crawl",
    "minimax_api_key": "",       ← 空!
    "minimax_base_url": "",      ← 空!
    "minimax_model": "",         ← 空!
    "chrome_user_data_dir": "/Users/hanamaki_mac_mini/.xhs-info-crawl/chrome-pool",
    ...
}}
```

但 `~/.xhs-info-crawl/.env` 里这些字段是有值的(MINIMAX_API_KEY=sk-cp-op_...)。
同时 `~/.xhs-info-crawl/app.db` 是 8/23 10:51 写过的(说明 backend 启动后 db 路径对,读到了 DATA_DIR)。

## 根因

3 层缺陷:

### 层 1: launcher 写 LLM 配置到 .app/.env,backend 子进程只读 cwd 下 .env

- `launcher/status_server.py` PUT `/settings/system-config` 已经做**双写**:
  - `project_root/.env`(即 `.app/.env`,作为兜底)
  - `DATA_DIR/.env`(即 `~/.xhs-info-crawl/.env`,作为用户配置主源,见 `_LAUNCHER_USER_FIELD_KEYS`)
- backend 子进程 cwd = `.app/Contents/Resources/xhs-info-crawl/`(见 process_manager.py:140)
- backend Settings `env_file=".env"`(见 app/core/config.py:11)是相对路径
- pydantic-settings 按 cwd 解析 → 找到 `.app/.env`
- `.app/.env` 是默认模板,**用户字段(MINIMAX_API_KEY 等)永远是空**
- **DATA_DIR/.env 永远没被 backend 读到**

所以 `chrome_user_data_dir` 是好的(因为 backend Settings 从 DATA_DIR 推导),LLM 配置永远是空(因为 launcher 双写到 DATA_DIR/.env,但 backend 不读)。

### 层 2: launcher 自己的 stdout/stderr 日志写到 .app/data/logs/

- `process_manager.py:39`: `self._logs_dir = project_root / "data" / "logs"`
- api.log / worker.log / beat.log / web.log 写到 `.app/data/logs/`
- 用户期望这些日志在 `~/.xhs-info-crawl/logs/`
- DATA_DIR 转绝对路径后,launcher 的日志**没跟着走**

### 层 3: /api/v1/tasks 500(独立 bug,本 spec 不修)

不在本次修复范围(等用户单独反馈)。

## 设计

### 修复 1: backend Settings 同时读 cwd .env + DATA_DIR/.env

让 `app/core/config.py::Settings` 改造为:
1. 先按 cwd 解析 `.env`(dev/launcher 共用路径)
2. 再按 `DATA_DIR`(从 cwd .env 解析出来的绝对路径)读 `<DATA_DIR>/.env`
3. **DATA_DIR/.env 的字段优先级 > cwd/.env**(用户在 DATA_DIR 配的覆盖默认)

实现方式:
- `pydantic_settings.BaseSettings` 支持 `env_file` 为单文件,**不直接支持多文件**
- 不能在 `model_config` 里塞两个文件路径
- 标准做法:在 Settings 子类里 override `settings_customise_sources`,在 `init_kwargs` 里把 cwd .env + DATA_DIR/.env 内容合并后塞进 `EnvSettingsSource` 之前

或者更简单(不依赖 pydantic 内部 API):
- 保留 `env_file=".env"` 不动
- 在 Settings 子类里加 `model_validator(mode="before")`,手动读 DATA_DIR/.env,把里面字段塞进 data dict

但 mode="before" 拿到的 data 已经被 pydantic 处理过;实际更稳的做法是用自定义 source:
```python
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

class _DataDirEnvSource(PydanticBaseSettingsSource):
    """读 <DATA_DIR>/.env,优先级高于 cwd .env。"""
    def __init__(self, settings_cls):
        super().__init__(settings_cls)
        from pathlib import Path
        # 用 cwd .env 先解析 DATA_DIR(bootstrap 模式)
        cwd_env = Path.cwd() / ".env"
        data_dir = None
        if cwd_env.exists():
            for line in cwd_env.read_text(encoding="utf-8").splitlines():
                if line.startswith("DATA_DIR="):
                    raw = line.split("=", 1)[1].strip()
                    if raw:
                        data_dir = Path(raw).expanduser().resolve()
                        break
        self._path = data_dir / ".env" if data_dir else None

    def get_field_value(self, field, field_name):
        if self._path is None or not self._path.exists():
            return None, None, False
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip().upper() == field_name.upper():
                return v.strip(), field_name, False
        return None, None, False

    def __call__(self) -> dict[str, Any]:
        if self._path is None or not self._path.exists():
            return {}
        result = {}
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            result[k.strip().upper()] = v.strip()
        return result

    def prepare_field_value(self, field, value, value_is_complex):
        return value
```

然后在 Settings 子类:
```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings,
    ):
        # DATA_DIR/.env 优先级高于 cwd/.env;env_settings 最高(进程环境覆盖一切)
        return (init_settings, env_settings, _DataDirEnvSource(settings_cls), dotenv_settings)
```

pydantic_settings 源码顺序: 靠**前**的 source 优先级**更高**。
所以 `(init_settings, env_settings, _DataDirEnvSource, dotenv_settings)` 意味着:
- 命令行 init 参数 > 进程 env > DATA_DIR/.env > cwd/.env > 文件 secret
- 这正好是想要的:用户在 DATA_DIR 配的 LLM 覆盖 .app/.env 里的空,进程环境(测试/CI)覆盖一切

### 修复 2: launcher stdout/stderr 日志走 DATA_DIR

`process_manager.py`:
- `__init__` 不再硬编码 `self._logs_dir = project_root / "data" / "logs"`
- 改为从 `.env` 读 `LOG_DIR`(`bootstrap_env` 已经写),fallback 才用 `project_root/data/logs`
- `bootstrap_env` 增加 `LOG_DIR` 写入:
  - 如果 .env 里 LOG_DIR 为空/缺失 → 写 `DATA_DIR/logs`(已经解析为绝对路径)
  - 已存在 → 调用 resolve_data_dir 同样的逻辑转绝对路径

### 修复 3(本 spec 不做): /api/v1/tasks 500

单独 TODO 排查。

## TDD

### `backend/tests/test_settings_load_data_dir_env.py`(新增)

7 个 case:

1. `test_cwd_env_only`: 仅有 cwd/.env,字段按 cwd 解析 ✅(回归)
2. `test_data_dir_env_only`: 仅有 DATA_DIR/.env,字段按 DATA_DIR 解析 ✅
3. `test_data_dir_overrides_cwd`: cwd/.env `MINIMAX_API_KEY=old`,DATA_DIR/.env `MINIMAX_API_KEY=new` → `settings.minimax_api_key == "new"`
4. `test_env_var_overrides_data_dir`: 进程 env `MINIMAX_API_KEY=runtime` > DATA_DIR/.env `MINIMAX_API_KEY=data` > cwd/.env `MINIMAX_API_KEY=cwd` → `settings.minimax_api_key == "runtime"`
5. `test_missing_data_dir`: cwd/.env 无 DATA_DIR → 不报错,_DataDirEnvSource 返回空 dict
6. `test_relative_data_dir_in_cwd_env`: cwd/.env `DATA_DIR=./data` → DATA_DIR/.env 不被读(因为 resolve 前相对路径不能确定;这个 case 让 settings 走 cwd/.env 自己的 fallback 路径)
7. `test_priority_chain_full`: 同时有 cwd/.env + DATA_DIR/.env + 进程 env,验证优先级链

### `launcher/tests/test_process_manager_logs_dir.py`(新增)

5 个 case:

1. `test_logs_dir_default_under_data_dir`: .env 无 LOG_DIR → `logs_dir == DATA_DIR/logs`
2. `test_logs_dir_from_env_absolute`: .env `LOG_DIR=/custom/logs` → 用 /custom/logs
3. `test_logs_dir_relative_resolved`: .env `LOG_DIR=./logs` → resolve 成 project_root/logs(避免重蹈 DATA_DIR 覆辙)
4. `test_logs_dir_created_on_startup`: 第一次启动时自动创建目录
5. `test_existing_logs_dir_preserved`: 已存在的目录不被覆盖

## 验收

- [ ] `pytest backend/tests/test_settings_load_data_dir_env.py` 7/7 全绿
- [ ] `pytest launcher/tests/test_process_manager_logs_dir.py` 5/5 全绿
- [ ] 旧测试不回归:`pytest backend/tests/ launcher/tests/` 全过
- [ ] 重打 .app,启动后:
  - `GET /api/v1/settings/system-config` `minimax_api_key` 返回真实值(不再是空)
  - `~/.xhs-info-crawl/logs/api.log` 有新启动日志
- [ ] commit + push + tag v0.7.3

## 关联教训

- 任何 launcher 启动 backend 子进程的场景,cwd 与 DATA_DIR 不一致时,backend 都不能只信 cwd 下 .env
- 进程组 / cwd / 配置文件路径必须从一而终走同一个绝对锚点
- "读 .env"和"写 .env"是两件事,不能因为 launcher 读两边就以为 backend 也读两边
