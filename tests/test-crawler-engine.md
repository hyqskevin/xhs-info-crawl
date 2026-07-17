# 测试用例：爬虫引擎 (Crawler Engine)

## 测试环境
- **框架**: pytest 7.x + pytest-asyncio
- **语言**: Python 3.11
- **Mock 策略**: Mock OpenCLI 子进程调用，Mock Redis/DB 连接
- **被测模块**: `backend/app/services/crawler.py`

## Mock 依赖

```python
# conftest.py fixtures
@pytest.fixture
def mock_opencli():
    """Mock opencli CLI 命令执行结果"""
    with patch("backend.app.services.crawler.subprocess_run") as mock:
        yield mock

@pytest.fixture
def mock_db_session():
    """Mock 数据库会话"""
    with patch("backend.app.core.database.get_session") as mock:
        yield mock

@pytest.fixture
def mock_minio():
    """Mock MinIO 客户端"""
    with patch("backend.app.services.crawler.minio_client") as mock:
        yield mock
```

## 登录态前置门禁（所有爬虫案例共用）

- 所有搜索、详情和下载操作前必须先执行 `opencli xiaohongshu whoami -f json`。
- OpenCLI 通过浏览器扩展从当前 Chrome 登录会话复用 Cookie；系统不得打印、返回或持久化 Cookie 明文。
- 登录检查返回错误码 77 / `AUTH_REQUIRED` 时，任务立即进入 `PAUSED`，前端提示“请在 Chrome 登录小红书后重试”。
- 登录失败后禁止继续执行搜索、详情或下载命令。
- 用户完成登录后，通过“测试连接”或“重试任务”重新执行登录检查；只有检查通过才继续爬虫操作。

### TC-CRAWL-000：登录态检查与 Cookie 复用

**Given**：Chrome 已连接 OpenCLI 扩展；登录态可能有效或过期。

**When**：准备执行任意爬虫操作。

**Then**：

- 先执行 `whoami`；成功时才执行目标命令。
- 错误码 77 时任务暂停，目标命令调用次数为 0。
- 不记录 Cookie 明文，仅由 OpenCLI 在内存中复用浏览器会话。

### TC-CRAWL-000A：近一周筛选与自适应滚动

**Given**：登录检查通过，搜索结果页已加载。

**When**：执行关键词搜索采集。

**Then**：

- 点击右侧“筛选”，选择“最新”和“一周内”。
- 使用稳定的 CSS/DOM 选择器打开筛选面板并点击选项，不依赖会随页面刷新变化的 OpenCLI 数字引用。
- 默认目标 50 条，每轮下拉 800px，最多 8 轮。
- 连续 2 轮没有新增卡片时提前停止。
- 采集完成后按发布时间再次过滤近 7 天。

### TC-CRAWL-000B：详情页多轮下拉

**Given**：笔记详情页已打开。

**When**：采集正文、图片和互动字段。

**Then**：

- 每轮下拉后等待页面稳定并重新读取内容。
- 默认最多 8 轮。
- 连续 2 轮正文、图片和互动字段没有新增时停止。
- 达到完整内容条件后提前停止。

---

## TC-CRAWL-001: 关键词搜索 - 正常流程

**优先级**: P0
**类型**: 单元测试
**被测函数**: `run_keyword_crawl(task_id, city_code, keyword)`

### Given
- task_id = 1, city_code = "shanghai", keyword = "周末活动"
- OpenCLI 返回 10 条搜索结果（JSON 格式）
- 所有笔记发布时间在近 7 天内
- SEARCH_LIMIT = 50

### When
调用 `run_keyword_crawl(1, "shanghai", "周末活动")`

### Then
- `subprocess.run` 被调用，参数包含 `["opencli", "xiaohongshu", "search", "--keyword", "上海 周末活动", "--limit", "50", "-f", "json"]`
- 返回 10 条笔记记录
- 每条笔记包含 `platform_note_id`, `title`, `author_id`, `author_name`, `source_url`, `published_at`
- 所有笔记保存到数据库，status = "PENDING"
- 搜索间隔 `time.sleep` 被调用，参数在 [10, 15] 区间内

```python
def test_keyword_crawl_returns_notes(mock_opencli, mock_db_session):
    """关键词搜索应返回符合预期的笔记列表"""
    mock_opencli.return_value = CompletedProcess(
        args=[], returncode=0,
        stdout=json.dumps({
            "items": [
                {
                    "id": "note-001",
                    "title": "本周末上海展览推荐",
                    "author": {"id": "author-1", "name": "活动达人"},
                    "url": "https://www.xiaohongshu.com/...",
                    "published_at": "2025-07-10T10:00:00Z"
                }
            ]
        })
    )

    result = run_keyword_crawl(1, "shanghai", "周末活动")

    assert len(result) == 1
    assert result[0]["platform_note_id"] == "note-001"
    mock_opencli.assert_called_once()
    # 验证搜索间隔在 10-15 秒之间
    # 验证 city_code 到 city_name 的转换
```

---

## TC-CRAWL-002: 关键词搜索 - 过滤超过 7 天的笔记

**优先级**: P0
**类型**: 单元测试
**被测函数**: `filter_recent_notes(notes, days=7)`

### Given
- 3 条笔记，发布时间分别为 3 天前、7 天前（边界）、10 天前
- 当前时间: 2025-07-16T00:00:00Z

### When
调用 `filter_recent_notes(notes, days=7)`

### Then
- 返回 2 条笔记（3 天前 + 7 天前）
- 10 天前的笔记被过滤掉

```python
def test_filter_recent_notes_excludes_old_notes():
    """应过滤超过 7 天的笔记"""
    now = datetime(2025, 7, 16, tzinfo=timezone.utc)
    notes = [
        {"id": "1", "published_at": "2025-07-13T10:00:00Z"},  # 3 天前
        {"id": "2", "published_at": "2025-07-09T00:00:01Z"},  # 7 天前（边界内）
        {"id": "3", "published_at": "2025-07-06T10:00:00Z"},  # 10 天前
    ]

    with patch("backend.app.services.crawler.datetime") as mock_dt:
        mock_dt.now.return_value = now
        mock_dt.timezone = timezone
        result = filter_recent_notes(notes, days=7)

    assert len(result) == 2
    assert result[0]["id"] == "1"
    assert result[1]["id"] == "2"
```

---

## TC-CRAWL-003: 笔记详情下载 - 正常流程

**优先级**: P0
**类型**: 单元测试
**被测函数**: `download_note_details(note_id, note_url)`

### Given
- note_id = 1, note_url = "https://www.xiaohongshu.com/explore/xxx"
- OpenCLI note 命令返回详情 JSON（标题、正文、互动数据）
- OpenCLI download 命令返回 3 张图片路径
- MinIO 上传成功

### When
调用 `download_note_details(1, note_url)`

### Then
- `subprocess.run` 被调用两次（note + download）
- 笔记详情更新到数据库（title, content, likes, collects, comments）
- 3 张图片通过统一 Storage 接口保存，返回 storage_key；阶段一写入本地目录，阶段二写入 MinIO
- 3 条 `note_images` 记录创建，ocr_status = "pending"
- 图片、`source.md`、`activities.md` 与 `activities.xlsx` 最终位于同一个 `data/archive/YYYY-MM-DD/task-{task_id}/` 目录。

### TC-CRAWL-003A：日期归档与多活动导出

**Given**：任务在 2026-07-16 执行，一篇笔记识别出 3 个活动和 16 张图片。

**Then**：

- 归档目录为 `data/archive/2026-07-16/task-{task_id}/`。
- `images/` 包含 16 张原图。
- `source.md` 包含原文链接和逐图 OCR 文字。
- `source.md` 使用相对路径嵌入全部归档图片，例如 `![图片 1](images/note-id_01.jpg)`。
- `activities.md` 包含 3 个活动，并按 `source_image_indexes` 添加可点击的来源图片链接；`activities.xlsx` 包含表头和 3 行数据。
- 数据库生成 3 条活动，每条 `source_url` 均为原文链接。

```python
def test_download_note_details_stores_all_data(
    mock_opencli, mock_db_session, mock_minio
):
    """应下载笔记详情并存储图片"""
    mock_opencli.side_effect = [
        # note 命令结果
        CompletedProcess(args=[], returncode=0, stdout=json.dumps({
            "title": "夏日音乐节",
            "content": "周末去徐汇滨江看音乐节...",
            "likes": 120, "collects": 45, "comments": 23
        })),
        # download 命令结果
        CompletedProcess(args=[], returncode=0, stdout=json.dumps({
            "files": ["/tmp/img1.jpg", "/tmp/img2.jpg", "/tmp/img3.jpg"]
        }))
    ]
    mock_minio.upload.return_value = "xhs-images/note-001/img1.jpg"

    result = download_note_details(1, "https://www.xiaohongshu.com/...")

    assert result["title"] == "夏日音乐节"
    assert len(result["images"]) == 3
    assert mock_minio.upload.call_count == 3
```

---

## TC-CRAWL-004: 博主白名单抓取

**优先级**: P0
**类型**: 单元测试
**被测函数**: `run_blogger_crawl(task_id, blogger)`

### Given
- blogger = {"platform_user_id": "user-123", "username": "活动推荐官"}
- OpenCLI 用户主页返回 5 条近 7 天笔记

### When
调用 `run_blogger_crawl(1, blogger)`

### Then
- 返回 5 条笔记
- 笔记的 author_id = "user-123"
- 所有笔记保存到数据库

```python
def test_blogger_crawl_fetches_user_notes(mock_opencli, mock_db_session):
    """应按博主 ID 抓取其近期笔记"""
    mock_opencli.return_value = CompletedProcess(
        args=[], returncode=0,
        stdout=json.dumps({"items": [
            {"id": f"note-{i}", "title": f"活动推荐 {i}"}
            for i in range(5)
        ]})
    )

    result = run_blogger_crawl(1, {
        "platform_user_id": "user-123",
        "username": "活动推荐官"
    })

    assert len(result) == 5
    assert all(n["author_id"] == "user-123" for n in result)
```

---

## TC-CRAWL-005: 错误处理 - OpenCLI 超时（错误码 75）

**优先级**: P0
**类型**: 单元测试
**被测函数**: `_handle_opencli_error(returncode, context)`

### Given
- OpenCLI 返回 exit code 75（超时）
- 重试计数器 retry_count = 0

### When
调用错误处理

### Then
- 触发重试逻辑
- 重试次数 +1
- 日志记录 "OpenCLI timeout, retrying..."

```python
def test_opencli_timeout_triggers_retry():
    """超时应自动重试，最多 3 次"""
    error_handler = OpenCLIErrorHandler(max_retries=3)

    with patch.object(error_handler, "_retry") as mock_retry:
        error_handler.handle(75, {"task_id": 1})

    mock_retry.assert_called_once()
```

---

## TC-CRAWL-006: 错误处理 - 需要认证（错误码 77）

**优先级**: P0
**类型**: 单元测试
**被测函数**: `_handle_opencli_error(returncode, context)`

### Given
- OpenCLI 返回 exit code 77（需要认证）
- 当前任务状态 = RUNNING

### When
调用错误处理

### Then
- 任务状态更新为 PAUSED
- 发送告警通知
- 不触发重试

```python
def test_opencli_auth_error_pauses_task(mock_db_session):
    """登录态失效应暂停任务并告警"""
    error_handler = OpenCLIErrorHandler()

    with patch("backend.app.services.crawler.send_alert") as mock_alert:
        error_handler.handle(77, {"task_id": 1})

    # 验证任务状态变为 PAUSED
    mock_db_session.execute.assert_called()
    mock_alert.assert_called_once_with(
        "登录态失效",
        "Task 1 paused: 小红书登录 session 已过期，请重新登录"
    )
```

---

## TC-CRAWL-007: 错误处理 - 结果为空（错误码 66）

**优先级**: P1
**类型**: 单元测试
**被测函数**: `_handle_opencli_error(returncode, context)`

### Given
- OpenCLI 返回 exit code 66（结果为空）

### When
调用错误处理

### Then
- 记录日志 "No results found for keyword: {keyword}"
- 继续下一个关键词
- 不触发重试
- 不更新任务状态为失败

```python
def test_empty_result_skips_gracefully():
    """结果为空应跳过，不视为错误"""
    error_handler = OpenCLIErrorHandler()

    result = error_handler.handle(66, {
        "task_id": 1,
        "keyword": "周末活动"
    })

    assert result == "SKIP"
```

---

## TC-CRAWL-008: 搜索间隔控制

**优先级**: P1
**类型**: 单元测试
**被测函数**: `run_keyword_crawl` 中的 `time.sleep` 调用

### Given
- 配置的搜索间隔为 [10, 15] 秒

### When
连续执行两次关键词搜索

### Then
- 两次搜索之间调用 `time.sleep`
- sleep 参数在 [10, 15] 区间内

```python
def test_search_interval_is_respected():
    """关键词搜索之间必须有 10-15 秒间隔"""
    with patch("backend.app.services.crawler.time.sleep") as mock_sleep:
        run_keyword_crawl(1, "shanghai", "关键词1")
        run_keyword_crawl(2, "shanghai", "关键词2")

    sleep_arg = mock_sleep.call_args[0][0]
    assert 10 <= sleep_arg <= 15
```

---

## TC-CRAWL-009: 防并发 - 任务运行中不可重复触发

**优先级**: P1
**类型**: 单元测试
**被测函数**: `trigger_crawl_task(task_type, params)`

### Given
- 已有任务 task_id=1，status=RUNNING

### When
尝试触发新的相同类型任务

### Then
- 返回错误 "TASK_IN_PROGRESS"
- 不创建新任务

```python
def test_concurrent_crawl_prevented(mock_db_session):
    """运行中的任务不可重复触发"""
    mock_db_session.query.return_value.filter.return_value.first.return_value = {
        "id": 1, "status": "RUNNING"
    }

    with pytest.raises(TaskInProgressError) as exc:
        trigger_crawl_task("keyword", {"city": "shanghai"})

    assert "TASK_IN_PROGRESS" in str(exc.value)
```

---

## TC-CRAWL-010: 每周搜索次数限制

**优先级**: P1
**类型**: 单元测试
**被测函数**: `check_weekly_limit()`

### Given
- 配置的每周搜索上限 = 500
- 本周已执行 500 次搜索

### When
尝试执行第 501 次搜索

### Then
- 抛出 `WeeklyLimitExceededError`
- 任务暂停
- 日志记录 "本周搜索次数已达上限"

```python
def test_weekly_search_limit_enforced(mock_db_session):
    """超过每周 500 次搜索上限应拒绝执行"""
    mock_db_session.query.return_value.scalar.return_value = 500

    with pytest.raises(WeeklyLimitExceededError):
        check_weekly_limit()

    # 验证日志输出
```

---

## TC-CRAWL-011：模型日期归一化与模糊时间降级

- `4/5`、`4月5日` 等明确日期按任务当前年份归一化为 ISO 8601。
- `2026-07-18T晚间`、自由文本和非法日历日期不得直接调用 `fromisoformat`。
- 无法确定具体时间时 `start_time=null`，活动保留并标记 `NEEDS_REVIEW`。

对应自动化：`backend/tests/test_multi_activity_archive.py`。

## TC-CRAWL-012：单篇失败隔离与旧任务续跑

- 下载、OCR、提取阶段按环境变量配置重试，超过次数仅将当前笔记计入失败。
- 当前笔记残缺数据清理后继续下一篇；认证错误例外，必须暂停整批任务。
- 旧任务中已有活动的 `OCR_DONE` 笔记视为完成并改为 `PROCESSED`；没有活动的残缺笔记清理后重试。

对应自动化：`backend/tests/test_crawl_task_resilience.py`。

## TC-CRAWL-013：搜索标题必须包含对应关键词

- 关键词搜索结果记录对应关键词，多关键词命中按 URL 合并。
- 标题包含任一对应关键词才进入详情下载；不匹配结果增加 `skipped_notes` 并记录日志。
- 被跳过结果不得调用详情、图片下载、OCR 或 MiniMax；博主结果不执行此过滤。

对应自动化：`backend/tests/test_crawl_task_resilience.py`。

## 测试运行命令

```bash
# 运行爬虫模块测试
pytest tests/test_crawler.py -v

# 运行并生成覆盖率报告
pytest tests/test_crawler.py --cov=backend.app.services.crawler --cov-report=html
```
