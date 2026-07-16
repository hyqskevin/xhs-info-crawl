# 测试用例文档索引

## 项目
小红书本地活动信息抓取系统 (xhs-activity-crawler)

## 测试框架
- **后端**: pytest 7.x + pytest-asyncio + pytest-celery
- **API 测试**: httpx + FastAPI TestClient
- **覆盖率**: pytest-cov

## 测试模块

| 序号 | 模块 | 文件 | 用例数 | 优先级分布 |
|------|------|------|--------|------------|
| 1 | 爬虫引擎 | `test-crawler-engine.md` | 10 | P0:6, P1:4 |
| 2 | OCR 图片识别 | `test-ocr.md` | 6 | P0:4, P1:1, P2:1 |
| 3 | 字段提取管道 | `test-extraction-pipeline.md` | 8 | P0:6, P1:2 |
| 4 | 活动去重 | `test-activity-dedup.md` | 9 | P0:7, P1:2 |
| 5 | 认证与用户管理 | `test-auth.md` | 10 | P0:7, P1:2, P2:1 |
| 6 | 活动 CRUD API | `test-activity-crud-api.md` | 10 | P0:7, P1:3 |
| 7 | 任务调度 | `test-task-scheduling.md` | 10 | P0:6, P1:4 |
| 8 | 周报生成 | `test-report-generation.md` | 9 | P0:6, P1:3 |
| 9 | 前端 UI 与跳转 | `test-frontend-ui-e2e.md` | 13 个编号 / 28 个浏览器场景 / 12 个组件模块场景 | 已实现:13 |

**总计：72 个测试用例**

可执行实现与最新运行结果见 `EXECUTION_STATUS.md`。本文件及各 `test-*.md` 是测试规格，不等同于全部已经实现的自动化代码。

## 分阶段执行

- 阶段一执行除 Flower 之外的核心契约，并使用 SQLite、本地文件系统和 Celery filesystem broker；报告测试必须覆盖 `.xlsx` 与 `.md` 双格式。
- 阶段二复用全部阶段一契约，再增加 PostgreSQL、Redis、MinIO、Docker Compose 和 Flower 的集成测试。

## 运行全部测试

```bash
# 安装依赖
pip install pytest pytest-asyncio pytest-cov pytest-celery httpx

# 运行所有测试
pytest tests/ -v

# 生成覆盖率报告
pytest tests/ --cov=backend --cov-report=html
```

## 测试分层

| 层级 | 数量 | 说明 |
|------|------|------|
| 单元测试 | ~50 | 测试单个函数/方法的行为 |
| 集成测试 | ~18 | 测试 API 路由 + 数据库交互 |
| 性能测试 | ~2 | 验证时间和资源限制 |
| 参数化测试 | ~5 | 多种输入组合 |

## 编写规范

1. **命名规范**: `test_<功能描述>_<预期行为>`，如 `test_keyword_crawl_returns_notes`
2. **Given-When-Then**: 每个用例按此结构组织
3. **Mock 边界**: 只 Mock 系统边界（外部 API、数据库），不 Mock 内部实现
4. **一个断言一个行为**: 每个 test case 验证一个行为
5. **优先级标注**: P0（核心路径）、P1（边界/异常）、P2（性能/优化）
