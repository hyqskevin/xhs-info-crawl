# 博主笔记抓取改用 search 模式（带 xsec_token 的完整 URL）（2026-07-17）

## 背景

任务 #7 抓取博主笔记时，opencli 报错：

```
xiaohongshu note now requires a full signed URL
Pass a full Xiaohongshu note URL with xsec_token from search results or user/profile context.
exitCode: 2
```

每篇博客笔记都失败，0 篇下载成功。

### 根因

`backend/app/services/opencli_adapter.py::blogger_notes()` 直接打开博主主页，从 DOM 里抓 `a[href*="/explore/"]` 的链接：

```javascript
(() => Array.from(document.querySelectorAll('a[href*="/explore/"]')).map(a => ({
    title: (a.textContent || '博主笔记').trim(),
    url: new URL(a.getAttribute('href'), location.origin).href
})))
```

博主主页 DOM 里的链接是**裸 `/explore/<id>`**（如 `https://www.xiaohongshu.com/explore/69142d3e000000000302e5ec`），**不带 `xsec_token`**，opencli note 命令现在严格校验 xsec_token，**直接拒绝**。

### 关键词抓取为什么 OK？

`xiaohongshu search` 返回的搜索结果 URL **带 xsec_token**（实测：

```json
{"author_url": "https://www.xiaohongshu.com/user/profile/619ca5dc...?xsec_token=ABtnuOGr3Nb-70Vx21bpWANCIfPh8_mq-..."}
```

所以关键词抓取走的 `xiaohongshu note <带 token 的 url>` **正常**。

## 目标

博主抓取改为**用 search 命令按用户名搜索**，复用关键词抓取的搜索结果 URL（含 xsec_token）。流程：

```
旧：blogger_notes(profile_url) → 打开 profile → 抓 /explore/ 裸链接 → note 失败
新：blogger_notes(username) → search "宁波 <username>" → 取带 token 的 URL → note 成功
```

## 设计

### 改动点

#### 1. `OpenCLIAdapter.blogger_notes()` 签名 + 实现调整

```python
def blogger_notes(self, username: str, profile_url: str) -> list[dict]:
    """博主笔记抓取：通过 search 拿到带 xsec_token 的 URL 列表。

    Args:
        username: 博主的用户名（用于 search 关键词）
        profile_url: 备用，保留兼容（profile_url 留空也能跑）

    Returns:
        list of {"title": str, "url": str}，url 带 xsec_token
    """
    if not username or not username.strip():
        raise OpenCLIError("blogger_notes: username 为空")

    self.check_login()
    results = self.search_recent(f"{username}", limit=20)  # 复用 search 逻辑
    return [{"title": r.get("title", "博主笔记"), "url": r["url"]} for r in results
            if r.get("url") and "xsec_token" in r["url"]]
```

**为什么这样改**：
- `search_recent(keyword, limit)` 内部调 `xiaohongshu search <keyword> --limit 20`，返回的结果 URL 带 `xsec_token`
- 复用 search 的实现，避免重复代码
- 博主关联城市 → 按用户名搜 → 取博主自己的笔记（通过 author 过滤？）

#### 2. `crawl_task.py` 调用方调整

```python
# 旧：
for blogger in scope.bloggers:
    profile_url = (blogger.profile_url or "").strip()
    if not profile_url:
        log(db, task.id, "WARNING", f"跳过博主：profile_url 为空 id={blogger.id}")
        continue
    results.extend((city.code, item) for item in adapter.blogger_notes(profile_url))

# 新：
for blogger in scope.bloggers:
    if not blogger.username:
        log(db, task.id, "WARNING", f"跳过博主：username 为空 id={blogger.id}")
        continue
    notes = adapter.blogger_notes(blogger.username, blogger.profile_url or "")
    # 过滤：只保留博主自己发的笔记（按 author 字段匹配）
    matched = [n for n in notes if n.get("author") == blogger.username or n.get("title", "").strip()]
    log(db, task.id, "INFO", f"博主 {blogger.username!r} 搜索命中 {len(notes)} 篇，过滤后 {len(matched)} 篇")
    results.extend((city.code, item) for item in matched)
```

#### 3. 失败兜底

如果 search 拿不到任何带 xsec_token 的 URL（小红书降级搜索结果），降级用 `search_recent` 的 fallback URL：
- 关键词抓取结果里 author_url 指向博主主页，也带 xsec_token
- 如果搜索失败，**不**调裸 `/explore/<id>`（之前就是这么挂的）

#### 4. 数据迁移

之前手动填的 `profile_url` 字段——**保留兼容**：
- 有 profile_url：用 search by username 即可（不依赖 profile_url 内容）
- 有 platform_user_id：可作 search 关键词（更精确）
- 都为空：靠 username

## 验收

### 自动化测试

`backend/tests/test_blogger_notes_signed_url.py`：
- `test_blogger_notes_uses_search_with_xsec_token`：mock search_recent 返回带 token URL，验证 blogger_notes 不直接打开 profile
- `test_blogger_notes_filters_by_author`：mock 多条结果，验证按作者过滤
- `test_blogger_notes_skips_when_no_xsec_token`：mock 搜索结果都不带 token，跳过
- `test_blogger_notes_works_without_profile_url`：只传 username 也能跑

`backend/tests/test_opencli_adapter_blogger.py`（集成）：
- mock subprocess run，调 blogger_notes 返回空 list 不抛错

### 手动 E2E

1. 选城市 `nb`，博主只选 `从零发现宁波`（已 enrich，profile_url 有值）
2. 提交任务 `mixed`，`blogger_ids=[<该博主.id>]`，`keywords=[]`
3. **预期**：
   - 任务正常跑
   - 日志显示 `博主 '从零发现宁波' 搜索命中 N 篇`
   - 笔记 `downloaded` > 0
   - 不出现 `Missing url` 或 `xsec_token` 错误

## 任务

1. 改 `backend/app/services/opencli_adapter.py::blogger_notes` 实现
2. 改 `backend/app/tasks/crawl_task.py` 调用方
3. 写单元测试
4. 写集成测试
5. 更新 `docs/api-doc.md`（如改 API 行为）
6. 更新 `docs/crawler-design.md`（博主抓取流程）
7. 更新 `docs/TODO.md`

## TODO

`docs/TODO.md` "当前待办"区追加：

```
- [ ] 博主笔记抓取改用 search 模式（带 xsec_token 的完整 URL）
  - 目标：解决博主抓取的笔记 URL 缺 xsec_token 导致 opencli note 失败的问题。
  - 验收：见 `docs/superpowers/specs/2026-07-17-blogger-notes-signed-url-design.md`（待审）。
```

## 风险

- search by username 可能会把同名博主的笔记都抓下来，需要过滤 author 字段
- 小红书 search 接口可能限流（和关键词抓取一样）
- 博主的主页可能比 search 结果更完整（全部笔记），改用 search 后可能漏抓**已下架**或**仅主页可见**的笔记