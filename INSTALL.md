# Install & Run xhs-info-crawl（开发者安装指南）

> 当前发版：**v0.6.0**。
>
> 终端用户请看 [README-USER.md](README-USER.md)。

This document describes how to bring up the project on a fresh Linux/macOS machine for **development / local use**. For production-grade deployment with Docker, see [docs/superpowers/specs/2026-07-21-deployment-design.md](docs/superpowers/specs/2026-07-21-deployment-design.md) (stage two TODO).

---

## 目录

1. [系统要求](#1-系统要求)
2. [克隆仓库](#2-克隆仓库)
3. [后端（FastAPI + Celery + SQLite）](#3-后端fastapi--celery--sqlite)
4. [前端（Vue 3 + Vite）](#4-前端vue-3--vite)
5. [打包版桌面启动器（可选）](#5-打包版桌面启动器可选)
6. [首次使用](#6-首次使用)
7. [测试（提交前必跑）](#7-测试提交前必跑)
8. [进程管理与重启](#8-进程管理与重启)
9. [常见问题排查](#9-常见问题排查)
10. [下一步](#10-下一步)
11. [打包版（终端用户）](#11-打包版终端用户)

---

## 1. 系统要求

| 工具 | 版本 | 用途 |
|---|---|---|
| Python | ≥ 3.11 | 后端 |
| Node.js | ≥ 18 LTS（推荐 22） | 前端 |
| npm | Node 自带 | 前端 |
| Git | 任意 | 源码 |
| macOS / Linux | — | 宿主 |
| OpenCLI | latest | xhs 爬虫 |
| Chrome | 任意最新 | xhs 登录 / opencli |
| `uv` | latest | Python 包管理（推荐） |
| （可选）Make | 任意 | 顶层快捷命令 |

> **Windows 用户**：安装 WSL2，在 WSL 内按 Linux 步骤走。

---

## 2. 克隆仓库

```bash
git clone https://github.com/hyqskevin/xhs-info-crawl.git
cd xhs-info-crawl

# 推荐切到最新的稳定 tag
git fetch --tags
git checkout v0.6.0    # 或 main 分支
```

---

## 3. 后端（FastAPI + Celery + SQLite）

### 3.1 安装依赖

用 `uv`（推荐）或 `pip`：

```bash
cd backend
uv sync                       # 等价于 pip install -e ".[dev]"
# 或者：
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[ocr]"       # ocr extra 安装 paddleocr / paddlepaddle
```

### 3.2 初始化数据库

```bash
# 可选：覆盖默认 admin 密码（生产环境必须改）
export INITIAL_ADMIN_PASSWORD="ChangeMe123!"

# 应用所有迁移（包含 seed admin）
uv run alembic upgrade head    # 或 alembic upgrade head
```

迁移 `0012_seed_admin` 在 upgrade 时若 `users` 表为空则插入 `admin` 用户；密码来自 `INITIAL_ADMIN_PASSWORD`，未设置则用 `Admin@123` 且 WARNING 提示"生产环境必须更改"。脚本**幂等**：若 admin 已存在则跳过。

### 3.3 环境变量（可选项）

完整列表见 `.env.example`。常用项：

| 变量 | 默认值 | 作用 |
|---|---|---|
| `XHS_BACKEND_HOST` | `0.0.0.0` | uvicorn 绑定地址 |
| `XHS_BACKEND_PORT` | `8000` | uvicorn 端口 |
| `INITIAL_ADMIN_PASSWORD` | `Admin@123` | seed admin 密码（生产必须覆盖） |
| `OPENCLI_BROWSER_COMMAND_TIMEOUT` | `120` | 秒 |
| `CELERY_BROKER_URL` | `filesystem:///abs/path/celery_broker` | 阶段一 filesystem broker |
| `CELERY_RESULT_BACKEND` | `filesystem:///abs/path/celery_results` | 阶段一 |
| `PADDLE_PDX_CACHE_HOME` | `./data/paddlex` | PaddleOCR 缓存（必须落在项目内！） |
| `HF_HOME` | `./data/huggingface` | huggingface_hub 缓存（同上） |

> **重要**：所有写操作（缓存、临时文件、日志、数据库）必须落在项目根目录内。`backend/tests/test_project_internal_writes.py` 会静态扫描确保没有 `/tmp`、`~` 等硬编码外泄路径。新增服务代码后跑该测试。

### 3.4 启动后端三件套

开**三个**终端（每个跑一条）：

```bash
# 终端 1 — API
cd backend && source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 终端 2 — Celery worker
cd backend && source .venv/bin/activate
celery -A app.tasks.crawl_task worker --loglevel=info --concurrency=1

# 终端 3 — Celery beat（定时调度）
cd backend && source .venv/bin/activate
celery -A app.tasks.crawl_task beat --loglevel=info
```

> **注意**：终端 1 的 `uvicorn --reload` 会自动重载 API 层代码；但 **Celery worker / beat 不会自动重载**。详见[§8 进程管理与重启](#8-进程管理与重启)。

或者用顶层 Makefile（每个 `make dev-*` 在独立终端跑）：

```bash
make dev-api       # → http://127.0.0.1:8000
make dev-worker
make dev-beat
```

---

## 4. 前端（Vue 3 + Vite）

### 4.1 安装依赖

```bash
cd frontend
npm ci         # 推荐用 npm ci 装确定版本；或 npm install
```

### 4.2 启动 dev server

```bash
npm run dev    # → http://localhost:5173（含 /api 反代到 8000）
```

或者：

```bash
make dev-web
```

### 4.3 生产构建

```bash
npm run build       # 输出到 frontend/dist/，由 FastAPI 直接挂载
npm run preview     # → http://localhost:4173
```

### 4.4 API 地址配置

- **开发模式**：默认 `http://localhost:8000`（vite proxy 转发）
- **打包版**：`launcher/env_bootstrap.py` 启动时通过 `window.__APP_CONFIG__.apiBaseUrl` 注入运行时配置

---

## 5. 打包版桌面启动器（可选）

如果你想**直接试运行** v0.6.0 的桌面端（PyWebView 窗口 + 三服务一键启停），无需手动跑上面 4 个终端：

```bash
# 一次性构建 launcher UI + 后端依赖
cd launcher/ui && npm install && npm run build
cd ../..

# 启 launcher 主线程（会自动拉起后端 + worker + beat + 打开窗口）
cd launcher
python -m launcher
```

launcher 默认会自动：

- 探测空闲 API 端口（8001-8020）
- 探测空闲前端端口（5173-5199）
- 探测空闲状态服务端口（9000-9020）
- 探测空闲 opencli daemon 端口
- 在窗口里显示三服务状态卡 + OpenCLI 检测 + OCR 安装

详见 [README-USER.md](README-USER.md) §4-§7。

---

## 6. 首次使用

1. 浏览器打开 <http://localhost:5173>（dev）或 launcher 窗口里的"打开网页"
2. 用 `admin` / `Admin@123` 登录（或你在 `.env` 里设置的密码）
3. 进入"**配置中心**"：
   - 新建一条城市（如"宁波"）
   - 新建 2-3 个关键词（如"市集"、"展览"）
   - 加几个博主（手动加或 Excel 批量导入）
4. 进入"**仪表盘**"，底部表单选好城市 + 关键词 + 博主，发起抓取
5. 抓取过程中**确保 Chrome 已登录小红书**（<https://www.xiaohongshu.com>）
6. 抓完后到"**活动管理**"审核，到"**周报管理**"生成周报

### 6.1 配置中心页面示例

![配置中心](assets/screenshots/08-settings.png)

---

## 7. 测试（提交前必跑）

### 7.1 后端测试

```bash
cd backend
uv run pytest -q
# 或：
pytest -q
```

应看到 ≥ 800 passed。具体用例数随版本变动。

### 7.2 前端测试

```bash
cd frontend
npm run test -- --run        # Vitest 单元测试
npm run build                # vue-tsc + vite build（也包含类型检查）
```

### 7.3 E2E（Playwright）

```bash
cd frontend
npm run test:e2e             # 完整 e2e
# 或只跑某个用例
npx playwright test login.spec.ts
```

### 7.4 静态扫描（项目内写操作合规）

```bash
cd backend
uv run pytest tests/test_project_internal_writes.py -q
```

确保所有写操作（缓存 / 临时文件 / 日志 / DB）都落在项目根目录内。

### 7.5 一键全量

```bash
make test
```

---

## 8. 进程管理与重启

**核心规则**：

| 改了什么 | 需要重启吗 |
|---|---|
| `app/api/v1/*.py`（API 层） | ❌ uvicorn `--reload` 已生效 |
| `app/schemas/*.py`（pydantic schema） | ❌ uvicorn 已生效 |
| `app/models/*.py`（ORM 模型） + 新迁移 | ✅ **必须手动重启 worker** |
| `app/services/*.py`（依赖 SQL 的服务） | ✅ **必须重启 worker** |
| `app/tasks/*.py`（Celery 任务） | ✅ **必须重启 worker + beat** |
| `migrations/versions/*.py`（新迁移） | ✅ alembic upgrade + 重启 worker |
| 前端 `src/**/*` | ❌ Vite HMR 自动刷新 |

**为什么**：Celery worker / beat 不会自动重载。worker 拿着旧的 ORM 模型访问新 schema 会触发 `no such column`、`OperationalError`，并把 traceback 写到 `error_message` 字段——前端看到的"任务报错"。

**重启 worker / beat 的两种方式**：

```bash
# 1. 终端里 Ctrl+C 终止后再起
celery -A app.tasks.crawl_task worker --loglevel=info --concurrency=1

# 2. 如果是 launcher 启的，关掉启动器窗口 → 重启启动器
```

**凡是涉及模型 / 迁移 / schema 的 TODO，验收项必须包含"重启 worker"**。

---

## 9. 常见问题排查

| 症状 | 修复 |
|---|---|
| `ModuleNotFoundError: app.xxx` | 确认在 `backend/` 下，venv 已激活 |
| Celery task 一直不执行 | 检查 broker 目录可写；检查 `celery beat` 也起来了 |
| OpenCLI 错误 `Missing url` | 部分博主需要补 `profile_url`：在"配置中心"点"补充博主信息" |
| 前端连不上后端 | 确认 CORS / `VITE_API_BASE` / vite proxy 配置 |
| worker 报 `no such column` | 你改了 model 或 migration 忘了重启 worker，见[§8](#8-进程管理与重启) |
| `alembic` 报 revision 不一致 | 看 `migrations/versions/0001..0025_*.py` 是否完整；可能需要手工 `alembic stamp head` |
| 登录 401 | `users` 表为空或密码不对；跑 `INITIAL_ADMIN_PASSWORD=xxx alembic upgrade head` |
| 登录被锁（429 Retry-After） | 5 次失败 / 1 分钟触发 5 分钟锁定；等几分钟或重启后端清内存 |
| 后端报 `Permission denied` 写 data 目录 | 项目根目录权限问题；不要把项目放在 `~/Downloads/` 受保护位置 |
| `error_message` 里有 paddleocr 报"找不到模型" | 检查 `PADDLE_PDX_CACHE_HOME=$ROOT_DIR/data/paddlex` 是否生效 |

---

## 10. 下一步

- [`AGENTS.md`](AGENTS.md) — AI 协作流程
- [`tests/`](tests) — E2E 测试案例（md）
- [`README.md`](README.md) — 仓库结构 + 命令清单 + Changelog
- [`README-USER.md`](README-USER.md) — 终端用户使用手册

---

## 11. 打包版（终端用户）

如果你是终端用户（不是开发者），不需要安装 Python、Node.js 或任何编译工具链。

### 11.1 下载

1. 打开 [Releases 页面](https://github.com/hyqskevin/xhs-info-crawl/releases)
2. 找到最新版本（推荐 v0.6.0+）
3. 下载对应平台的 zip：
   - **macOS（Apple Silicon）**：`xhs-info-crawl-<version>-macos.zip`
   - **Windows**：`xhs-info-crawl-<version>-windows.zip`
   - **源码（开发者）**：`xhs-info-crawl-<version>-src.zip`

### 11.2 安装

- **macOS**：解压 → 右键 `xhs-info-crawl.app` → "打开" → 在 Gatekeeper 弹窗中点"打开"（首次）。后续双击即可。
- **Windows**：解压 → 双击 `xhs-info-crawl` 文件夹里的 `start.bat`。

### 11.3 与开发者安装的差异

| 维度 | 开发者 | 打包版 |
|---|---|---|
| Python | 系统装（3.11+） | 内置 `runtime/python/` (cpython-3.11.9) |
| Node.js | 需要（18+） | 不需要（前端预构建） |
| 依赖 | `pip install -e ".[ocr]"` | 预装在 `runtime/venv/` |
| 前端 | `npm run dev` | 由 FastAPI StaticFiles 服务 |
| 启动器 | 不需要 | PyWebView 窗口（与 Web UI 不同） |
| OCR | 通过 `[ocr]` extra | v0.6.0 起内置，**无需单独下载 addon** |

### 11.4 升级

1. 下载新版 zip
2. 解压到**新位置**（不要覆盖！）
3. 把旧版的 `data/` 整个复制到新版目录
4. 启动新版

### 11.5 用户手册

完整的终端用户指南（OpenCLI 配置、OCR 安装、日常使用、FAQ）：见 [`README-USER.md`](README-USER.md)。