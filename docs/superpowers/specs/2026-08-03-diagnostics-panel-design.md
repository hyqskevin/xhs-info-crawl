# 仪表盘连接检测面板（opencli + 小红书号 + 浏览器池）

> 状态：待审核（按 TODO 持续授权，可自动进入开发）。

## 1. 背景与目标

仪表盘目前只有一张"后端服务"健康卡片（来自 `GET /health`）。用户在排障时常卡在三件事：

1. `opencli` 二进制不在 PATH（worker 重启后 nvm bin 找不到，2026-07-27 真实事故）；
2. 小红书账号未扫码登录（whoami 阻塞等扫码）；
3. Chrome/CDP 端点不可达或 sessions 异常（`user store was not found`、`stale page identity`）。

这三件事都发生在 worker/Chrome 端，无法从 `/health` 探测。后端 `POST /settings/opencli/test` 已能做 whoami 检测，但入口在 SettingsView，仪表盘看不到。

目标：在 Dashboard 新增「连接检测」卡片，含三个独立检测按钮与对应状态徽章，让用户在仪表盘一发即查。

> 注：小红书号池（多 XhsAccount）尚未建（见 TODO "多小红书账号配置 + 自动切换"），本 spec 中的"小红书池"指**当前共享 Chrome 会话**——只反映现有能力，不引入新模型。

## 2. 已确认的产品规则

1. 三个检测分别独立：opencli / xhs-login / xhs-pool，可单独触发，互不影响。
2. 进入仪表盘时**自动跑一次**三检测（一次 HTTP 请求：`GET /api/v1/diagnostics/snapshot` 聚合返回三段），不轮询，避免触发 opencli 调用风暴。
3. 用户手动点击任一按钮 → 单端点 GET → 局部刷新对应徽章。
4. 失败原因必须可读，含可执行指引（"opencli 不在 PATH，请设置 `OPENCLI_BIN`"等）。
5. 后端错误返回用 503/200 二分：
   - **503**：opencli 调用本身异常（bin 缺失、CDP 不可达、命令非 0 exit），属于环境问题；
   - **200**：业务态即使"未登录"也带 `logged_in=false` 等字段，前端按字段展示。
6. 三个端点都要 `Admin` 鉴权。
7. 检测不会触发实际抓取动作，仅做轻量探测。

## 3. 设计

### 3.1 数据契约

```python
# GET /api/v1/diagnostics/snapshot（聚合，返回单次入仪表盘）
{
  "opencli": {
    "ok": bool,
    "bin": str,            # 配置的 bin 名（默认 "opencli"）
    "resolved": str | None,# shutil.which 解析的绝对路径；None 表示找不到
    "reason": str | None,  # ok=false 时的可读原因
    "version": str | None, # `opencli --version` 输出；ok=true 时尝试填充
  },
  "xhs_login": {
    "logged_in": bool,
    "username": str | None,
    "user_id": str | None,
    "reason": str | None,  # logged_in=false 时分类原因：timeout / auth_required / other
  },
  "xhs_pool": {
    "cdp_endpoint": str,        # settings.opencli_cdp_endpoint
    "cdp_reachable": bool,
    "sessions": list[dict],     # `opencli browser list` JSON 解析结果；解析失败时为 []
    "reason": str | None,
  },
  "checked_at": str,            # ISO 8601 UTC
}
```

### 3.2 端点

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/v1/diagnostics/snapshot` | 三合一聚合（首次入页 + 手动"全部重测"） |
| GET | `/api/v1/diagnostics/opencli` | 单测 opencli 二进制 |
| GET | `/api/v1/diagnostics/xhs-login` | 单测 whoami（`OpenCLIAdapter.check_login()`） |
| GET | `/api/v1/diagnostics/xhs-pool` | 单测 CDP + sessions 列表 |

均需 `Admin` 鉴权。`/snapshot` 内部依次调用另三个单测函数，**任一单测失败不影响其他返回**（分别捕获异常）。

### 3.3 服务层

新文件 `backend/app/services/diagnostics.py`：

```python
from app.services.opencli_adapter import OpenCLIAdapter, AuthenticationRequired, OpenCLIError

def probe_opencli(settings) -> dict: ...
def probe_xhs_login(settings) -> dict: ...
def probe_xhs_pool(settings) -> dict: ...
def probe_snapshot(settings) -> dict: ...
```

- `probe_opencli`：用 `shutil.which(settings.opencli_bin)` 找路径；找不到 → `ok=false, reason="opencli 不在 PATH，请设置 OPENCLI_BIN 环境变量"`；找到 → 尝试 `opencli --version`（短超时 5s），exit 非 0 → `ok=false, reason=<stderr>`；OK → 填 `version`。
- `probe_xhs_login`：复用 `OpenCLIAdapter(settings).check_login()`。正常返回 dict → `logged_in=true` + 提取 `username`/`user_id`（whoami 返回结构里有）；捕获 `AuthenticationRequired` → `logged_in=false, reason="auth_required"`；捕获 `OpenCLITimeout` → `logged_in=false, reason="timeout"`；其他异常 → `logged_in=false, reason="other"`。
- `probe_xhs_pool`：拼 `settings.opencli_cdp_endpoint` 尝试 HTTP 探测（`GET http://{host}/json/version`，2s 超时，CDP 协议约定端点）；状态码 200 → `cdp_reachable=true`；其他 → `cdp_reachable=false, reason=...`；然后尝试 `opencli browser list --format json`，解析 sessions；任一步异常都隔离不影响整体。

### 3.4 路由

新文件 `backend/app/api/v1/diagnostics.py`，4 个路由 handler，FastAPI dependency `Admin`。注册到 `router.py`（保持 v1 命名空间）。OpenCLI 调用都包 try/except；opencli 二进制缺失时返回 503（带 `reason`），whoami 业务态 200。

### 3.5 前端

`DashboardView.vue` 新增 `<ElCard class="diagnostics-card">`：

```vue
<template>
  <ElCard shadow="never" class="diagnostics-card">
    <template #header><div class="card-title"><ElIcon><Connection /></ElIcon><strong>连接检测</strong></div></template>
    <div class="diagnostics-grid">
      <div class="diag-item">
        <span class="diag-label">opencli 二进制</span>
        <ElTag :type="diag.opencli.ok ? 'success' : 'danger'">
          {{ diag.opencli.ok ? `已就绪${diag.opencli.version ? ' v' + diag.opencli.version : ''}` : '缺失' }}
        </ElTag>
        <ElButton size="small" :loading="loading.opencli" @click="probe('opencli')">检测</ElButton>
        <p v-if="!diag.opencli.ok" class="diag-reason">{{ diag.opencli.reason }}</p>
      </div>
      <div class="diag-item">
        <span class="diag-label">小红书号登录</span>
        <ElTag :type="diag.xhs_login.logged_in ? 'success' : diag.xhs_login.reason === 'timeout' ? 'warning' : 'danger'">
          {{ diag.xhs_login.logged_in ? `已登录: ${diag.xhs_login.username || diag.xhs_login.user_id}` : diag.xhs_login.reason || '未登录' }}
        </ElTag>
        <ElButton size="small" :loading="loading.xhs_login" @click="probe('xhs_login')">检测</ElButton>
        <p v-if="diag.xhs_login.reason && !diag.xhs_login.logged_in" class="diag-reason">{{ reasonText(diag.xhs_login.reason) }}</p>
      </div>
      <div class="diag-item">
        <span class="diag-label">小红书池（Chrome）</span>
        <ElTag :type="diag.xhs_pool.cdp_reachable ? 'success' : 'danger'">
          {{ diag.xhs_pool.cdp_reachable ? `CDP 可达 · ${diag.xhs_pool.sessions.length} sessions` : 'CDP 不可达' }}
        </ElTag>
        <ElButton size="small" :loading="loading.xhs_pool" @click="probe('xhs_pool')">检测</ElButton>
        <p v-if="!diag.xhs_pool.cdp_reachable" class="diag-reason">{{ diag.xhs_pool.reason }}</p>
      </div>
    </div>
  </ElCard>
</template>
```

`onMounted` → `loadSnapshot()`（聚合）。三按钮单独调用对应单端点并更新 `diag` 对应字段。`reasonText` 把 `auth_required/timeout/other` 翻译成中文。

## 4. 验收

### 4.1 后端

新增 `backend/tests/test_diagnostics_api.py` 6 用例：

1. `test_snapshot_returns_three_sections`：mock 三个 probe 都返回 ok，断言 `/snapshot` 200 + 三段字段。
2. `test_opencli_probe_missing_bin_returns_503`：monkeypatch `shutil.which` 返回 None，断言 `/opencli` 503 + `reason` 含"OPENCLI_BIN"。
3. `test_xhs_login_probe_authentication_required_returns_200_logged_in_false`：monkeypatch `check_login` 抛 `AuthenticationRequired`，断言 `/xhs-login` 200 + `logged_in=false, reason="auth_required"`。
4. `test_xhs_login_probe_timeout_returns_200_logged_in_false`：monkeypatch `check_login` 抛 `OpenCLITimeout`，断言 200 + `reason="timeout"`。
5. `test_xhs_pool_probe_cdp_unreachable_returns_200_cdp_reachable_false`：monkeypatch `httpx` 或 raw HTTP 探测失败，断言 200 + `cdp_reachable=false, reason` 非空。
6. `test_snapshot_isolates_failures`：让 opencli probe 抛异常，断言 `/snapshot` 仍 200 且 opencli 段是错误占位、其它两段正常。

后端全量 `pytest -q` 全绿（基线 526 + 6 新 ≥ 532 passed）；前端 build 通过。

### 4.2 前端

`DashboardView.spec.ts` 加 4 用例：

1. "renders diagnostics card with three sections after snapshot loads"：mock `api.diagnosticsSnapshot` 返回 ok 数据，断言三段渲染对应徽章文字。
2. "single probe button updates only that section"：mock `api.opencliProbe` 单独，断言只更新 opencli 字段，其他两段不变。
3. "shows failure reason text when ok=false"：mock snapshot 让 opencli `ok=false reason="..."`，断言渲染 reason 文案。
4. "loading state disables button during probe"：用 vi.fn 延迟 resolve，断言按钮 `:loading=true`。

### 4.3 API 文档

`docs/api-doc.md` 加 4 个新端点：`GET /api/v1/diagnostics/{snapshot,opencli,xhs-login,xhs-pool}`，含入参/出参/状态码。

## 5. 部署

改动 `app/api/v1/*.py`（新增文件并注册路由）与 `app/services/diagnostics.py`（新文件）。这些都跑在 uvicorn 进程，不需要重启 celery worker/beat。uvicorn `--reload` 自动加载新模块。

但用户在 Dashboard 点按钮后仍可能因 worker 持旧代码出现偏差——本 spec 不涉及 worker 侧改动，无需 worker/beat 重启。

## 6. 回滚

删除新文件 `app/api/v1/diagnostics.py`、`app/services/diagnostics.py`，从 `router.py` 移除 import。前端 DashboardView 删除 diagnostics card 块。无迁移、无 schema 变更。