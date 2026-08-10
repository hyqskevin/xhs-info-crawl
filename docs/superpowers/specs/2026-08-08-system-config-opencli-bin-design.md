# 系统配置页接入 OPENCLI_BIN — 设计

**日期**: 2026-08-08
**关联 TODO**: 用户反馈 `opencli 不在 PATH，请设置 OPENCLI_BIN 环境变量指向 /Users/kevin_w/.nvm/versions/node/v22.18.0/bin/opencli`，
但当前只能在 `.env` 里改（需要 SSH 到服务器、编辑、重启服务），期望在配置中心可视化填写自定义路径。
**依赖基线**: 2026-08-03 已实现 `GET/PUT /settings/system-config` 端点 + SettingsView 「系统配置」tab，覆盖 17 项 env 配置；
本规格仅补 OPENCLI_BIN 一项，不动其他字段。

## 1. 问题

- `OPENCLI_BIN` 是 worker 抓取流程的 opencli 二进制路径（[opencli_adapter.py](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/backend/app/services/opencli_adapter.py) 启动时读入 `self._bin`）；
- 当前仅 `.env` 可改，重启后才能让 `Settings.opencli_bin` 重新加载；UI 完全无入口；
- 用户在面板外修改 `.env` 容易改错（注释、空行、key 拼写），且不便分发到生产/测试环境；
- 现行 `system-config` 端点（17 项）刚好缺这一项——补齐即可复用现有 UI / 持久化路径（写 `.env` + 缓存清理），无需新增端点。

## 2. 设计

### 2.1 后端（[backend/app/api/v1/settings.py](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/backend/app/api/v1/settings.py)）

- `_ENV_KEY_MAP` 增加 `"opencli_bin": "OPENCLI_BIN"`；
- `SystemConfigIn` 增加 `opencli_bin: str | None = None`；
- `_update_env_file` 已支持任意 key，无需改动；
- `update_system_config` 自动复用同一逻辑：传值即写入 .env 并清缓存，
  未传（None）则不动 `.env` 中现有值（向后兼容）；
- 空字符串（`""`）表示用户主动清除，回退到 `Settings` 默认值 `opencli`（PATH 解析）；
- GET 自动包含新字段（`_read_system_config` 按 `_ENV_KEY_MAP` 遍历）。

### 2.2 前端（[frontend/src/views/SettingsView.vue](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/frontend/src/views/SettingsView.vue)）

- 「系统配置」tab 在「抓取数量」分组之上插入新的 **「抓取工具」** 分组，
  保留语义独立（未来可扩展 `OPENCLI_CDP_ENDPOINT` / `PADDLEOCR_MODEL_DIR` 等工具路径）；
- 单字段 `ElInput`：`v-model="systemConfig.opencli_bin"`，`placeholder="/path/to/opencli"`，
  右侧 `append` 加 ElTooltip「支持绝对路径，留空回退 PATH 解析」；
- `loadSystemConfig` / `saveSystemConfig` 已走泛型 `Record<string, any>`，无需改；
- 顶部 hint 文案「修改后需重启服务生效」继续适用（worker/beat 不自动重载）。

### 2.3 不变项

- `Settings.opencli_bin` 默认值 `"opencli"`、`opencli_adapter.py` 的 `self._bin` 装配、`find_opencli` 预检、
  diagnostics 三段检测：全部沿用，无需改动；
- 已有 `test_opencli_bin.py` / `test_diagnostics_api.py` 不回归。

## 3. TDD 计划（先红后绿）

### 3.1 后端

`backend/tests/test_system_config_api.py` 新增 1 用例：

- `test_update_system_config_writes_opencli_bin`：
  - PUT `{opencli_bin: "/custom/path/opencli"}` → 200；
  - 重新 GET → `data.opencli_bin == "/custom/path/opencli"`；
  - 临时 .env 文件中 `OPENCLI_BIN=/custom/path/opencli` 行确实被写入；
  - 既有 17 项 + opencli_bin 共 18 项字段全部出现。

### 3.2 前端

`frontend/src/views/SettingsView.spec.ts` 新增 1 用例：

- `system-config tab 渲染 opencli_bin 输入框并随保存回传`：
  - 切到 system-config tab，输入 `/Users/kevin_w/.nvm/versions/node/v22.18.0/bin/opencli`；
  - 点保存 → mock `api.updateSystemConfig` 收到的 payload 包含该字段；
  - 重新 load 后 input 显示新值。

## 4. 验收

- 后端 `tests/test_system_config_api.py` 新用例先红后绿；
- 后端全量测试绿（基线 544 passed, 1 skipped → +1 新用例）；
- 前端 `SettingsView.spec.ts` 新用例先红后绿，前端全量测试绿，build 通过；
- 实操：
  1. 登录 admin → 配置中心 → 系统配置 → 抓取工具；
  2. 输入 `/Users/kevin_w/.nvm/versions/node/v22.18.0/bin/opencli` → 保存；
  3. 检查 `data/logs/uvicorn.log` reload 成功 + `.env` 中 `OPENCLI_BIN=` 行更新；
  4. 重启 worker/beat（spec 部署要求）→ 仪表盘系统状态卡 opencli 探测显示「✓」。

## 5. 部署

- `app/api/v1/settings.py` 改动 → uvicorn `--reload` 自动加载；
- **worker / beat 必须重启**才能让新 `OPENCLI_BIN` 在抓取流程生效（已有 [AGENTS.md](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/AGENTS.md) 约定）；
- 前端 Vite HMR 自动刷新，无需手动操作。

## 6. 非目标

- 不做 opencli 路径合法性校验（保存时仅做非空 / 字符串检查，由 diagnostics 卡 + worker 预检兜底）；
- 不做"自动检测系统 opencli 路径"功能（用户已经在外部 nvm 装好，自己填更准）；
- 不在 UI 上加 opencli 测试按钮（仪表盘系统状态已有同源检测）。