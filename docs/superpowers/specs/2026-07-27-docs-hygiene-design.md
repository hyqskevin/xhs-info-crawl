# TODO/文档卫生 — 设计 spec

> 对应 `docs/TODO.md` 待办 #12。

## 背景（取证结论）

1. **api-doc 覆盖缺口**：以 `app.openapi()` 枚举真实路由共 59 个端点，与 `docs/api-doc.md` 差集后缺失：
   - 仪表盘：`GET /dashboard/analytics`；健康检查 `GET /health`；
   - 任务：`DELETE /tasks/batch`；
   - 配置：keyword-groups 五个端点（GET/POST、`/{kg_id}` GET/DELETE、`/cities` PUT、`/words` PUT）、blogger-groups 三个端点（GET/POST、`/{group_id}` GET/DELETE、`/members` PUT）、博主导入三件套（import / import-template / enrich）、`GET /settings/opencli/config`；
   - 海报：poster-templates 四端点 + poster-tasks 八端点 + posters 图片两端点；
   - 定时任务：schedules 四端点；
   - 推文：`POST /notes/{id}/reprocess`；`POST /notes/batch/approve` 需按 TODO#7 补充「无有效子活动跳过 + `skipped` 明细」语义；`POST /duplicates/{id}/merge` 补 409 幂等说明。
2. **dedupe_cities.py 位置**：spec（2026-07-21-dedupe-cities-design.md:27）写 `backend/scripts/dedupe_cities.py`，实际在 `backend/app/scripts/dedupe_cities.py`（可 import 的包内位置，测试从 `app.scripts.dedupe_cities` 导入）。对齐方式选「改文档不改码」：移动文件会破坏包导入且无任何收益。
3. **「城市去重」TODO 条目**：验收证据已满足——0013 上线前已跑脚本（TODO 上一条 实测行佐证）、当前生产库重名数 0、`cities.name` 已有唯一索引 `ix_cities_name_unique` 且 TODO#9 起模型层同步声明，重名不可能再产生。条目应打勾移入已完成。

## 设计

1. `docs/api-doc.md`：按现有「一节一端点、用途一句话」风格原位补齐上述全部缺失端点（配置接口节内插 keyword-groups / blogger-groups / 博主导入 / opencli config；新增「海报接口」「定时抓取接口」两节；仪表盘/任务/健康检查小节补充）；更新 `batch/approve` 与 `merge` 语义为当前实现。
2. `docs/superpowers/specs/2026-07-21-dedupe-cities-design.md`：位置行更正为 `backend/app/scripts/dedupe_cities.py` 并注明实际形态（包内可导入模块）。
3. `docs/TODO.md`：「城市去重」标 [x] 移入已完成区，记录证据（生产 0 重名 + 唯一索引兜底）。

## 验收

- 自查脚本：`app.openapi()` 59 端点路径全部能在 api-doc.md 中检索到（按 `:id`/`{id}` 归一化比对）；
- 全量测试不受影响（纯文档改动，仅回归确认）；
- TODO「城市去重」状态与实际一致。
