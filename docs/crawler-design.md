# 爬虫设计

## 爬虫工具

- **工具**：OpenCLI (`jackwener/OpenCLI`)
- **核心命令**：
  - `opencli xiaohongshu search --keyword "{keyword}" --limit {n}`
  - `opencli xiaohongshu note --url "{note_url}"`
  - `opencli xiaohongshu download "{note_url}" --output ./images`
- **登录态**：复用 Chrome 已登录 session，通过 CDP 连接

## 本地验证环境

### 启动 Chrome 并开启 CDP

**macOS：**

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/chrome-debug-profile" \
  --remote-allow-origins="*"
```

**Linux：**

```bash
google-chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/chrome-debug-profile" \
  --remote-allow-origins="*"
```

启动后，在 Chrome 中登录小红书。

### 设置环境变量并测试

```bash
export OPENCLI_CDP_ENDPOINT="http://localhost:9222"
opencli doctor
opencli xiaohongshu search --keyword "上海 周末活动" --limit 10 -f json
```

## 抓取流程

### 登录态与 Cookie 前置检查

每次搜索、笔记详情或图片下载前必须先调用 `opencli xiaohongshu whoami -f json`。OpenCLI 通过浏览器扩展从当前 Chrome 会话中获取并复用 Cookie；应用不得读取、打印、写入日志、写入数据库或保存 Cookie 明文。

若检查返回错误码 77 / `AUTH_REQUIRED`：

1. 当前抓取任务切换为 `PAUSED`。
2. 停止后续搜索、详情和下载命令。
3. 管理端提示用户在当前 Chrome 登录小红书。
4. 用户登录后点击“测试连接”或“重试”，系统重新执行 `whoami`。
5. 仅当登录检查通过后才恢复爬虫流程。

### 搜索筛选与滚动加载

关键词搜索不只依赖 OpenCLI adapter 的默认结果。登录检查通过后，浏览器流程必须：

1. 打开小红书搜索结果页。
2. 点击结果区右侧“筛选”。
3. 选择排序“最新”。
4. 读取当前城市的 `recent_filter`，选择“不限、一天内、一周内、半年内”中的对应原生选项；“不限”不点击时间选项。
5. 关闭筛选层或等待结果刷新。
6. 按配置多轮向下滚动，收集更多笔记卡片。
7. 若 OpenCLI 返回标准发布时间字段，则按城市配置的时间范围再次校验；浏览器原生筛选仍是主约束。

### 标题关键词硬过滤

- 每条关键词搜索结果记录触发搜索的关键词；同一 URL 的多个命中关键词合并后再去重。
- 仅当小红书笔记标题精确包含至少一个对应关键词时，才进入详情下载、OCR 和 MiniMax 提取。
- 中文按子串匹配，英文忽略大小写；只忽略标题与关键词两端空白，不做分词、同义词扩展或语义放宽。
- 标题不匹配时增加 `skipped_notes` 并写 INFO 日志，博主白名单结果不受关键词标题过滤。

滚动停止条件：达到 `XHS_SEARCH_TARGET_COUNT`；达到最大轮次；或连续 `XHS_SCROLL_STAGNANT_ROUNDS` 轮没有新增卡片。默认每轮下拉 800px、目标 50 条、最多 8 轮、连续 2 轮无新增即停止。

### 笔记详情滚动

打开笔记详情后同样执行多轮下拉，以触发正文展开、图片和延迟内容加载。详情页最多滚动 `XHS_DETAIL_SCROLL_MAX_ROUNDS` 轮；连续两轮正文、图片 URL 和互动字段没有新增时停止。每轮滚动后必须等待页面稳定，再重新读取 DOM/网络数据，不得复用滚动前的元素 ref。

```python
def run_keyword_crawl(task_id: int, city_code: str, keyword: str):
    # 1. 调用 OpenCLI 搜索
    result = opencli.run(
        "xiaohongshu", "search",
        f"--keyword", f"{city_name} {keyword}",
        f"--limit", str(SEARCH_LIMIT),
        "-f", "json"
    )
    
    # 2. 解析搜索结果
    notes = parse_search_result(result)

    # 2.1 浏览器筛选：最新 + 城市 recent_filter；多轮滚动加载到目标数量
    notes = collect_search_results_with_scroll(target=SEARCH_TARGET_COUNT)
    
    # 3. 过滤近 7 天笔记
    notes = filter_recent_notes(notes, days=7)
    
    # 4. 保存到 notes 表（待处理状态）
    save_notes(task_id, notes, city_code, keyword)
    
    # 5. 间隔 10-15 秒
    time.sleep(random.randint(10, 15))
```

## 笔记详情下载

### 日期任务归档

阶段一本地文件统一按任务开始日期归档，不再把图片和导出文件分散保存：

```text
data/archive/YYYY-MM-DD/task-{task_id}/
├── source.md
├── activities.md
├── activities.xlsx
└── images/
```

- `source.md` 保存笔记标题、正文、原文链接及逐图 OCR 文字。
- `activities.md` 与 `activities.xlsx` 每一项/每一行对应一个具体活动。
- 图片保留原文件名；数据库 `note_images.storage_key` 保存相对 `data/` 的路径。
- 同一任务抓取多篇笔记时，图片文件名必须包含笔记 ID，避免冲突。

### 一篇笔记拆分多个活动

PaddleOCR 对每张图片逐字识别后，系统以 `[IMAGE n]` 标记合并标题、正文和 OCR 文本。MiniMax-M3 必须返回 `activities` 数组；每个元素包含活动名称、时间、地点、费用、类型、摘要、置信度和 `source_image_indexes`。每个具体活动独立写入 `activities`，并共同保留原始笔记 `source_url`。

缺少时间或地点的条目仍然入库并标记 `NEEDS_REVIEW`；不得把整篇合集笔记降维为一条活动。

模型日期先经过白名单格式归一化，再进入数据库转换。支持完整 ISO 8601、`M/D`、`M月D日` 等明确日期；`4/5` 会按任务当前年份补全，`2026-07-18T晚间` 等无法确定具体时刻的文本不会直接传给 `datetime.fromisoformat`，而是将时间置空并标记 `NEEDS_REVIEW`。该校验同时使用严格正则和解析器，禁止猜测“晚间”等模糊时刻。

长 OCR 文本的 M3 推理超时由 `.env` 的 `MINIMAX_TIMEOUT_SECONDS` 控制，阶段一默认 180 秒。

```python
def download_note_details(note_id: int, note_url: str):
    # 1. 调用 OpenCLI 获取笔记详情
    detail = opencli.run("xiaohongshu", "note", "--url", note_url, "-f", "json")
    
    # 2. 保存标题、正文、互动数据
    update_note(note_id, detail)
    
    # 3. 通过统一 Storage 接口保存图片
    images = opencli.run("xiaohongshu", "download", note_url, "--output", tmp_dir)
    for img_path in images:
        storage_key = storage.save(img_path)
        save_note_image(note_id, storage_key, original_url=...)
```

## 错误处理

阶段一按单篇笔记隔离处理。下载、OCR、提取各阶段的重试次数和间隔由 `.env` 的 `PIPELINE_STAGE_MAX_RETRIES`、`PIPELINE_STAGE_RETRY_DELAY_SECONDS` 控制；单篇笔记最终失败时记录 URL、错误和失败计数，清理该笔记的残缺数据后继续下一篇。认证失效仍立即暂停整个任务。任务级失败可由仪表盘“继续抓取”沿用原任务 ID 续跑，已有活动的旧笔记视为完成，残缺旧笔记先清理再重试。

任务实时记录发现、下载、OCR、提取和失败数量，并记录当前阶段与当前笔记。正常跑完但存在单篇失败时状态为 `COMPLETED_WITH_ERRORS`，不会误报为整批失败。

用户请求安全停止后，运行中任务进入 `STOP_REQUESTED`。worker 完成当前单篇笔记并保留其事务和归档，然后在下一篇开始前写入 `STOPPED` 并退出；禁止强制杀死当前处理导致半成品。`STOPPED` 可按原任务 ID 继续抓取。

| 错误码 | 含义 | 处理策略 |
|--------|------|----------|
| 0 | 成功 | 继续 |
| 66 | 结果为空 | 记录并跳过 |
| 69 | Browser Bridge 未连接 | 检查 Chrome/CDP，重试 |
| 75 | 超时 | 重试，最多 3 次 |
| 77 | 需要认证 | 暂停任务，发送告警 |
| 78 | 配置错误 | 记录错误，人工检查 |
| 130 | 用户中断 | 记录任务中断 |

## 反爬策略

- 关键词搜索间隔：10-15 秒
- 单账号每周搜索总量不超过 500 次（可配置）
- 使用 OpenCLI 的真实浏览器行为，避免低级别 HTTP 请求
- 遇到验证码或登录失效，立即暂停并告警
- 不抓取评论、私信等敏感内容
- 搜索和详情滚动均设置最大轮次及无新增提前停止条件，禁止无限滚动
