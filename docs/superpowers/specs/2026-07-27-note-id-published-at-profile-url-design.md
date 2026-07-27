# 博主链接发布时间解析错误修复设计

- 日期：2026-07-27
- 状态：已审核（持续授权）
- 关联 TODO：当前待办 #14

## 背景与根因

用户发现：待审核推文实际发布于 2026 年 7 月，但系统里发布时间全部显示为 2026 年以前。

取证（生产库 + 实测函数）：

1. 博主抓取的笔记 URL 形如 `/user/profile/<用户ID 24hex>/<笔记ID 24hex>?xsec_token=...`，含**两个** 24 hex ID。
2. `note_id_published_at`（`backend/app/services/note_id_published_at.py`）用 `_NOTE_ID_RE.search()` 取**第一个** 24 hex —— 即用户 ID，解出的是**博主账号注册时间**（如 `6145b3a2` → 2021-09-18），不是笔记发布时间。
3. `crawl_task.py` 里雪花解析优先级最高（优先于 DOM 文本），错误值直接写库。
4. 实证：同一博主 15 篇笔记 `published_at` 全部为 `2021-09-18 17:38:42`（该博主注册时间）；取第二个 ID（笔记 ID `6a5f0b8e`）则正确解出 `2026-07-21 14:02:54`。
5. 生产库受影响：所有 source_url 含 `/user/profile/` 的笔记，其中 65 篇发布时间落在 2026 年以前（按注册年份分布于 2018-08 ~ 2025-11）；账号注册于 2026 年的博主笔记日期"看起来正常"但同样是注册时间。
6. `extract_platform_note_id`（note_identity.py）按路径段模式提取，取的是笔记 ID，**无此 bug**，去重未受影响。

## 目标

1. 雪花解析对博主 profile 链接取**笔记 ID**（路径中最后一个 24 hex），而非第一个。
2. 存量错误数据一次性矫正，脚本幂等可重复执行。

## 设计

### 1. 修复 `note_id_published_at`

- 先剥离 query string（防 `xsec_token` 中偶然出现 24 hex 片段），只在 URL **path** 中匹配。
- 取 path 中**最后一个** 24 hex 作为笔记 ID：
  - `/user/profile/<uid>/<noteid>` → noteid ✅
  - `/explore/<noteid>`、`/search_result/<noteid>` → 唯一一个 ✅
  - 裸 24 hex 字符串 → 其本身（向后兼容既有测试与调用）✅
- epoch 范围校验、+8h 对齐逻辑不变。

### 2. 存量数据矫正脚本

`backend/scripts/fix_published_at_from_note_id.py`：

- 遍历 `notes` 表，对每条用修复后的函数重算 `published_at`；与库存值不同则更新。
- explore/search_result 链接重算值不变 → 天然幂等、零副作用。
- 打印扫描/更新/跳过计数；支持 `--dry-run`。
- 执行前备份 `data/app.db`。

### 3. 测试

`backend/tests/test_note_id_published_at.py` 新增：

1. profile URL 必须解出**第二个** ID 的时间（真实案例：`6a5f0b8e...` → 2026-07-21，而不是 `6145b3a2` → 2021-09-18）。
2. query string 中的 24 hex 不干扰（构造 `xsec_token` 含 24 hex 的 URL）。
3. 既有 explore / search_result / 裸 ID / 非法输入用例保持绿。

## 验收

- 新用例先红后绿；后端全量测试绿。
- 矫正脚本 `--dry-run` 输出与正式执行计数一致；执行后 `SELECT COUNT(*) FROM notes WHERE source_url LIKE '%/user/profile/%' AND published_at < '2026-01-01'` 归零（账号注册时间全部消失）。
- 前端待审核列表发布时间显示为 2026 年 7 月真实发布日期。
- 部署注意：改动在 `app/services`（SQL 相关任务链路），**需重启 worker**（与 TODO#13 一起在任务 #19 跑完后重启）。

## 非目标

- 不改 +8h 对齐算法本身（与 OpenCLI noteIdToDate 口径一致）。
- 不动 DOM 解析兜底链路（`extract_published_at`）。
- 不动 `platform_note_id` 与去重逻辑（无 bug）。
