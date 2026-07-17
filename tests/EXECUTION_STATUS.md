# 自动化测试执行状态

最后执行：2026-07-17

## 当前结果

```text
后端：88 passed, 1 skipped
前端组件/模块：16 passed（11 个测试文件）
前端 Playwright（Google Chrome）：32 passed
生产构建：passed
```

跳过项为 `TC-AUTH-010` Token 刷新机制；原测试规格将其标记为 P2 可选功能。

## 已落地的可执行覆盖

| 规格模块 | 当前可执行覆盖 | 文件 |
|----------|----------------|------|
| 认证 | 登录成功/失败、无效与过期 Token、角色权限、密码强度 | `backend/tests/test_auth_api.py` |
| 活动管理 | 禁止手工创建、分页、城市/类型/状态/日期筛选、详情、审核更新、非法状态、单条与批量软删除 | `backend/tests/test_activities_api.py`、`backend/tests/test_activity_batch_delete.py` |
| 周报 | 单城市约束、城市与类型分组、状态过滤、格式、空数据、性能、持久化、重复生成、鉴权 MD/XLSX 下载 | `backend/tests/test_reports.py`、`backend/tests/test_report_city_validation.py` |
| 处理服务 | 去重评分与合并、规则/LLM 提取、模糊日期降级、OCR、OpenCLI 错误映射、阶段重试、单笔记隔离与旧任务续跑 | `backend/tests/test_pipeline_services.py`、`backend/tests/test_multi_activity_archive.py`、`backend/tests/test_crawl_task_resilience.py` |
| E2E | 登录→读取爬取活动→人工审核→筛选→生成周报→下载 MD/XLSX | `backend/tests/test_e2e_workflow.py` |
| 脚手架 | 配置、SQLite、本地存储、Celery filesystem broker、健康检查、`.env`、启动脚本 | `backend/tests/test_*.py` |
| 前端组件/模块 | App、布局、7 个页面组件、路由守卫、HTTP Token 请求头 | `frontend/src/**/*.spec.ts`，共 11 个文件、16 条场景 |
| 前端浏览器 E2E | 登录与菜单、仪表盘配置化抓取及细化进度/续跑、活动筛选/分页/详情/审核/批量删除、去重、单城市周报与下载、城市组合配置、OpenCLI 独立 Loading 与 Toast | `frontend/e2e/navigation.spec.ts`、`frontend/e2e/business.spec.ts`、`frontend/e2e/documented-flows.spec.ts` |
| MiniMax | 国内官方端点配置、鉴权头、模型、JSON 解析与错误处理 | `backend/tests/test_minimax.py` |
| OpenCLI 登录与筛选 | `whoami` 必须先于 search；77 时停止；用稳定 CSS/DOM 选择器操作“最新”和时间范围，不依赖动态数字引用 | `backend/tests/test_pipeline_services.py`、`backend/tests/test_opencli_and_dedup_integration.py`、`scripts/test-opencli.sh` |
| 多活动与日期归档 | 一篇笔记拆分多活动、来源图片编号、原文链接、日期/任务目录、MD/XLSX/图片同目录 | `backend/tests/test_multi_activity_archive.py` |

## 阶段一剩余增强项

- 大图片压缩/旋转等 OCR 预处理仍属于准确率增强，不阻塞基础图片 OCR 链路。
- OpenCLI 每周总量上限目前由环境变量保留，后续可增加按自然周持久化计数器。
- `TC-AUTH-010` Token 刷新为测试规格中的 P2 可选项，当前未实现。

## 运行命令

```bash
uv run --project backend pytest backend/tests -q
npm --prefix frontend test -- --run
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```
