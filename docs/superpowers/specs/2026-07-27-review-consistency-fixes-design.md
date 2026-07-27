# 审核规则一致性修复包 — 设计 spec

> 对应 `docs/TODO.md` 问题修复区「审核规则一致性修复包」。
> 打包修复四个同类缺陷：批量审核缺校验、merge 无幂等、配置删除不清理关联、时间口径不一致。

## 背景

代码审查发现审核链路存在四个一致性缺陷（取证见各节）。本包按 TODO 验收要求逐点修复，每点一节设计 + 定向测试。

## 7.1 批量审核绕过「有效子活动」校验

**现状**：单条审核 `POST /notes/{id}/review`（notes.py:193-203）在 APPROVED 时校验该笔记至少有 1 条未删除的 Activity，否则 422；但 `POST /notes/batch/approve`（notes.py:250-253）直接 `_batch_status`，无任何校验。无子活动的笔记经批量审核后进入 APPROVED，却永远不会出现在任何推文里（read-note 渲染依赖 Activity），形成「审了但没人看见」的脏状态。

**设计**：批量审核按 id 逐个校验，**无有效子活动的 id 跳过**（不整批 422——批量操作不应因个别脏数据全挂），响应体新增 `skipped: [{id, reason}]` 明细字段（默认空数组，向后兼容）。日志记 WARNING 便于发现数据问题。

**验收**：批量审核混合 id（有/无子活动）后，有子活动的 APPROVED、无子活动的保持 PENDING_REVIEW 且出现在 skipped 明细中。

## 7.2 duplicate merge 无幂等校验

**现状**：`POST /duplicates/{id}/merge`（duplicates.py:36-55）不检查 `candidate.status`，对同一 pending 候选并发/重复调用时：首次调用把 candidate 置为 `merged`、note B 软删；二次调用仍按已软删的 note B 重复执行 merge 逻辑，再次扫描提取（空跑）且返回 200 成功假象。

**设计**：入口检查 `candidate.status != "pending"` 时返回 409「该候选已处理」。同时查不到候选仍 404（不变）。

**验收**：同一候选 merge 两次，第二次 409；note/activity 状态与首次 merge 后一致（幂等）。

## 7.3 配置删除不清理关联表

**现状**：
- `delete_city`（settings.py:326-334）只删 `keywords`，不删 `blogger_cities`、`keyword_group_cities` → 城市删后关联表留孤儿行；
- `delete_setting(kind=bloggers)`（settings.py:491+）只 `db.delete(item)`，不删 `BloggerCity`、`BloggerGroupMember` → 博主删后 cities/组内引用成孤儿（组内仍显示该博主、抓取时 blogger_id 解析不到名字）。

**设计**：删除时级联清理：
- `delete_city`：`Keyword`（现有）+ `BloggerCity` + `KeywordGroupCity` 同步删除；
- `delete_setting(bloggers)`：`BloggerCity` + `BloggerGroupMember` 同步删除。

均同事务提交，失败整体回滚。

**验收**：删除城市/博主后，对应关联表无该 city/blogger_id 残留行；其余数据不受影响。

## 7.4 时间口径统一为「北京墙钟 naive」

**现状（三层口径打架）**：
1. 雪花路径 `note_id_published_at`：XHS ID 时间戳 +8h 标 UTC → 实际是**北京墙钟 naive**（经任务 #19 真实数据验证：卡片显示 15:35/15:50/18:41 下午至傍晚，合理）；
2. DOM 路径 `parse_published_at`：所有分支 `.astimezone(timezone.utc)` 返回**真 UTC**，与雪花路径差 8h；
3. 比较边界：`week_bounds` 返回 UTC-aware 边界、`activities/notes` 日期过滤用 `datetime.combine(..., tzinfo=timezone.utc)` → UTC 边界与「北京墙钟存储」比较，周报表/日期筛选在每日 0-8 点错位。

**设计（统一为北京墙钟 naive，零数据迁移）**：
1. `parse_published_at` 各分支返回 `SHANGHAI`-aware（不再转 UTC）；SQLite DateTime 存储时丢弃 tz 即 naive 北京墙钟，与现有 250+ 行数据一致；
2. `note_id_published_at` 显式 `.astimezone(SHANGHAI).replace(tzinfo=None)`（行为不变，仅把「+8h 是转北京墙钟」写明白）；
3. `week_bounds` 返回 naive（去掉 `replace(tzinfo=timezone.utc)`），`week_bounds_str` 改用 naive 格式化；
4. `activities.py` / `notes.py` 日期过滤 `datetime.combine(...)` 去掉 `tzinfo=timezone.utc`；
5. `docs/database-design.md` 增补时间口径章节：`Note.published_at` / `Activity.start_time` 均为北京墙钟 naive，`created_at` 为 UTC naive，比较时构造 naive 边界；
6. `published_at.py` 模块 docstring 与新口径同步。

**验收**：`parse_published_at("编辑于 07-25 上海")` 返回北京墙钟当日（与雪花路径同一笔误差 ≤ 分钟级）；本周报表在 UTC 0-8 点区间仍正确覆盖北京时间周一以来的活动；现有 `test_published_at_parser.py` 用例按新口径更新后全绿。

## 范围外（明确不做）

- 不迁移任何存量数据（现有数据本来就是北京墙钟 naive）；
- 不改 UTC `created_at` 口径（各服务自建边界，无共享口径）；
- 前端无改动（API 响应仅新增可选 `skipped` 字段）。

## 测试计划

新增 `backend/tests/test_review_consistency.py`：
- 批量审核：混合有/无子活动 id → 200，APPORVED/PENDING 分流正确，skipped 明细正确；
- merge 幂等：二次 merge → 409；
- delete_city：keywords/blogger_cities/keyword_group_cities 均清空；
- delete blogger：blogger_cities/blogger_group_members 清空；
- week_bounds：naive 且周一 00:00 / 周日 23:59:59；
- 日期过滤：边界日期笔记在 filter 中正确命中。
更新 `test_published_at_parser.py`：预期从「真 UTC」改为「北京墙钟」。
全量回归 `cd backend && pytest -q`。
