# `user/profile` 笔记稳定身份与重复抓取设计

> 状态：已通过持续授权审核，待实现。

## 1. 目标

小红书博主结果返回 `user/profile/<user-id>/<note-id>` 形式的签名 URL 时，系统必须稳定提取 `<note-id>`，并与同一笔记的旧 token URL 识别为同一条笔记。重复抓取已处理笔记时直接复用既有记录，不重复调用详情、下载或插入数据库。

## 2. 证据与根因

任务 `#7` 真实运行时，数据库已经存在 `platform_note_id=6a5739490000000016024c14` 的已处理笔记；再次取得同一篇笔记的新签名 URL 后，预检查没有命中旧记录，随后 INSERT 触发 `notes.platform_note_id` 唯一约束。

根因在 `backend/app/services/note_identity.py`：`extract_platform_note_id()` 仅识别 `explore`、`search_result` 和 `discovery/item` 路径，不识别博主抓取产生的 `user/profile/<user-id>/<note-id>`。创建 Note 时的兜底逻辑能从路径末段写入正确 note ID，但预检查因提取结果为 `None`，退化为完整 URL 比较；token 变化后便无法命中。

## 3. 设计

### 3.1 URL 身份规则

在统一身份提取函数中增加严格路径规则：

```text
/user/profile/<user-id>/<note-id>
```

只捕获 profile 路径的第二个标识段 `<note-id>`。纯博主主页 `/user/profile/<user-id>` 不得被误判为笔记。

查询参数不参与身份，因此同一路径下不同 `xsec_token`、`xsec_source` 必须得到相同 note ID。现有 `explore`、`search_result`、`discovery/item` 规则保持不变。

### 3.2 重复抓取行为

`prepare_existing_note()` 继续使用统一的 `extract_platform_note_id()`：

- 已存在且已处理：更新为本次有效签名 URL，返回 `True`，跳过详情、下载、OCR、提取和 INSERT；
- 已存在但未完成且无活动：按现有规则清理残留，再允许重新处理；
- 不存在：正常进入处理流水线。

不增加数据库迁移。现有记录的 `platform_note_id` 已由创建时路径末段兜底写入正确值，修复读取侧身份即可命中。

### 3.3 数据与安全

- 数据库仍以 `notes.platform_note_id` 唯一约束作为最终一致性保护；
- 不在日志或测试记录中输出完整签名 token；
- 不把纯用户主页当作笔记，避免用户 ID 与笔记 ID 混淆。

## 4. TDD

1. `user/profile/<user-id>/<note-id>` 能提取 note ID；不同 token 结果一致；
2. 纯 `/user/profile/<user-id>` 返回 `None`；
3. 已处理的旧 token `user/profile` 笔记遇到新 token 时，`prepare_existing_note()` 返回 `True` 并刷新 URL；
4. `process_note()` 遇到上述重复笔记时不调用 adapter，不增加下载/提取计数；
5. 现有 explore/search_result/discovery 身份测试与全量测试保持通过。

## 5. 验收

- 定向测试先因不支持 `user/profile` 路径而失败，再由最小身份规则修复转绿；
- 重复抓取不再触发 `notes.platform_note_id` 唯一约束；
- 后端、前端组件和 Playwright E2E 全量通过；
- 更新 `docs/TODO.md` 并独立提交。

## 6. 不在本次范围

- 不修改博主搜索、OpenCLI 页面解析和账号异常隔离；
- 不重新处理已经完成的笔记内容；
- 不修改模糊去重、活动去重或周报逻辑。
