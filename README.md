# 小红书本地活动信息抓取系统

本仓库采用两阶段交付。阶段一在本机直接运行 Vue 3、FastAPI 和 Celery，使用 SQLite、filesystem broker 与本地文件；阶段二再升级 PostgreSQL、Redis、MinIO 和 Docker Compose。

详细设计见 [docs/phase-roadmap.md](docs/phase-roadmap.md)。

## 本地要求

- macOS 或 Linux
- Python 3.11+（由 `uv` 管理）
- Node.js 22+
- `uv`
- OpenCLI 与支持 CDP 的 Chrome（抓取功能实现后使用）

## 初始化

```bash
make init
```

该命令安装前后端依赖、创建 `.env`、建立 `data/` 运行目录并初始化 SQLite。阶段一不需要 Docker、PostgreSQL、Redis 或 MinIO。

所有可调整的运行变量统一维护在根目录 `.env`。首次初始化会从 `.env.example` 复制；后端、Celery、前端及启动脚本均读取该文件。不要把真实密钥提交到 Git。

## 启动

分别打开四个终端运行：

```bash
make dev-api
make dev-worker
make dev-beat
make dev-web
```

服务地址：

- 管理端：http://127.0.0.1:5173
- API：http://127.0.0.1:8000
- API 文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/v1/health

Celery 的生产者和 Worker 共用 `data/celery/queue/`。SQLite、图片和导出分别位于 `data/app.db`、`data/images/` 和 `data/exports/`。

## 验证

```bash
make test
make build
```

## 当前脚手架边界

当前代码提供 Vue 管理端外壳、FastAPI 健康接口、SQLite 生命周期、本地 Storage 接口及 Celery filesystem broker。抓取、OCR、字段提取、去重、认证和 Excel/Markdown 业务实现将按测试规格继续开发。
