# 推文子活动软删除与周报全收录测试案例

关联 spec：`docs/superpowers/specs/2026-07-21-remove-activity-approval-status-design.md`

## 数据模型

1. 应用 0011 迁移后，SQLite/SQLAlchemy 加载 `Activity` 模型时不再要求 `status` 列：
   - `Activity` 没有 `status` 列；
   - 存在 `deleted_at` 可空 datetime 列；
   - 旧库升级后所有活动行的 `deleted_at` 为 `NULL`（不论旧 `status` 值）。
2. 回滚迁移时 `deleted_at` 被移除，`status` 列被恢复，默认值 `ACTIVE`；软删除的行回填 `status='DELETED'`。

## 后端 API

1. `GET /api/v1/activities` 默认不返回软删除行；插入 3 条活动并把其中一条 `deleted_at` 设为现在，再请求列表仅返回 2 条。
2. `GET /api/v1/activities?status=APPROVED` 不再按 status 过滤：即使没有 status 字段也按现有数据集返回；或返回 422 视实现而定（已实现为移除该参数）。
3. `DELETE /api/v1/activities/{id}` 后该活动 `deleted_at` 非空，列表查询 404。
4. `POST /api/v1/activities/batch/approve` 返回 `410 Gone`，detail 文案提示使用 `/api/v1/notes/{id}/review`。
5. `PUT /api/v1/activities/{id}` 不再校验 status 转换；传入 `{"status":"RAW"}` 返回 422，但文案是“活动已取消审核状态字段”。
6. 删除接口幂等：连续两次 `DELETE` 同一活动，第二次返回 404。
7. `DELETE /api/v1/activities/batch` 软删多条；`status_code=200` 返回 `deleted_ids`；重复删除已软删的活动返回 404。

## 业务逻辑

1. LLM 抽取服务 `extract_activities` 返回 dict 中不再包含 `status` 键；`Activity(**fields)` 模型构造不会因缺字段报错。
2. `merge_activities` 返回 dict 中 `status` 不存在；调用方对返回值不再依赖 `status`。
3. `create_duplicate_candidates` 使用 `Activity.deleted_at.is_(None)`；软删的活动不再与其他活动形成新候选。

## 周报收录

1. 准备 1 篇 `APPROVED` 推文，其下 3 条子活动 `deleted_at IS NULL`，1 条已被软删：
   - 生成周报 markdown 与 xlsx。
   - markdown 与 xlsx 内分别出现 3 条子活动，未软删 1 条不出现在内容中。
2. 推文 `review_status != APPROVED` 时整篇不进周报，下属子活动也不计入。
3. 推文 `published_at` 不在本周时整篇不进周报，即使 `review_status=APPROVED`。
4. 子活动 `start_time` 在未来、过去、本周之外都进入周报；周报对子活动发生时间无要求。

## 前端组件

1. 活动管理详情表的活动列不再有“状态”列；操作列只剩“编辑/删除”。
2. 工具栏不再有“批量通过”按钮；批量删除按钮保留。
3. 活动编辑对话框表单字段为 `name/location/summary`；不含 `status`。
4. 推文维度筛选器 `review_status` 仍保留 `PENDING/APPROVED/REJECTED`。
5. 详情头部“通过/驳回”属于推文维度，按钮点击后调用 `/api/v1/notes/{id}/review`。

## 浏览器 E2E

1. 打开 `/activities`，进入推文详情：
   - 详情内活动表格不含“状态”列；
   - 工具栏不见“批量通过”按钮；
   - 编辑活动表单不出现 status 输入。
2. 删除一条子活动后，刷新详情该行消失，列表总数减少。

## 验收命令

```bash
cd backend && .venv/bin/pytest -q
cd ../frontend && npm run test -- --run
npm run build
npx playwright test
cd .. && git diff --check
```
