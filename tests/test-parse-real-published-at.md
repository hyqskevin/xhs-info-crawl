# 真实发布时间解析与展示测试案例

关联 spec：`docs/superpowers/specs/2026-07-21-parse-real-published-at-design.md`

## 解析服务

1. 绝对日期：`2025-07-20`、`2025/07/20`、`2025年7月20日`、带时间 `2025-07-20 18:30`、`2025-07-20T18:30:00+08:00` 全部解析为 Asia/Shanghai，并转 UTC 存储。
2. `MM-DD`：`07-20`、`7/20`、`7月20日`；与 now_local 比，未来超过 2 天回退到上一年。
3. 相对时间：`2天前`、`5小时前`、`30分钟前` 基于 now_local（Asia/Shanghai）回推。
4. 解析失败（含空文本、垃圾文本、非法月份）返回 `None`，不再回退到 `created_at`。

## 入库回填

1. `process_note` 在创建 Note 时调用 `extract_published_at(detail, fallback_now=started_at)`：
   - OpenCLI 详情携带 `published_at`/`publishTime`/`date` 时优先解析；
   - 否则从 `content`/`title`/`snippet` 中抽取；
   - 解析失败仍落库，`published_at = None`；
   - 日志 `INFO` "未解析真实发布时间：<title or url>"。
2. 入库时间 `created_at` 仅保留审计用途。

## 列表筛选

1. `GET /api/v1/notes?start_date=...&end_date=...` 仅以 `published_at` 为准。
2. 缺 `published_at` 的推文不参与日期范围筛选（既不被纳入也不被排除，相当于"待确认"集合）。
3. 不再使用 `func.coalesce(published_at, created_at)`。

## 周报收录

1. `select_notes` 仅筛选 `published_at IS NOT NULL` 且在本周区间内的 APPROVED 推文。
2. `published_at` 为空的推文整体不进入周报。
3. 周报 markdown 中显示"发布时间待确认"占位，但不影响收录。

## 前端

1. 列表"发布时间"列：
   - 展示 `scope.row.published_at`，无值时显示"待确认"；
   - 不再回退到 `created_at`。
2. 编辑推文对话框允许清空发布时间（视为"待确认"）。
3. 详情页同步展示"待确认"。

## 验收命令

```bash
cd backend && .venv/bin/pytest -q
cd ../frontend && npm run test -- --run
npm run build
npx playwright test
```
