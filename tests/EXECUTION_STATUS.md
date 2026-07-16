# 自动化测试执行状态

最后执行：2026-07-16

## 当前结果

```text
后端：66 passed, 1 skipped
前端组件：1 passed
前端 Playwright（Google Chrome）：28 passed
生产构建：passed
```

跳过项为 `TC-AUTH-010` Token 刷新机制；原测试规格将其标记为 P2 可选功能。

## 已落地的可执行覆盖

| 规格模块 | 当前可执行覆盖 | 文件 |
|----------|----------------|------|
| 认证 | 登录成功/失败、无效与过期 Token、角色权限、密码强度 | `backend/tests/test_auth_api.py` |
| 活动 CRUD | 创建、分页、城市/类型/状态/日期筛选、详情、更新、非法状态、软删除 | `backend/tests/test_activities_api.py` |
| 周报 | 城市与类型分组、状态过滤、格式、空数据、性能、持久化、重复生成、MD/XLSX 下载 | `backend/tests/test_reports.py` |
| 处理服务 | 去重评分与合并、规则/LLM 提取、OCR 成功/空/失败/批量/置信度、OpenCLI 错误映射与近 7 天过滤、任务锁 | `backend/tests/test_pipeline_services.py` |
| E2E | 登录→创建活动→审核→筛选→生成周报→下载 MD/XLSX | `backend/tests/test_e2e_workflow.py` |
| 脚手架 | 配置、SQLite、本地存储、Celery filesystem broker、健康检查、`.env`、启动脚本 | `backend/tests/test_*.py` |
| 前端 | 仪表盘组件与后端健康状态 | `frontend/src/views/DashboardView.spec.ts` |
| 前端浏览器 E2E | 28 条场景：登录校验/成功/失败/守卫、仪表盘、5 个菜单跳转、活动新增/编辑/审核/删除/筛选/分页/详情、任务防重复/状态/日志、去重双栏/合并/忽略、周报生成/预览/MD/XLSX 下载、城市/关键词/博主配置与 OpenCLI 成功/认证失败 | `frontend/e2e/navigation.spec.ts`、`frontend/e2e/business.spec.ts`、`frontend/e2e/documented-flows.spec.ts` |
| MiniMax | 国内官方端点配置、鉴权头、模型、JSON 解析与错误处理 | `backend/tests/test_minimax.py` |
| OpenCLI 登录门禁 | `whoami` 必须先于 search；77 时停止 | `backend/tests/test_pipeline_services.py`、`scripts/test-opencli.sh` |

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
