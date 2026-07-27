# 活动级 duplicate_candidates 停写 + 存量清理设计（TODO#5 方案 A）

- 日期：2026-07-27
- 状态：已审核（用户 2026-07-27 明确选择方案 A）
- 关联：审计 `docs/superpowers/qa/2026-07-25-project-audit.md` 第三节

## 背景

`create_duplicate_candidates` 在活动写入时为同城活动生成重复候选（生产库 1160 行），但无任何 API/UI 消费——去重页（`api/v1/duplicates.py`）与 dashboard 只消费推文级 `note_duplicate_candidates`。用户拍板：方案 A，停写 + 一次性清空存量。

## 设计

### 1. 停写

- `crawl_task.py`：删除活动循环末尾的 `create_duplicate_candidates(db, activity)` 调用及 import；推文级 `create_note_duplicate_candidates` 保持不变。
- `dedup.py`：删除 `create_duplicate_candidates` 函数及其专用导入（`true`、`DuplicateCandidate`、`Activity`——其余函数只用 dict/Note）。
- 测试：`test_opencli_and_dedup_integration.py` 删 2 个直接测试该函数的死用例及 import。
- 保留：`DuplicateCandidate` 模型与空表（`test_activity_cleanup.py` 的过期活动清理会联动清候选行，保持有效；避免额外 drop table 迁移）。

### 2. 存量清理脚本

`backend/scripts/cleanup_duplicate_candidates.py`：

- `DELETE FROM duplicate_candidates`，幂等（重复执行为 no-op）。
- 支持 `--dry-run` 只报计数；正式执行打印 before/after。
- 执行前用 `scripts/backup.sh` 备份。

### 3. 测试（TDD）

`backend/tests/test_duplicate_candidates_stop.py`：

1. `dedup` 模块不再有 `create_duplicate_candidates`，仍有 `create_note_duplicate_candidates`（先红）。
2. `crawl_task.py` 源码 AST 中无 `create_duplicate_candidates` 引用（先红）。
3. 清理脚本：种子 2 行 → 执行归零 → 再执行仍归零（幂等）（先红，脚本不存在）。

## 验收

- 3 个新用例先红后绿；后端全量测试绿（除已知 poster 环境用例）。
- 生产库 `SELECT COUNT(*) FROM duplicate_candidates` 归零。
- 部署：改动 `crawl_task.py`/`dedup.py`，**需重启 worker**。

## 非目标

- 不 drop `duplicate_candidates` 表、不删模型（避免破坏性迁移；空表零成本）。
- 不动推文级 `note_duplicate_candidates` 及去重页任何行为。
