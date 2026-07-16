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
