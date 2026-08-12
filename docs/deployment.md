# 部署与运行方案

## 阶段一：本地直接运行

阶段一不使用 Docker、PostgreSQL、Redis 或 MinIO。开发者只需安装 Python 3.11、Node.js、OpenCLI 和 Chrome。

预期统一命令如下，具体命令由脚手架实施时落地：

```bash
make init       # 创建 Python 环境、安装前后端依赖、初始化 SQLite
make dev-api    # FastAPI
make dev-worker # Celery Worker + filesystem broker
make dev-beat   # Celery Beat
make dev-web    # Vue/Vite
make test       # 后端与前端测试
```

运行数据默认位于：

```text
data/app.db
data/images/
data/exports/
data/celery/queue/
```

启动 Chrome CDP 并登录小红书后，设置 `OPENCLI_CDP_ENDPOINT`。API、Worker 与 Beat 是独立本机进程，filesystem broker 目录必须使用相同配置。

### 阶段一环境变量

根目录 `.env` 是阶段一唯一运行配置入口。API、Celery、前端和启动脚本均加载该文件；新增可配置项时必须同步更新 `.env.example`，不得在代码或脚本中新增环境相关硬编码。

完整变量清单以仓库根目录 `.env.example` 为准，包括应用、API/前端端口、CORS、数据库、本地目录、Celery、定时任务、抓取限制和外部服务配置。`make init` 会在保留 `.env` 已有值的前提下补充后来新增的变量。

## 阶段二：完整技术栈部署

阶段二增加 Docker Compose，并部署 PostgreSQL 15、Redis、MinIO、FastAPI、Celery Worker、Celery Beat、Flower 和前端。生产环境再增加 Nginx、HTTPS、备份与访问控制。

阶段二通过配置替换完成升级：

- `DATABASE_URL` 从 SQLite 改为 PostgreSQL。
- `CELERY_BROKER_URL` 和 result backend 改为 Redis。
- `STORAGE_BACKEND` 从 `local` 改为 `minio`，并配置 MinIO 凭据。
- 使用 Alembic 将阶段一数据结构迁移到 PostgreSQL，并提供 SQLite 数据导入工具。

OpenCLI 与 Chrome 初期仍可运行在本地电脑，通过 CDP 与后端连接；服务器化 Chrome 属于阶段二后续部署优化，不是阶段一验收条件。

## 打包版部署（2026-08-10 新增）

打包版面向非开发者用户,通过 GitHub Actions 自动构建,推 tag 触发。spec:`docs/superpowers/specs/2026-08-10-one-click-packaging-design.md`。

### 打包版架构

```
xhs-info-crawl/
├── runtime/                       # 便携运行时(平台相关)
│   ├── python/                    # python-build-standalone cpython-3.11.9
│   └── venv/                      # 已装好 fastapi/celery/uvicorn/pywebview/...
├── app/                           # 应用代码
│   ├── backend/                   # Python 后端源码
│   ├── frontend/dist/             # 前端已构建静态产物
│   └── migrations/
├── launcher/                      # PyWebView 启动器
│   ├── main.py                    # 入口,管理 3 个子进程 + 状态服务 + PyWebView 窗口
│   ├── status_server.py           # 本地 HTTP 状态服务(端口 = API_PORT + 1)
│   ├── process_manager.py         # API/Worker/Beat 子进程管理
│   ├── ocr_installer.py           # OCR 增强包一键安装
│   ├── opencli_checker.py         # OpenCLI 连接测试
│   ├── port_finder.py             # 端口冲突自动探测(8000-8020)
│   ├── env_bootstrap.py           # .env 初始化 + 敏感配置生成
│   ├── requirements.txt
│   └── ui/dist/                   # 启动器 UI 构建产物
├── data/                          # 运行数据(首次启动初始化)
│   ├── logs/                      # 服务日志
│   ├── paddlex/official_models/   # PaddleOCR 模型(OCR 增强包安装后填充)
│   ├── huggingface/               # HuggingFace 缓存
│   └── tmp/                       # 临时文件
├── .env                           # 首次启动由 launcher 从 .env.example 生成
├── .env.example
└── README-USER.md                 # 用户使用说明
```

### GitHub Actions 构建流程

两个独立工作流:

1. **主程序**(`release.yml`):推 `v*.*.*` tag 触发
   - `build-macos` job:macos-latest,构建 `xhs-info-crawl-<version>-macos.zip`
   - `build-windows` job:windows-latest,构建 `xhs-info-crawl-<version>-windows.zip`
   - `release` job:ubuntu-latest,下载两个 zip + 生成源码 zip + 创建 GitHub Release

2. **OCR 增强包**(`release-ocr-addon.yml`):推 `ocr-addon-*` tag 触发
   - `build-macos-arm64` job:macos-latest
   - `build-macos-x86_64` job:macos-13
   - `build-windows-x64` job:windows-latest
   - `release` job:汇总 3 个 zip 到 OCR Addon Release

### 本地复现打包

```bash
# macOS(需先构建 frontend/dist 和 launcher/ui/dist)
./scripts/package-macos.sh <version>

# Windows
.\scripts\package-windows.ps1 -Version <version>

# OCR 增强包(3 平台)
./scripts/package-ocr-addon.sh macos arm64 <paddleocr_version>
./scripts/package-ocr-addon.sh macos x86_64 <paddleocr_version>
./scripts/package-ocr-addon.sh windows x64 <paddleocr_version>
```

### OCR 增强包分发

OCR 增强包与主程序版本独立,采用 `paddleocr-<paddleocr_version>` 格式(如 `ocr-addon-3.7.0`)。

- 用户在启动器内点"下载安装 OCR" → 启动器根据平台选择对应 zip
- wheels 安装到 `runtime/venv/`(pip install)
- 模型文件解压到 `data/paddlex/official_models/`
- 自动设 `OCR_ENABLED=true`
- 与项目 `PADDLE_PDX_CACHE_HOME=./data/paddlex` 配置对齐,无路径冲突

### 数据目录布局

| 目录 | 用途 | 备份优先级 |
|---|---|---|
| `data/app.db` | SQLite 数据库(所有抓取数据) | 高 |
| `data/images/` | 下载的笔记图片 | 中 |
| `data/exports/` | Excel/Markdown 导出文件 | 中 |
| `data/archive/` | 按日期归档的图片和 Markdown | 中 |
| `data/backups/` | 数据库备份 | 高 |
| `data/paddlex/` | PaddleOCR 模型(可重新下载) | 低 |
| `data/huggingface/` | HuggingFace 缓存(可重新下载) | 低 |
| `data/celery/` | Celery 消息队列(临时) | 不备份 |
| `data/tmp/` | 临时文件 | 不备份 |
| `data/logs/` | 服务日志 | 不备份 |
| `data/run/` | 进程注册表(临时) | 不备份 |

### 升级与迁移策略

- **小版本升级**:下载新版 zip,替换除 `data/` 外的所有文件,保留 `data/` 和 `.env`
- **大版本升级**:先备份数据,按 release notes 执行迁移(如 `alembic upgrade head`)
- **跨平台迁移**:复制 `data/` 目录到新平台的解压目录,首次启动自动检测并适配
- **回滚**:用旧版 zip 替换,保留 `data/`(注意大版本回滚可能需要数据库降级)

### 启动器进程管理

启动器(Python 主进程)管理 3 个子进程:

| 子进程 | 启动命令 | 健康检查 | 日志 |
|---|---|---|---|
| API | `runtime/venv/bin/python -m uvicorn app.main:app` | `GET /api/v1/health` 返回 200 | `data/logs/api.log` |
| Worker | `runtime/venv/bin/python -m celery -A app.tasks.crawl_task worker` | 进程存活 | `data/logs/worker.log` |
| Beat | `runtime/venv/bin/python -m celery -A app.tasks.crawl_task beat` | 进程存活 | `data/logs/beat.log` |

启动顺序:API → (健康检查通过) → Worker → Beat。退出时反向停止:Beat → Worker → API,先 SIGTERM 5 秒后 SIGKILL。

