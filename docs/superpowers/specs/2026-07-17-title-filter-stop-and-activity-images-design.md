# 标题过滤、安全停止与活动图片详情设计

## 背景与目标

当前任务会把小红书搜索结果全部交给详情下载和活动提取。任务 #4 使用“活动、展览、信息差”三个关键词时，“信息差”等宽泛查询返回了抽奖、红包到期、发票截止等内容；系统没有在搜索结果与详情下载之间执行标题相关性校验，导致无关笔记进入 MiniMax 提取。

活动图片已经下载到 `data/archive/YYYY-MM-DD/task-{id}/images/`，`note_images.storage_key` 也保存了相对路径，但活动详情接口固定返回 `note: null` 和 `images: []`。前端详情抽屉沿用 Element Plus 默认宽度，无法舒适展示完整字段和图片。

本次实现三个目标：

1. 只有标题包含本次搜索关键词的小红书笔记才能进入下载与提取流程。
2. 运行中的抓取任务支持安全停止，并保留已经成功处理的数据。
3. 活动详情以更宽的抽屉展示，并在详情表格下显示来源页面图片。

## 标题相关性规则

### 匹配规则

- 每次关键词搜索结果必须携带触发该搜索的 `matched_keyword`。
- 采用标题精确子串包含规则：`matched_keyword in title`。
- 中文匹配忽略标题和关键词两端空白；英文匹配额外忽略大小写。
- 多关键词搜索结果按原文 URL 去重。同一 URL 可能命中多个搜索结果，只要标题包含任意一个对应关键词即可保留。
- 标题不包含任何对应关键词时，在详情下载之前跳过，不调用 `note`、`download`、OCR 或 MiniMax。
- 博主白名单抓取不来源于关键词搜索，不应用标题关键词过滤。

### 进度与日志

- `total_notes` 表示去重后的搜索发现数，包含随后因标题不匹配而跳过的结果。
- 新增 `skipped_notes` 记录标题不匹配数量，仪表盘与任务日志页展示“已跳过”。
- 每条跳过结果写入 INFO 日志，包含笔记 URL、标题和未命中的关键词，不记录 Cookie 或其他敏感数据。
- 任务进度百分比以 `extracted_notes + failed_notes + skipped_notes` 作为已完成数量。

### 提取边界

标题过滤是唯一的笔记相关性准入规则。MiniMax-M3 只负责从已通过标题校验的笔记正文和 OCR 文本中拆分具体活动，不再判断搜索结果是否相关，也不放宽标题规则。

## 安全停止任务

### API 与状态

- 新增 `POST /api/v1/tasks/{task_id}/stop`。
- 仅 `PENDING`、`RUNNING` 或 `STOP_REQUESTED` 任务可以停止；其他终态返回 `409`。
- `PENDING` 任务直接进入 `STOPPED`。
- `RUNNING` 任务进入 `STOP_REQUESTED`，表示正在等待当前笔记处理结束。
- worker 在搜索完成后、开始每一篇笔记前检查任务状态；发现 `STOP_REQUESTED` 后退出批次并写入 `STOPPED`。
- 当前正在处理的单篇笔记不强制中断，成功数据正常提交和归档，失败按原单篇隔离规则处理。
- `STOPPED` 为可续跑状态。原有 restart 接口扩展为接受 `FAILED` 和 `STOPPED`，沿用原任务 ID、参数和已完成进度。

### 前端交互

- 仪表盘最近任务状态为 `PENDING`、`RUNNING` 或 `STOP_REQUESTED` 时显示“停止抓取”。
- 点击按钮使用 Element Plus 确认框说明“当前笔记完成后停止，已处理数据会保留”。
- 请求中按钮显示 Element Plus Loading，成功后 Toast 提示“已请求安全停止”。
- `STOP_REQUESTED` 显示“正在停止”，`STOPPED` 显示“已停止”。
- `FAILED` 和 `STOPPED` 均显示“继续抓取”。

## 活动详情与来源图片

### 后端数据

- `GET /api/v1/activities/{activity_id}` 返回活动、关联笔记和该笔记的全部图片。
- `note` 至少包含 `id`、`title`、`content`、`source_url` 和 `status`。
- `images` 每项包含 `id`、`ocr_status`、`ocr_text` 和受保护的 `url`。
- 新增 `GET /api/v1/activities/{activity_id}/images/{image_id}`。接口必须验证登录、活动与图片属于同一笔记，并从配置的 `DATA_DIR` 下解析 `storage_key`；不存在或越界路径返回 `404`。
- 图片接口使用 `FileResponse` 返回本地文件，不公开整个归档目录，不接受调用方提供的文件路径。

### 前端布局

- 活动详情继续使用 Element Plus `ElDrawer`，桌面端宽度为 `70%`，窄屏使用 `95%`。
- 上方保留 `ElDescriptions` 活动字段表格，并增加原文标题和原文链接。
- 表格下方增加“来源页面图片”。使用 `ElImage` 展示响应式缩略图网格，启用 `preview-src-list` 多图预览和懒加载。
- 图片请求需要携带 Bearer Token。前端通过 Axios 读取 Blob 并创建对象 URL，关闭详情或重新加载时释放 URL，避免内存泄漏。
- 没有图片时显示 Element Plus Empty，不使用 Emoji 或自制图标。

## 数据库变更

- `crawl_tasks` 新增 `skipped_notes INTEGER NOT NULL DEFAULT 0`。
- 状态字段继续使用字符串，不新增状态表；新增合法值 `STOP_REQUESTED`、`STOPPED`。
- 不修改现有 `notes`、`note_images` 和 `activities` 关系。

## 错误处理

- 标题为空视为不匹配并计入跳过，不尝试下载详情。
- 单条日志写入失败不得改变标题过滤结果，但数据库提交失败仍按任务级错误处理。
- 停止请求重复调用保持幂等：`STOP_REQUESTED` 返回当前任务；`STOPPED` 返回 `409`，避免把历史完成任务误认为正在停止。
- 图片记录存在但文件丢失时返回 `404`，详情中的其他图片仍可查看。
- Blob 图片加载失败时单张显示失败占位，不影响详情其他字段。

## 测试与验收

### 后端

- 标题包含对应关键词时保留；不包含时跳过；多关键词任一命中时保留；博主结果不受过滤。
- 被跳过笔记不调用详情、下载、OCR 或 MiniMax，并增加 `skipped_notes` 与日志。
- `POST /tasks/{id}/stop` 覆盖 PENDING、RUNNING、STOP_REQUESTED、终态和未找到任务。
- worker 在当前笔记结束后停止下一篇，状态最终为 `STOPPED`；已成功数据保留。
- `STOPPED` 可按同一任务 ID 续跑。
- 活动详情返回关联笔记与图片；图片接口验证鉴权、归属、文件存在和路径边界。

### 前端组件与浏览器功能

- Dashboard 组件覆盖停止确认、请求中 Loading、状态中文映射和停止后继续。
- Activities 组件覆盖 70% 抽屉、笔记字段、图片网格、无图片状态和对象 URL 释放。
- Playwright 覆盖运行中任务点击安全停止、停止状态继续抓取、活动详情多图展示与点击预览。

### 验收标准

- 使用关键词“活动”时，标题不包含“活动”的搜索结果不会进入详情下载和活动表。
- 仪表盘能够安全停止运行任务，当前笔记处理完后计数不再增长，已入库数据仍可查询。
- 活动详情在桌面端明显加宽，详情表格下能看到该来源笔记下载的全部页面图片并支持预览。
