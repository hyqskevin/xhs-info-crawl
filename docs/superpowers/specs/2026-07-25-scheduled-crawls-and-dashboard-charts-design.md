# 定时任务调度 + 博主分组 + 仪表盘抓取统计 — 设计

日期：2026-07-25
关联 TODO：当前待办第 2、3 条（吸收原"Beat 每周定时抓取真正生效"）
关联既有 spec：`2026-07-25-crawl-scope-and-archive-layout-design.md`（scope 语义）、`2026-07-21-city-and-keyword-groups-design.md`

## 1. 需求（用户 2026-07-25 确认）

1. 左侧 navbar 新增一栏「定时任务」，含两个子栏位：
   - 子栏位一：定时任务配置——每周几 + 时间、抓取城市、关键词组、白名单（博主）组；语义：**有关键词抓关键词，有白名单抓白名单，都有则都抓**；
   - 子栏位二：关键词组和白名单组的配置（CRUD），可被栏位一选择。博主分组是新实体。
2. 仪表盘展示：
   - 各定时任务最近一次抓取的成功/失败状态；
   - 折线图：x = 抓取时间，y = 抓取数量；
   - 饼图：抓取成功率。

## 2. 总体设计

### 2.1 调度机制：DB 驱动 dispatcher（替代静态 ping）

Celery Beat 的静态 `beat_schedule` 不支持用户运行时增删任务，因此采用标准做法：

- `celery_app.py` 的 `weekly-crawl`（health.ping）替换为 `scheduled-crawl-dispatch`：每分钟执行 `app.tasks.crawl_task.scheduled_dispatch`；
- dispatcher 每次 tick：
  1. 取 Asia/Shanghai 当前时间 `now`；
  2. 查 `scheduled_crawls`：`enabled=true` 且 `day_of_week == now.isoweekday()` 且 `hour/minute` 匹配；
  3. **幂等**：slot = `now.strftime("%Y-%m-%dT%H:%M")`，若 `schedule.last_fired_slot == slot` 则跳过（防 beat 重启/重复 tick 重发）；
  4. **单任务约束**：若已有 PENDING/RUNNING/STOP_REQUESTED 任务，跳过本次触发并记 WARNING（保守语义：定时任务不打断人工任务；与手动 `/tasks/crawl` 的"顶替"语义刻意不同）；
  5. 展开范围：`keyword_group_ids` 直接入 params（`resolve_effective_keywords` 已支持）；`blogger_group_ids` 展开为组内 enabled 博主 ∩ 当前城市 enabled 博主的 `blogger_ids`；
  6. 创建 CrawlTask（`type='scheduled'`，params 含 `schedule_id`、`fired_slot`、`schedule_name`），生成 run_token，`run_crawl.delay()`；
  7. 更新 `last_fired_slot`。

### 2.2 数据模型（migration `0015_scheduled_crawls_and_blogger_groups`）

```text
blogger_groups        id, name(unique), description, enabled, created_at
blogger_group_members id, group_id FK→blogger_groups CASCADE,
                      blogger_id FK→bloggers CASCADE, created_at
                      UniqueConstraint(group_id, blogger_id)
scheduled_crawls      id, name, enabled,
                      day_of_week INT (1-7, ISO，1=周一),
                      hour INT (0-23), minute INT (0-59),
                      city_code VARCHAR(32),
                      keyword_group_ids JSON (list[int]),
                      blogger_group_ids JSON (list[int]),
                      recent_filter VARCHAR(16) NULL (缺省用城市配置),
                      last_fired_slot VARCHAR(16) NULL,
                      created_at, updated_at
```

- 博主组不直接绑城市：组是博主的命名集合；触发时按任务城市过滤（博主须在该城市 `blogger_cities.enabled=true`）；
- 范围校验在 API 写入时做（组存在/启用、城市存在/启用），触发时再按当时配置动态过滤（组后来被禁用 → 自然落空）。

### 2.3 API

博主分组（仿 keyword-groups，`/settings` 下，admin）：

```
GET    /settings/blogger-groups
GET    /settings/blogger-groups/{id}
POST   /settings/blogger-groups            {name, description?, blogger_ids[], enabled}
PUT    /settings/blogger-groups/{id}/members  {blogger_ids[]}  # 全量替换
DELETE /settings/blogger-groups/{id}
```

定时任务（新 router `/schedules`，admin）：

```
GET    /schedules                      # 列表，含最近一次任务状态
POST   /schedules                      {name, day_of_week, hour, minute, city_code,
                                        keyword_group_ids[], blogger_group_ids[], recent_filter?, enabled}
PUT    /schedules/{id}
DELETE /schedules/{id}
```

校验：城市存在且启用；组存在且启用；`day_of_week∈1..7`、`hour∈0..23`、`minute∈0..59`；关键词组与博主组至少选一（422「请至少选择一个关键词组或博主组」）。

仪表盘统计（`GET /dashboard/analytics`，登录即可）：

```json
{
  "recent_tasks": [{"id","source","schedule_name","status","started_at","total_notes","success_notes","failed_notes"}],
  "status_counts": {"COMPLETED": n, "COMPLETED_WITH_ERRORS": n, "FAILED": n, "STOPPED": n, "OTHER": n},
  "schedules": [{"id","name","enabled","day_of_week","hour","minute","last_task":{"id","status","started_at"}|null}]
}
```

- `recent_tasks`：最近 20 次任务（按 id 倒序取再正序），`source = scheduled/manual`（按 params.type / schedule_id 判定）；
- `status_counts`：最近 50 次任务的状态分布（饼图数据）；
- `schedules[].last_task`：按 `params->>'schedule_id'` 匹配的最新 CrawlTask（SQLite JSON 查询用 `json_extract`，模型层用 Python 过滤避免方言绑定——见实现）。

### 2.4 前端

**新页面 `SchedulesView.vue`**（nav「定时任务」，`/schedules`，icon `Timer`）：

- Tab1「定时任务」：表格（名称、周期"每周X HH:mm"、城市、关键词组、博主组、时间范围、启用、最近状态、操作）；新建/编辑对话框（ElSelect 星期、ElTimePicker 时间、城市单选、关键词组多选、博主组多选、recent_filter 单选、启用开关）；删除二次确认。
- Tab2「分组管理」：内嵌两个子 tab——「关键词组」直接复用现有 `KeywordGroupSettings.vue` 组件；「博主组」新建 `BloggerGroupSettings.vue`（表格 + 对话框，成员为博主多选，展示成员用户名）。
- 配置中心的「关键词组」tab 保留（同一组件两个入口，不破坏既有路径与测试）。

**仪表盘 `DashboardView.vue`** 新增三块：

- 「定时任务状态」卡：每个 schedule 一行（名称、周期、启用、最近状态 ElTag），无定时任务时空状态；
- 「抓取趋势」折线图：最近 20 次任务，x=开始时间（MM-DD HH:mm），三条线：发现/成功/失败；
- 「成功率」饼图：最近 50 次任务状态分布（COMPLETED=成功、COMPLETED_WITH_ERRORS=部分成功、FAILED=失败、STOPPED=已停止、OTHER=其他）。
- 图表库：引入 `echarts`（Element Plus 无图表能力，符合 UI 规范"明确缺少必要能力时允许自定义"）；新建 `components/CrawlTrendChart.vue` 与 `components/CrawlSuccessPie.vue` 封装 init/resize/dispose；组件测试 `vi.mock('echarts')`。

## 3. TDD 计划（先红）

后端新增：

- `tests/test_blogger_group_api.py`：CRUD、重名 409、成员全量替换、删除级联；
- `tests/test_schedules_api.py`：CRUD、字段边界校验（day_of_week/hour/minute 越界 422）、城市/组校验 422、两组皆空 422、列表含 last_task；
- `tests/test_scheduled_dispatch.py`：到点触发创建任务并入队（celery_dispatches 语义改为直接调函数）、slot 幂等（同 slot 不重复）、不到点不触发、有 RUNNING 任务跳过、博主组展开（组内 3 博主仅 2 个属于城市 → blogger_ids=[2 个]）、组后补禁用落空；
- `tests/test_dashboard_analytics.py`：recent_tasks 排序与数量上限、status_counts 分布、schedules.last_task 匹配。

前端新增：

- `tests/views/SchedulesView.spec.ts`：加载列表、提交表单调用 createSchedule（payload 含 day_of_week/hour/minute/组）、删除确认；
- `DashboardView.spec.ts` 更新：渲染定时状态卡与图表容器（mock echarts 与 analytics API）。

既有改动：

- `celery_app.py` beat_schedule 替换 → `tests/test_celery_config.py` 同步；
- `run_crawl` 的 `type` 字段仅记录，不影响现有逻辑。

## 4. 验收

- 上述测试先红后绿；后端、前端全量测试与 `npm run build` 绿；
- migration `0015` 在临时库 upgrade/downgrade 通过；生产库 upgrade 后 `blogger_groups`/`scheduled_crawls` 存在；
- 实操链路：建博主组 → 建定时任务（本周几当前时间+1 分钟）→ beat tick 后 CrawlTask 生成且 params 含展开结果；
- **涉及 ORM 模型、`app/tasks/*.py`、`app/services/*.py` 改动：完成后必须重启 celery worker 与 beat**（连同待办"重启 celery beat 与 worker"一并执行并提示用户）。

## 5. 非目标

- 不做 django-celery-beat / 秒级 cron 表达式；
- 定时任务不支持多城市（单次一个城市，与手动任务一致）；
- 不做频率控制（待办第 4 条）；
- 不移除配置中心的关键词组 tab。
