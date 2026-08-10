# diagnostics xhs_pool 探测适配 opencli daemon/cdp 双模式 — 设计 (v2 版本驱动)

**日期**: 2026-08-10
**版本**: v2（版本驱动 + 能力兜底，替代 v1 能力探测方案）
**关联**: 用户反馈 opencli v1.8.5 用 daemon+扩展模式连浏览器,不再需要 CDP 9222 端口;
且不同 opencli 版本连接模式不同,应先检测版本再按版本路由到对应检测方式。

## 1. 问题

opencli 有两种连接浏览器的模式:

| 模式 | opencli 版本 | Chrome 要求 | 检测方法 |
|---|---|---|---|
| **CDP 模式** | <v1.8.5 | `--remote-debugging-port=9222` | `socket.connect(9222)` |
| **daemon 模式** | ≥v1.8.5 | 普通 Chrome + 扩展 | `opencli daemon status` |

当前 `probe_xhs_pool` 硬编码 CDP 检测,对 daemon 模式的 opencli 永远报失败,
误导用户以为连接有问题。实际 `OpenCLIAdapter` 抓取正常(它不依赖 CDP)。

### v1 方案为何被推翻

v1 用"先试 daemon,失败回退 CDP"的能力探测。问题:
- 正常路径需要先试 daemon(可能超时 5s)才能确定模式,慢
- 无法在返回结果中展示 opencli 版本信息
- 用户明确要求"检测不同版本,再分别调用不同的链接检测"

## 2. 设计:版本驱动 + 能力兜底

```
probe_xhs_pool(settings):
  1. 解析 opencli 路径(shutil.which)
     - 找不到 → mode="unknown", reason="opencli 不在 PATH"
  2. 获取版本(_safe_version → _parse_opencli_version)
     - 解析成功(version_tuple 非 None):
       a. version >= (1,8,5) → _probe_daemon, mode="daemon"
       b. version < (1,8,5)  → _probe_cdp,    mode="cdp"
     - 解析失败(version_tuple 为 None)→ 能力探测兜底:
       a. _probe_daemon 成功 → mode="daemon"
       b. _probe_daemon 失败 → _probe_cdp → mode="cdp" 或 "unknown"
  3. 返回结果包含 mode + version + version_tuple
```

### 2.1 版本阈值常量

```python
DAEMON_MODE_MIN_VERSION: tuple[int, int, int] = (1, 8, 5)
```

≥此版本走 daemon 检测;<此版本走 CDP 检测。阈值变更只需改此常量。

### 2.2 版本解析 `_parse_opencli_version`

```python
def _parse_opencli_version(text: str) -> tuple[int, int, int] | None:
    """从 `opencli --version` 输出提取语义化版本。

    支持格式:
      - "v1.8.5"
      - "1.8.5"
      - "opencli v1.8.5"
      - "opencli version 1.8.5"
      - "1.8.5\n..." (首行首个 semver)

    返回 (major, minor, patch) 或 None(无法解析)。
    """
```

用正则 `r"(\d+)\.(\d+)\.(\d+)"` 提取首个匹配,转为 int 元组。

### 2.3 daemon 探测 `_probe_daemon` + `_parse_daemon_status`

`_probe_daemon(bin_path)` 运行 `opencli daemon status`(5s 超时),返回 `{success, output}`。

`_parse_daemon_status(text)` 解析输出:

实际输出示例:
```
Daemon: running (PID 1152)
Version: v1.8.5
Uptime: 62h 40m
Extension: connected (v1.0.22)
Profiles: jjm94buu v1.0.22
Memory: 20 MB
Port: 19825
```

解析规则:
- `Daemon: running` → `daemon_running=True`
- `Daemon: stopped` / `Daemon: not running` → `daemon_running=False`
- `Extension: connected` → `extension_connected=True`
- `Extension: disconnected` / 无此行 → `extension_connected=False`
- `Profiles: jjm94buu v1.0.22` → `profiles=["jjm94buu"]`(取首个 token)
- `Port: 19825` → `daemon_port=19825`

### 2.4 返回结构

```python
{
    "mode": "daemon" | "cdp" | "unknown",
    "version": str | None,           # 原始版本字符串(如 "v1.8.5")
    "version_tuple": list[int] | None,  # 解析后版本(如 [1,8,5]),JSON 友好
    # daemon 模式字段
    "daemon_running": bool | None,
    "extension_connected": bool | None,
    "profiles": list[str],
    "daemon_port": int | None,
    # CDP 模式字段(保留,向后兼容)
    "cdp_endpoint": str | None,
    "cdp_reachable": bool | None,
    "sessions": list,
    # 通用
    "reason": str | None,
}
```

`cdp_reachable` 在 daemon 模式下设为 `None`(未知),不报红/绿。
前端根据 `mode` 决定展示哪组字段。

### 2.5 健康判断

- **daemon 模式**: `ok = daemon_running and extension_connected and len(profiles) > 0`
- **cdp 模式**: `ok = cdp_reachable`
- **unknown 模式**: `ok = False`,reason 说明原因

## 3. 变更点

### 3.1 后端 [diagnostics.py](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/backend/app/services/diagnostics.py)

- 新增常量 `DAEMON_MODE_MIN_VERSION = (1, 8, 5)`
- 新增 `_parse_opencli_version(text: str) -> tuple[int, int, int] | None`
- 新增 `_parse_daemon_status(text: str) -> dict`
- 新增 `_probe_daemon(bin_path: str) -> dict`(运行 `opencli daemon status`)
- 重写 `probe_xhs_pool`:版本驱动路由 + 能力兜底
- 保留 `_probe_cdp` / `_cdp_host_port` / `_safe_version` 不动

### 3.2 前端 [DashboardView.vue](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/frontend/src/views/DashboardView.vue)

- `xhs_pool` 初始值增加 `mode/version/version_tuple` 等新字段
- `xhsPoolTag` computed:
  - `mode=="daemon"`: `daemon_running && extension_connected` → success "Daemon 已连接 · N profiles";否则 danger + reason
  - `mode=="cdp"`: 现有逻辑 `cdp_reachable`
  - `mode=="unknown"`: danger + reason
- 模板 "Chrome 浏览器" 行的标签改为 "浏览器连接"(daemon 模式不限于 Chrome)
- 可选:展示 opencli 版本号(若 `version` 非空)
- 错误处理 probe catch 中增加 `mode` 字段

### 3.3 测试

**后端** `test_diagnostics_api.py` 新增/调整:
- `test_parse_opencli_version_formats`: 多种格式(`v1.8.5`/`1.8.5`/`opencli v1.8.5`/无效)解析
- `test_parse_daemon_status_healthy`: 正常 daemon status 输出解析
- `test_parse_daemon_status_extension_disconnected`: 扩展断开解析
- `test_xhs_pool_daemon_mode_healthy`: 版本≥1.8.5 → daemon 检测 → mode="daemon"
- `test_xhs_pool_cdp_mode_old_version`: 版本<1.8.5 → cdp 检测 → mode="cdp"
- `test_xhs_pool_fallback_when_version_unparseable`: 版本解析失败 → 能力探测兜底 → daemon 成功
- `test_xhs_pool_fallback_to_cdp`: 版本解析失败 + daemon 失败 → cdp
- 既有 `test_xhs_pool_probe_cdp_unreachable` / `test_snapshot_*` mock 返回值增加 `mode/version` 字段

**前端** `DashboardView.spec.ts`:
- mock `diagnosticsXhsPool` 增加 `mode` 字段
- 新增用例:daemon 模式下展示 "Daemon 已连接" tag

## 4. 验收

- 后端全量测试绿(基线 + 新增用例)
- 前端全量测试绿,build 通过
- 实际 `/diagnostics/snapshot` 端点:
  - opencli v1.8.5 环境 → `mode="daemon"`, `version="v1.8.5"`, `version_tuple=[1,8,5]`, `daemon_running=true`, `extension_connected=true`, `profiles=["jjm94buu"]`
  - opencli 旧版环境 → `mode="cdp"`, `cdp_reachable=true`
- 仪表盘 "浏览器连接" 行:daemon 模式显示绿色 "Daemon 已连接 · 1 profiles"

## 5. 非目标

- 不改 `OpenCLIAdapter`(抓取逻辑不依赖 CDP,无需动)
- 不改 `OPENCLI_CDP_ENDPOINT` 配置(CDP 模式仍需要)
- 不删除 `_probe_cdp`(旧版 opencli 用户的回退路径)
- 不做 opencli 自动升级/安装
- 版本阈值硬编码为常量,不做配置化(YAGNI)
