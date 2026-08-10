# dev-*.sh 不再 source 全部 .env — 设计

**日期**: 2026-08-10
**关联**: 用户反馈"配置中心改 OPENCLI_BIN 后又回去了"

## 1. 问题

`scripts/dev-api.sh` / `dev-worker.sh` / `dev-beat.sh` 三个脚本都有：

```bash
set -a
source "$ROOT_DIR/.env"
set +a
```

`set -a` 让 `source .env` 把所有 KEY=VALUE 自动 export 到 `os.environ`。

pydantic_settings 优先级：`os.environ > .env 文件`。

这导致：

1. uvicorn/worker/beat 启动时，`.env` 的值被注入 `os.environ`
2. 用户通过配置中心 PUT `/settings/system-config` 改 `.env` 文件 → `update_system_config` 同步 `os.environ` + 清 `lru_cache` → 临时生效
3. uvicorn `--reload` 检测到代码变化 → 重启子进程 → 新子进程从父进程继承 **旧** `os.environ`（父进程启动后 `.env` 改了，但父进程 `os.environ` 不会更新）
4. 新子进程 `Settings()` 优先读 `os.environ` 旧值 → "又回去了"

**实测证据**（2026-08-10）：
- uvicorn 进程（PID 67617）`os.environ["OPENCLI_BIN"]` = `/Users/kevin_w/.nvm/...`（旧值）
- `.env` 文件 `OPENCLI_BIN` = `/Users/hanamaki_mac_mini/.local/bin/opencli`（新值）
- pydantic_settings 读到旧值 → 仪表盘报"opencli 不在 PATH"

## 2. 设计

### 2.1 核心改动

三个 dev 脚本不再 `source .env`，改为只从 `.env` 读取脚本启动参数（`API_HOST`/`API_PORT`/`CELERY_*`），其余配置项由 pydantic_settings 直接读 `.env` 文件。

### 2.2 改动后的 dev-api.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# 只读取启动脚本需要的变量，不 source 全部 .env
# 其余配置由 pydantic_settings 直接读 .env 文件
# 这样配置中心改 .env 后，清 lru_cache 即可生效，不受 os.environ 旧值干扰
API_HOST="$(grep -E '^API_HOST=' .env 2>/dev/null | head -1 | cut -d= -f2- || true)"
API_PORT="$(grep -E '^API_PORT=' .env 2>/dev/null | head -1 | cut -d= -f2- || true)"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"

exec uv run --project backend uvicorn app.main:app \
  --app-dir backend \
  --host "$API_HOST" \
  --port "$API_PORT" \
  --reload
```

### 2.3 改动后的 dev-worker.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

POOL="$(grep -E '^CELERY_WORKER_POOL=' .env 2>/dev/null | head -1 | cut -d= -f2- || true)"
CONCURRENCY="$(grep -E '^CELERY_WORKER_CONCURRENCY=' .env 2>/dev/null | head -1 | cut -d= -f2- || true)"
LOG_LEVEL="$(grep -E '^CELERY_LOG_LEVEL=' .env 2>/dev/null | head -1 | cut -d= -f2- || true)"
POOL="${POOL:-solo}"
CONCURRENCY="${CONCURRENCY:-1}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

exec uv run --project backend celery \
  -A app.tasks.celery_app:celery_app worker \
  --pool="$POOL" \
  --concurrency="$CONCURRENCY" \
  --loglevel="$LOG_LEVEL"
```

### 2.4 改动后的 dev-beat.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

LOG_LEVEL="$(grep -E '^CELERY_LOG_LEVEL=' .env 2>/dev/null | head -1 | cut -d= -f2- || true)"
CELERY_FOLDER="$(grep -E '^CELERY_FOLDER=' .env 2>/dev/null | head -1 | cut -d= -f2- || true)"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
CELERY_FOLDER="${CELERY_FOLDER:-./data/celery}"

exec uv run --project backend celery \
  -A app.tasks.celery_app:celery_app beat \
  --loglevel="$LOG_LEVEL" \
  --schedule "$CELERY_FOLDER/celerybeat-schedule"
```

## 3. 为什么这样改

| 方面 | 改前 | 改后 |
|---|---|---|
| `.env` 注入 os.environ | 全量 source | 不注入 |
| pydantic_settings 读取 | os.environ 优先（旧值覆盖 .env 新值） | 直接读 .env 文件 |
| 配置中心改 .env 后 | 需同步 os.environ + 清 lru_cache，reload 后失效 | 清 lru_cache 即生效，reload 后仍生效 |
| 启动参数来源 | source .env 的变量 | grep .env 的特定变量 + 默认值 |

## 4. 影响范围

- **uvicorn**：配置中心改 .env 后，uvicorn --reload 重启子进程能读到 .env 新值
- **worker/beat**：不自动 reload，改 .env 后仍需手动重启。但重启后读 .env 新值（不再被 os.environ 旧值干扰）
- `update_system_config` 的 `os.environ` 同步逻辑保留（让 API 层立即生效，不依赖 reload）

## 5. 验收

- [ ] 三个 dev-*.sh 脚本不再 `set -a; source .env; set +a`
- [ ] 重启 uvicorn 后，`/api/v1/diagnostics/opencli` 返回正确的 opencli 路径
- [ ] 配置中心改 OPENCLI_BIN → 仪表盘立即生效
- [ ] 改代码触发 uvicorn reload → Settings 读到 .env 新值（不回退）
- [ ] 后端全量测试通过
- [ ] worker/beat 重启后正常运行

## 6. 测试计划

- **单元测试**：新增 `test_get_settings_reads_env_file_not_os_environ`，验证当 os.environ 没有 OPENCLI_BIN 时，Settings 从 .env 文件读到正确值
- **手动验证**：重启进程 → 改 .env → 触发 reload → 确认 Settings 读到新值
