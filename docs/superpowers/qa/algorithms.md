# 项目算法与 ID 体系总览

> 本文档梳理项目里所有用到非显然算法的位置、它们的目的、入参出参与依赖。
> 用于：
> - 同事接手时快速了解"哪些地方用了算法"；
> - 选型文档；以后改实现时知道影响面；
> - 安全审计：算法一致性与强度。

最后整理：2026-07-21，对应 release `v0.2.0`。

---

## 1. 推文 ID（小红书 note ID）：Mongo-like ObjectID 雪花算法

### 1.1 现状

小红书平台用 **24 字符 16 进制（hex）字符串**作为推文 ID，结构与 MongoDB ObjectID 完全相同：

```
[8 hex 时间戳][5 hex 随机][3 hex 计数器][6 hex 计数器/MSB][2 hex 进程/机器]
        │                                                    │
        │                                                    └─ 12 位：进程标识 + 递增 counter
        └─ 32 位（4 字节）：Unix **秒**级时间戳，按 UTC+8 解释
```

### 1.2 反解发布日期

- 文件：`backend/app/services/note_id_published_at.py`
- 触发：抓取流程 `crawl_task.process_note`，`opencli_adapter.xiaohongshu.search` 已经直接给出 `published_at`，但当 `published_at` 缺失或 `raw_data` 没有时间信息时，回退到本算法从 `platform_note_id` 反算。
- 算法：

  ```
  1. 正则提取 URL/source_url 中的 24 hex 字符（不区分大小写）。
  2. 取前 8 hex → int(hex, 16) → ts 秒级 epoch。
  3. 过滤：1_000_000_000 ≤ ts ≤ 4_000_000_000（1971-01-01..2096-09-06）。
  4. ts + 8 小时（Asia/Shanghai → UTC 偏移），返回 tzinfo=UTC 的 datetime。
  ```

- 入参：`note_id_or_url: str | None`
- 出参：`datetime | None`（UTC，秒级）；非法输入返回 `None`。
- 精度：精确到**秒**（不计毫秒）。
- 验证范围：`backend/tests/test_note_id_published_at.py` 4 个 case：
  - 合法 24 hex；
  - 截断 6 hex（无法提取 → None）；
  - 空 URL；
  - 防御 hex 越界。

### 1.3 历史回填

`backend/scripts/backfill_note_id_published_at.py`：

- 扫描 `notes` 表里 `published_at IS NULL` 且 `platform_note_id` 是 24 hex 的行；
- 调 `note_id_published_at(platform_note_id)` 写入 `published_at`；
- 写出 before/after 计数；幂等，可重复跑。

---

## 2. UUID v4：抓取任务运行令牌

### 2.1 用途

每次 `POST /api/v1/tasks/crawl` 与 `POST /tasks/{id}/restart` 都会生成新的 `run_token`（UUID v4），落到 `crawl_tasks.run_token`。Worker 通过对比入参 `run_token` 与数据库值判断是否"陈旧消息"，避免旧执行继续写入。

### 2.2 出处

| 文件 | 用法 |
|---|---|
| `backend/app/models/task.py:13` | `run_token: Mapped[str] = mapped_column(String(36), default=lambda: str(uuid4()), index=True)` |
| `backend/app/api/v1/tasks.py:56` | 启动任务时 `CrawlTask(..., run_token=str(uuid4()), ...)` |
| `backend/app/api/v1/tasks.py:77` | 续跑任务时重置 `task.run_token=str(uuid4())` |

### 2.3 强度

- UUID v4：122 bit 随机熵（业内"中等"水平）；
- 任务 ID 不是公开面对前端；
- 主要作用是**去重 + 防 stale 消息**，不是鉴权（鉴权走 JWT）。

---

## 3. JWT（HS256）：登录与跨进程认证

### 3.1 出处

`backend/app/core/security.py`：

- `create_access_token(payload, secret_key)`：`jwt.encode(payload, settings.secret_key, algorithm="HS256")`；
- `require_admin(...)` / `get_current_user(...)`：`jwt.decode(credentials, secret_key, algorithms=["HS256"])`，校验 `sub` / `exp`。

### 3.2 现有局限

- 单 secret 对称；`SECRET_KEY` 未设置时使用固定默认（开发友好、上线必须改）；
- 无 refresh token；
- 无 token 黑名单（撤销需等待过期）；
- 阶段二建议：换成 RS256，配 refresh token + Redis 黑名单。

详见 `docs/risks-todos.md`（如已建立）。

---

## 4. Argon2：密码哈希

### 4.1 用法

`backend/app/core/security.py`：

- `pwdlib[argon2]` 提供 password hash；
- `verify_password(password, encoded)`：登录时校验；
- 新建/重置 admin 用 `hash_password` 编码。

### 4.2 强度

- 默认参数已由 `pwdlib` 选定（迭代 / 内存成本），无需业务调整；
- 所有 admin 密码必须经过 Argon2 编码才入库。

---

## 5. 序列相似度：去重候选筛查

### 5.1 出处

`backend/app/services/dedup.py`：

- 同城市下推文两两计算标题 + 正文的相似度；
- `SequenceMatcher` ratio + 自定义权重：`title=0.65` + `content=0.35`；
- 总分 ≥ `0.55` 写入 `note_duplicate_candidates` 表，`status='pending'`；
- 用户在仪表盘"重复项"页选择 merge 或 ignore。

### 5.2 算法细节

```
score = title_ratio(title_a, title_b) * 0.65 + content_ratio(content_a, content_b) * 0.35
matched_fields: list[FieldKey] = []
  if title_ratio >= 0.60: matched.append("title")
  if content_ratio >= 0.60: matched.append("content")
```

阈值 0.55 是经验值，权衡了"误报 vs 漏报"。

### 5.3 复杂度

- 当前实现 `O(n²)`（两两比）；n 在同城 200 篇以内可接受；
- 阶段二若单城市 > 1000 篇，可换 SimHash / MinHash + LSH bucket 做候选过滤。

---

## 6. 前端：vue-router / Element Plus 表格分页

| 算法/功能 | 文件 | 备注 |
|---|---|---|
| `vue-router` hash 模式 | `frontend/src/router.ts` | 默认 hash 模式；阶段二可以切 history 模式 + Nginx 配 fallback |
| `el-pagination` 分页 token | 各 `View.vue` | 受后端 `page` / `page_size` 限制 |
| `crypto.randomUUID()` | （未来） | 多账号体系新增用户邀请链接时可用 |

---

## 7. Celery 任务调度

`backend/app/tasks/crawl_task.py`：

- `@celery.task(bind=True, name='app.tasks.crawl_task.run_crawl')`；
- 任务执行 fence、stop token 通过 `run_token` 关联；
- 子进程通过 `task_registry` 注册（详见 `app/services/task_registry.py`）。

---

## 8. 数据保留与备份

| 资源 | 周期 | 算法 |
|---|---|---|
| Celery 文件 broker | 不清理 | filesystem |
| 图片存储 | 不清理 | filesystem |
| 数据库备份 | 手动 / cron | `make backup` 压缩 SQLite 到 `data/backups/` |

---

## 9. 总结：本项目算法栈

```
+----------------+     +-----------------+     +----------------+
| 小红书 ObjectID | →   | 解析发布时间    | →   | 写回 published |
+----------------+     +-----------------+     +----------------+
        ↑
        │ (24 hex, snowflake)
        │
+----------------+     +-----------------+     +----------------+
| UUID v4         | →  | 任务 run_token  | →   | 防 stale 消息  |
+----------------+     +-----------------+     +----------------+

+----------------+     +-----------------+     +----------------+
| JWT HS256       | →  | 登录认证         | →   | Bearer 中间件  |
+----------------+     +-----------------+     +----------------+

+----------------+     +-----------------+     +----------------+
| Argon2          | →  | 密码哈希         | →   | users 表       |
+----------------+     +-----------------+     +----------------+

+----------------+     +-----------------+     +----------------+
| SequenceMatcher | →  | 去重候选         | →   | 待人工 merge   |
+----------------+     +-----------------+     +----------------+
```

---

## 10. 阶段二待替换 / 待加强

| 当前算法 | 后续方向 | 阶段 |
|---|---|---|
| HS256 + 单 SECRET | RS256 + 短过期 + refresh token | 阶段二 |
| SQLite | PostgreSQL | 阶段二 |
| Filesystem Celery broker | Redis broker | 阶段二 |
| 本地 filesystem 图片存储 | MinIO / S3 | 阶段二 |
| SequenceMatcher 0.55 / 0.60 | SimHash / MinHash + LSH | 视规模 |
| run_token = UUID v4 | ULID（时间有序 + 易读） | 优化 |
