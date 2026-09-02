# Settings .env 加载优先级修复

## 目标

修复 `backend/app/core/config.py` 中 Settings 配置源优先级，使 **项目根目录 `.env`（cwd/.env）优先级高于 `DATA_DIR/.env`**。

当前行为：
- `_DataDirEnvSource` 优先级高于 `dotenv_settings`（cwd/.env）
- dev 模式下，`data/.env` 中 `MINIMAX_API_KEY=` 等空值覆盖了项目根 `.env` 里的真实配置
- 导致 API `GET /settings/system-config` 返回 `minimax_api_key_set: False`

期望行为：
- cwd/.env > DATA_DIR/.env（与其他 dotenv 文件源语义一致：更靠近项目的文件优先级更高）
- 进程 env 仍高于一切（测试/CI 覆盖能力保留）
- .app 打包场景：`.app/.env` 系统 key 优先，用户配置 key 仍可从 `DATA_DIR/.env` 读取

## 根因

`settings_customise_sources` 返回顺序中 `_DataDirEnvSource` 排在 `dotenv_settings` 之前：

```python
return (
    init_settings,
    env_settings,
    _DataDirEnvSource(settings_cls),  # data/.env
    dotenv_settings,                 # cwd/.env
    file_secret_settings,
)
```

pydantic_settings 的 `deep_update` 是"先处理的 source 获胜"，所以 `data/.env` 覆盖了 `cwd/.env`。

## 设计

1. 调整优先级顺序为：
   ```
   init_settings > env_settings > dotenv_settings(cwd/.env) > _DataDirEnvSource(data/.env) > file_secret_settings
   ```

2. 同步更新 `_DataDirEnvSource` 的 docstring，说明它是 **fallback / 补充源**，不是覆盖源。

3. 更新 `test_settings_load_data_dir_env.py`：
   - `test_data_dir_overrides_cwd` 改为 `test_cwd_overrides_data_dir`（语义反转）
   - 保留 `test_data_dir_env_only`（cwd 缺省时 fallback 到 DATA_DIR）
   - 保留 `test_env_var_overrides_data_dir`（进程 env 最高）
   - 保留 `test_priority_chain_full`（调整断言）

4. 新增测试明确语义：
   - `test_cwd_env_overrides_data_dir_env`：cwd/.env 有值时胜出
   - `test_data_dir_env_fallback_when_cwd_missing`：cwd/.env 缺字段时 fallback

## 验收

- [ ] TDD：新增/调整测试先失败（红）后通过（绿）
- [ ] `backend/tests/test_settings_load_data_dir_env.py` 全绿
- [ ] 后端全量 pytest 无新增失败
- [ ] dev 模式 API `GET /settings/system-config` 返回 `minimax_api_key_set: True`（使用项目根 `.env` 真实 key）
- [ ] 记录 dev/生产 db 路径差异：dev=`data/app.db`，生产=`~/Library/Application Support/com.xhs-info-crawl.local/data/app.db`

## 非范围

- 不改动 `data/.env` 生成逻辑（launcher 负责）
- 不改动 DATA_DIR 解析逻辑
- 不改动其他配置项默认值

## 部署

- API 层（uvicorn）必须重启
- worker/beat 不需重启（本次只改配置加载，不涉及 task/service 代码）
