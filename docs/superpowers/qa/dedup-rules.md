# 去重规则（Q&A）

> 状态：已完成。

## 问题

抓取列表里出现重复推文吗？去重是按什么字段？

## 回答

去重**有两层**：

1. **同平台 note ID 自动去重（硬键）**
   - `Note.platform_note_id` —— 小红书 24 hex 雪花 ID。在 `Note` 表上 `unique=True`，数据库层面就阻止重复行。
2. **内容相似度候选去重（软键）**
   - 同城市内、不同 ID 但内容雷同的推文，会被写入 `note_duplicate_candidates` 表，**不会自动删除**；
   - 用户在仪表盘"重复项"页人工 review，merge 或 ignore。

## 实现位置

### 硬键

- `app/services/note_identity.py::extract_platform_note_id` —— 从 URL 抽 24 hex note ID；
- `app/services/note_identity.py::canonicalize_note_url` —— 去掉 `xsec_token` 等 query；
- `app/services/pipeline.py::process_candidate_item` —— `identity = f"{city}:{platform_note_id}"`；
- `app/tasks/crawl_task.py::prepare_existing_note` —— 入库前查 `platform_note_id`，存在则更新不新增；
- `Note.platform_note_id` DB 列：`unique=True`。

### 软键（候选）

- `app/services/dedup.py::create_note_duplicate_candidates` —— 用 `difflib.SequenceMatcher` 算 title (权重 0.65) + content (权重 0.35) 相似度，score ≥ 0.55 入候选；
- 候选存 `note_duplicate_candidates` 表，状态 `pending`；
- 用户在仪表盘"重复项"页 merge（保留一个）或 ignore。

## 例子

| 场景 | platform_note_id | title 相似 | content 相似 | 行为 |
|---|---|---|---|---|
| `?...xsec_token=A` 与 `?...xsec_token=B` | 同 ID | — | — | 同 ID → DB 直接去重 |
| A.用户发的 与 B.博主发的同一篇 | 不同 | 高 | 高 | 写候选表，用户人工 merge |
| 不同内容笔记 | 不同 | 低 | 低 | 不入候选 |

## 含义

- 同一 note ID（不同 token / 不同博主主页 / 不同搜索词）→ 自动识别为同一篇；
- 内容**真**雷同 → 自动入候选，**不直接删**（避免假阳性），需要人工确认；
- 用户配置逻辑：硬键优先于软键。

## TODO

- [ ] 在仪表盘"重复项"页加 `kept_note_id` 高亮显示当前是否有人工 merge 决策；
- [ ] (可选) 加"全局相似度阈值配置"——硬阈值 0.55 目前写在 `dedup.py`，可让用户在配置中心改。

