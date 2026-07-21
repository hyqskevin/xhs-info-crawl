# xhs-info-crawl · 小红书本地活动信息抓取系统

A local-first system that scrapes local event information from Xiaohongshu (小红书), runs OCR + LLM extraction, and outputs Markdown / Excel reports.
本仓库采用两阶段交付：阶段一本地单机能跑（Vue 3 + FastAPI + Celery + SQLite + filesystem broker + 本地文件存储）；阶段二将迁移到 PostgreSQL、Redis、MinIO、Docker Compose 部署方案。

- 详细路线图：[`docs/phase-roadmap.md`](docs/phase-roadmap.md)
- 安装文档：[`INSTALL.md`](INSTALL.md)
- 阶段一设计文档：[`SPEC.md`](SPEC.md)
- AI 协作流程：[`AGENTS.md`](AGENTS.md)
- 待办与已完成：[`docs/TODO.md`](docs/TODO.md)

---

## 快速开始（Quick Start）

需要本地装了 `uv` + Node 22+ + Chrome + OpenCLI。

```bash
git clone https://github.com/hyqskevin/xhs-info-crawl.git
cd xhs-info-crawl
make init                     # 装依赖、建表、seed admin
```

开四个终端（每个跑一条 `make` 命令）：

```bash
make dev-api      # uvicorn → http://127.0.0.1:8000
make dev-worker   # celery worker (1 concurrency)
make dev-beat      # celery beat
make dev-web      # vite dev → http://127.0.0.1:5173
```

浏览器打开 <http://127.0.0.1:5173>，登录 `admin / Admin@123`（从 `.env` 中的 `ADMIN_PASSWORD`），配置中心先建一条城市与博主，再到仪表盘发起抓取即可。

> 详细的"安装、测试、迁移、备份" 见 [`INSTALL.md`](INSTALL.md)。

---

## 仓库结构

```
xhs-info-crawl/
├── README.md                ← 你正在读
├── INSTALL.md               ← 安装与初始化
├── AGENTS.md                ← AI 协作流程
├── SPEC.md                  ← 阶段一系统设计
├── Makefile                 ← 顶层快捷命令
├── .env.example             ← 环境变量样例
├── scripts/                 ← init / create-admin / backup / dev-* shims
├── backend/                 ← FastAPI + SQLAlchemy + Alembic + Celery
│   ├── app/
│   │   ├── api/v1/          ← HTTP endpoints
│   │   ├── models/          ← SQLAlchemy ORM
│   │   ├── services/        ← 业务服务（dedup / extraction / opencli 等）
│   │   ├── tasks/           ← Celery 任务
│   │   └── core/            ← config / database / security
│   ├── migrations/          ← Alembic 版本
│   ├── scripts/             ← 数据回填 / 修复脚本
│   └── tests/               ← pytest
├── frontend/                ← Vue 3 + Vite + Element Plus + Pinia
│   ├── src/views/           ← 仪表盘 / 活动管理 / 抓取日志 / 周报 / 重复项 / 配置中心
│   ├── e2e/                 ← Playwright
│   └── package.json
├── docs/                    ← 设计 / specs / 路线图 / 数据库设计 / API 文档
└── tests/                   ← E2E 测试案例（md）
```

---

## 当前已实现的功能（阶段一 v0.2.0）

✅ = 已完成

- ✅ 仪表盘：选择城市 + 关键词 + 博主发起抓取；查看最近任务进度；停止/续跑/结束；安全验证恢复
- ✅ 抓取日志：多选批量删除；点击查看任务运行日志
- ✅ 活动管理：城市/关键字/审核状态过滤；单篇与批量审核；编辑推文/子活动；标记可重新处理
- ✅ 重复项：硬键去重 + 软键相似度候选；merge / ignore 操作
- ✅ 周报：按周生成 Markdown / Excel 导出
- ✅ 配置中心：城市、关键词、博主维护；博主白名单 Excel 批量导入；博主信息自动补全
- ✅ 任务运行：登录态校验、风控自动暂停保留 Chrome 页面、安全停止
- ✅ 后端 309 + 前端 48 测试全绿，前端 `npm run build` 通过

阶段二（路线图中尚未开始）：PostgreSQL / Redis / MinIO / Docker Compose 部署。

---

## 常用命令

| 命令 | 作用 |
|---|---|
| `make init` | 安装依赖、建表、seed admin |
| `make dev-api` | 起 FastAPI (uvicorn) |
| `make dev-worker` | 起 Celery worker |
| `make dev-beat` | 起 Celery beat |
| `make dev-web` | 起 Vite dev server |
| `make migrate` | 升级 DB 到最新版本 |
| `make create-admin` | 手动创建/重置 admin |
| `make test` | 后端 + 前端测试 |
| `make build` | 前端生产构建 |
| `make test-e2e` | Playwright E2E |
| `make backup` | 打包 data 目录到 `data/backups/` |

---

## 发版与 Release

- 本仓库使用 SemVer + git tag；
- 每完成 TODO.md 一项就独立提交，累积到一个稳定点打 tag（如 v0.2.0、v0.3.0）；
- Tag 由维护者在 GitHub 网页 *Releases → Draft a new release* 中关联 release notes 并发布，
  任何人可下载 `xhs-info-crawl-vX.Y.Z.zip` 源码包；
- Docker / 二进制安装包属于阶段二目标，不在阶段一打包范围。

---

## 路径与数据

| 资源 | 位置 |
|---|---|
| SQLite DB | `data/app.db` |
| 图片存储 | `data/images/` |
| 周报导出 | `data/exports/` |
| Celery broker | `data/celery/queue/` |
| Celery results | `data/celery/results/` |
| 备份 | `data/backups/`（`make backup` 生成） |

---

## 反馈与协作

- Issue 区报告 bug 与 feature 需求
- PR 请开新分支
- 详细开发约定：[`AGENTS.md`](AGENTS.md)

---

## License

Private phase-one prototype; licensing to be decided at stage two packaging.
