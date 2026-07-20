# `user/profile` 笔记身份与重复抓取测试案例

## 自动化案例

1. 输入同一篇博主笔记的两个 `user/profile/<user-id>/<note-id>` URL，仅 token 不同。
2. 断言两者提取相同 `<note-id>`，且纯博主主页不能提取笔记 ID。
3. 数据库预置已处理笔记及旧签名 URL，再传入新签名 URL。
4. 断言预检查复用原记录、刷新有效 URL，不重复插入，不调用详情或下载。
5. 回归 explore、search_result、discovery/item 的身份识别。

## 验收命令

```bash
uv run --project backend pytest -q backend/tests/test_note_identity.py backend/tests/test_crawl_task_resilience.py
make test
make test-e2e
git diff --check
```

验收输出不得包含完整 `xsec_token`、Cookie 或其他登录凭据。

## 2026-07-20 验收结果

- 红测：身份规则与流水线复用测试 `2 failed, 1 passed`；失败原因分别为 `user/profile` 返回 `None`、已完成笔记继续进入详情阶段。
- 绿测：身份、任务韧性、执行权和自动停止回归 `30 passed`。
- 全量：后端 `215 passed, 1 skipped`；前端组件 `28 passed`；Playwright E2E `38 passed`；差异格式检查通过。
- 真实数据只读核对：任务 #7 的目标笔记存在且为 `PROCESSED`，新规则提取的 ID 与数据库 `platform_note_id` 一致。
- 安全：测试和验收结果未保存完整 URL、签名 token 或 Cookie。
