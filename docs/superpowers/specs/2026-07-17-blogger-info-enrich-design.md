# 博主信息补全 + 仪表盘拦截（2026-07-17）

## 目标

用户在配置中心只填博主名字（不知道 xhs_id / 主页 URL）也能保存博主。
但博主抓取脚本需要 `profile_url` 才能调用 opencli 的 `blogger_notes`，
否则 `Missing url` 报错。本需求解决：

1. 配置中心博主列表对 `profile_url` 为空的博主展示"补充博主信息"按钮；
   点击后调用 `opencli xiaohongshu search` 找该用户最近的笔记，从 `author_url`
   提取 `user_id` 和 `profile_url` 回填数据库。
2. 仪表盘博主下拉里 `profile_url` 为空的博主标"待补充"；
   用户在提交任务时若选中这些博主，弹 `ElMessage` 警告并阻止提交，
   引导用户先到配置中心补全。

## 设计

### 后端

- 新增服务 `app/services/blogger_enricher.py`，导出 `enrich_bloggers(db, bloggers, *, search_runner, limit)`：
  - 只处理 `profile_url` 为空的博主；
  - 通过注入的 `search_runner`（可 mock）调 `opencli xiaohongshu search <username> -f json`；
  - 解析结果中 `author == username` 的 `author_url`，从中提取 `user_id` 和清理后的 `https://www.xiaohongshu.com/user/profile/{id}`；
  - `platform_user_id` 已存在时不覆盖（保留人工填的真实 ID），但 `profile_url` 仍补；
  - 同一关键词结果按 username 缓存，避免重复 search。

- 新增 API `POST /api/v1/settings/bloggers/{id}/enrich`：
  - 404：博主不存在
  - 200 + `message="博主信息已完整，无需补充"`：已配置完整
  - 422：`未找到匹配 '<username>' 的博主主页`
  - 503：opencli 异常
  - 成功后通过 `db.refresh` 返回最新的博主数据（带 `city_codes`）。

### 前端

- `frontend/src/api/client.ts` 增加 `enrichBlogger(id)`。
- `frontend/src/views/SettingsView.vue` 博主列表的操作列：
  - `profile_url` 为空时显示"补充博主信息"按钮（warning 色，MagicStick 图标）；
  - 点击调用 `enrichBlogger`，成功后 `ElMessage.success` + 重新 `load()`。
- `frontend/src/views/DashboardView.vue`：
  - `cityBloggers` computed 改为按 `city_codes`（多对多数组）过滤（之前是 `city_code`）；
  - 新增 `incompleteBloggers` computed：从已选的 `blogger_ids` 中筛 `profile_url` 为空的博主；
  - 博主 `ElOption` 模板显示"待补充"标记（右侧 warning 色 12px）；
  - `start()` 函数增加守卫：若有 incomplete 博主，ElMessage 警告并 return，不发起任务。

## 验收

后端（`backend/tests/`）：
- `test_blogger_enricher.py`：
  - `enrich_fills_profile_url_and_user_id_when_missing`：search 命中后回填
  - `enrich_skips_bloggers_that_already_have_profile_url`：已有 URL 不调用 search
  - `enrich_handles_search_no_match`：找不到匹配不改 DB
  - `enrich_skips_existing_platform_user_id`：platform_user_id 已存在不覆盖
- `test_settings_blogger_enrich_api.py`：
  - `enrich_returns_unchanged_when_profile_url_already_set`：200 + 不变数据
  - `enrich_fills_profile_url_when_missing`：回填成功
  - `enrich_422_when_no_match_in_search`：search 无匹配 → 422
  - `enrich_404_when_blogger_not_found`：博主不存在 → 404

前端（`frontend/src/views/`）：
- `DashboardView.spec.ts` 新增 `blocks task submission when selected blogger has no profile_url`
- `SettingsView.spec.ts` 已覆盖博主列表渲染

E2E（`tests/test-frontend-ui-e2e.md`）：补一条 "博客主信息不全拦截任务" 用例。

## API 文档

更新 `docs/api-doc.md` 增加 `POST /api/v1/settings/bloggers/{id}/enrich`。