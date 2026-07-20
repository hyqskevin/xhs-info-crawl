# 测试用例：抓取范围由配置驱动

## 测试环境
- 后端：pytest + FastAPI TestClient
- 前端：Vitest + Vue Test Utils
- 数据：SQLite 测试库（每例 fixture 重建）

## 关联
- spec：`docs/superpowers/specs/2026-07-17-crawl-scope-config-driven-design.md`

## 验收案例

### TC-CSC-001：博主抓取走配置驱动
**前置**：城市 `shanghai` 的博主白名单里 `博主A` (enabled) 和 `博主B` (enabled) 关联到该城市；`博主C` 关联到 `beijing`。

**操作**：提交抓取任务，`city=shanghai`，`keywords=[]`，`blogger_ids=[1]`。

**预期**：
- 后端日志输出 `抓取范围生效：keywords=0 bloggers=1`
- 只调 `xiaohongshu user <博主A.profile_url>` 抓 `博主A`
- 不调任何 `xiaohongshu search` 命令
- 不抓 `博主B` 和 `博主C`

### TC-CSC-002：未启用博主被跳过
**前置**：`博主A` (enabled=False) 关联 `shanghai`。

**操作**：提交任务，`city=shanghai`，`blogger_ids=[<博主A.id>]`。

**预期**：
- `resolve_crawl_scope` 返回空博主列表
- 后端 `POST /tasks/crawl` 返回 422 "博客主无启用项"
- 不发起 celery 任务

### TC-CSC-003：博主 profile_url 为空时跳过 + WARNING 日志
**前置**：`博主A` profile_url=""，username="从零发现宁波"。

**操作**：提交任务包含该博主。

**预期**：
- 日志写入 `[WARNING] 跳过博主：profile_url 为空 id=<A.id>`
- 不调 `xiaohongshu user` / `xiaohongshu notes`
- 任务正常完成，0 篇笔记

### TC-CSC-004：关键词抓取走配置驱动
**前置**：城市 `shanghai` 的关键词配置：`["周末活动", "展览"]`。

**操作**：提交任务，`city=shanghai`，`keywords=[]`（依赖默认）。

**预期**：
- `resolve_effective_keywords` 返回 `["周末活动", "展览"]`
- 每个关键词调 `xiaohongshu search "上海 <keyword>"`
- 日志输出 `keywords=2 bloggers=0`

### TC-CSC-005：城市停用返回 422
**前置**：城市 `beijing` enabled=False。

**操作**：`POST /tasks/crawl {city: "beijing"}`。

**预期**：返回 422 "原任务城市已停用"。

## 自动化覆盖

| 用例 | 自动化文件 |
|---|---|
| TC-CSC-001 | `backend/tests/test_crawl_scope.py::test_blogger_only_resolves_enabled_in_city` |
| TC-CSC-002 | `backend/tests/test_crawl_scope.py::test_blogger_inactive_skipped` |
| TC-CSC-003 | `backend/tests/test_crawl_task_resilience.py::test_profile_url_empty_skipped_with_warning` |
| TC-CSC-004 | `backend/tests/test_crawl_scope.py::test_keyword_scope_uses_city_default_when_empty` |
| TC-CSC-005 | `backend/app/api/v1/tasks.py::create` 已有 422 检查 |

## 手动验收

1. 启动 dev-api + dev-worker + dev-web。
2. 配置中心 → 添加博主 `测试博主A` (profile_url 留空) 关联 `shanghai` 启用。
3. 仪表盘 → 选 `shanghai` + 选 `测试博主A`。
4. 期望：警告"博主信息不完整，请到配置中心点补充博主信息后再发起抓取"。
5. 配置中心 → 点"补充博主信息"按钮 → 等待回填。
6. 仪表盘 → 再次提交任务 → 期望抓到博主笔记。