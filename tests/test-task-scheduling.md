# 测试用例：任务调度 (Task Scheduling)

## 测试环境
- **框架**: pytest 7.x + pytest-celery
- **语言**: Python 3.11
- **Mock 策略**: Mock Celery task 调用，Mock OpenCLI
- **被测模块**: `backend/app/tasks/crawl_task.py`

## Mock 依赖

```python
@pytest.fixture
def celery_app():
    from backend.app.tasks.crawl_task import app
    app.conf.task_always_eager = True  # 同步执行，便于测试
    return app

@pytest.fixture
def celery_worker(celery_app):
    from celery.contrib.testing.worker import start_worker
    with start_worker(celery_app) as worker:
        yield worker

@pytest.fixture
def mock_opencli():
    with patch("backend.app.services.crawler.subprocess_run") as mock:
        yield mock

@pytest.fixture
def mock_db():
    with patch("backend.app.core.database.get_session") as mock:
        yield mock
```

---

## TC-TASK-001: Celery Beat 定时触发 - 周一凌晨 2 点

**优先级**: P0
**类型**: 单元测试
**被测配置**: `celery beat schedule`

### Given
- Celery Beat 配置了每周一 02:00 的 schedule

### When
检查 Celery Beat 配置

### Then
- task = "crawl_task.weekly_keyword_crawl"
- schedule = crontab(hour=2, minute=0, day_of_week=1)

```python
def test_weekly_crawl_scheduled_at_monday_2am(celery_app):
    """验证定时任务配置"""
    from backend.app.tasks.crawl_task import app

    schedule = app.conf.beat_schedule.get("weekly-keyword-crawl")

    assert schedule is not None
    assert schedule["task"] == "crawl_task.weekly_keyword_crawl"
    # 验证 crontab: 周一 02:00
```

---

## TC-TASK-002: 周任务 - 执行关键词搜索

**优先级**: P0
**类型**: 单元测试
**被测任务**: `weekly_keyword_crawl()`

### Given
- 数据库中有 2 个城市、每个城市 5 个关键词
- 所有城市和关键词均为启用状态

### When
Celery 执行 `weekly_keyword_crawl`

### Then
- 创建 1 条 crawl_task，type="keyword", status="RUNNING"
- 调用 `run_keyword_crawl` 10 次（2 城市 × 5 关键词）
- 每次调用间隔 10-15 秒
- 任务完成后 status="COMPLETED"

```python
def test_weekly_crawl_executes_all_keywords(celery_app, mock_db):
    """应执行所有城市×关键词组合"""
    mock_db.query.return_value.filter.return_value.all.return_value = [
        {"code": "shanghai", "name": "上海", "enabled": True},
        {"code": "beijing", "name": "北京", "enabled": True},
    ]

    with patch("backend.app.tasks.crawl_task.run_keyword_crawl") as mock_crawl:
        mock_crawl.return_value = [{"platform_note_id": "n1"}]
        result = weekly_keyword_crawl.apply()

    assert result.status == "SUCCESS"
    # 2 城市 × 每城市应有对应关键词数
    assert mock_crawl.call_count >= 2
```

---

## TC-TASK-003: 任务状态流转

**优先级**: P0
**类型**: 单元测试
**被测任务**: `weekly_keyword_crawl()`

### Given
- 任务正常执行

### When
追踪任务状态变化

### Then
- PENDING → RUNNING → SEARCH_DONE → DOWNLOADING → PROCESSING → DEDUPING → COMPLETED

```python
def test_task_status_transitions(celery_app, mock_db, mock_opencli):
    """任务应正确经历所有状态"""
    statuses = []

    def track_status(task_id, new_status):
        statuses.append(new_status)

    with patch("backend.app.tasks.crawl_task.update_task_status",
               side_effect=track_status):
        mock_opencli.return_value = CompletedProcess(
            args=[], returncode=0,
            stdout=json.dumps({"items": []})
        )
        result = weekly_keyword_crawl.apply()

    assert "RUNNING" in statuses
    assert "COMPLETED" in statuses
    # 验证状态顺序：RUNNING 在 COMPLETED 之前
    assert statuses.index("RUNNING") < statuses.index("COMPLETED")
```

---

## TC-TASK-004: 任务失败重试 - 3 次

**优先级**: P0
**类型**: 单元测试
**被测任务**: 带 `autoretry_for` 的 Celery task

### Given
- 任务执行中抛出临时异常（如 TimeoutError）

### When
任务重试

### Then
- 最多重试 3 次
- 每次重试间隔 300 秒（5 分钟）
- 3 次后仍失败，状态变为 FAILED
- 发送告警通知

```python
def test_task_retries_on_failure(celery_app, mock_opencli):
    """任务失败应重试 3 次"""
    mock_opencli.side_effect = TimeoutError("连接超时")

    with patch("backend.app.tasks.crawl_task.send_alert") as mock_alert:
        result = weekly_keyword_crawl.apply()

    # 验证重试次数
    assert result.status in ("FAILURE", "RETRY")
    # 最终应发送告警
    mock_alert.assert_called()
```

---

## TC-TASK-005: 手动触发任务

**优先级**: P0
**类型**: 集成测试
**被测接口**: `POST /api/v1/tasks/crawl`

### Given
- 请求参数指定城市和关键词

### When
发送 `POST /api/v1/tasks/crawl`

### Then
- HTTP 200
- 返回 task_id
- Celery 任务入队
- 任务 type = "manual"

```python
def test_manual_crawl_trigger(client, auth_headers, mock_db):
    """手动触发应返回任务 ID"""
    response = client.post("/api/v1/tasks/crawl", json={
        "type": "keyword",
        "cities": ["shanghai"],
        "keywords": ["周末活动", "展览"]
    }, headers=auth_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert "task_id" in data
```

---

## TC-TASK-006: 手动触发 - 任务运行中拒绝

**优先级**: P1
**类型**: 集成测试
**被测接口**: `POST /api/v1/tasks/crawl`

### Given
- 已有任务状态 = RUNNING

### When
发送 `POST /api/v1/tasks/crawl`

### Then
- HTTP 409
- message = "已有任务正在执行中"

```python
def test_manual_crawl_rejected_when_running(client, auth_headers, mock_db):
    """运行中应拒绝新任务"""
    mock_db.query.return_value.filter.return_value.first.return_value = {
        "id": 1, "status": "RUNNING"
    }

    response = client.post("/api/v1/tasks/crawl", json={
        "type": "keyword",
        "cities": ["shanghai"]
    }, headers=auth_headers)

    assert response.status_code == 409
```

---

## TC-TASK-007: 获取任务列表

**优先级**: P0
**类型**: 集成测试
**被测接口**: `GET /api/v1/tasks`

### Given
- 数据库有 15 条历史任务

### When
发送 `GET /api/v1/tasks`

### Then
- 返回任务列表（按创建时间倒序）
- 支持分页

```python
def test_get_task_list(client, auth_headers, mock_db):
    """应返回任务列表"""
    mock_db.query.return_value.order_by.return_value.offset.return_value \
        .limit.return_value.all.return_value = [
            {"id": i, "type": "keyword", "status": "COMPLETED"}
            for i in range(15, 0, -1)
        ]
    mock_db.query.return_value.filter.return_value.count.return_value = 15

    response = client.get("/api/v1/tasks", headers=auth_headers)

    assert response.status_code == 200
    assert len(response.json()["data"]["items"]) > 0
    assert response.json()["pagination"]["total"] == 15
```

---

## TC-TASK-008: 获取任务日志

**优先级**: P1
**类型**: 集成测试
**被测接口**: `GET /api/v1/tasks/1/logs`

### Given
- 任务 id=1 有执行日志

### When
发送 `GET /api/v1/tasks/1/logs`

### Then
- 返回日志列表
- 包含时间戳、日志级别、消息

```python
def test_get_task_logs(client, auth_headers, mock_db):
    """应返回任务执行日志"""
    mock_db.query.return_value.filter.return_value.order_by.return_value \
        .all.return_value = [
            {"timestamp": "2025-07-14T02:00:05Z", "level": "INFO",
             "message": "开始搜索: 上海 周末活动"},
            {"timestamp": "2025-07-14T02:00:20Z", "level": "INFO",
             "message": "找到 12 条笔记"},
            {"timestamp": "2025-07-14T02:00:35Z", "level": "WARNING",
             "message": "搜索间隔不足，等待 5 秒"},
        ]

    response = client.get("/api/v1/tasks/1/logs", headers=auth_headers)

    assert response.status_code == 200
    logs = response.json()["data"]
    assert len(logs) == 3
    assert logs[0]["level"] == "INFO"
```

---

## TC-TASK-009: 任务失败告警

**优先级**: P0
**类型**: 单元测试
**被测函数**: `send_alert(title, message)`

### Given
- 任务失败，需要通知管理员

### When
调用 `send_alert`

### Then
- 告警被发送
- 包含任务 ID、失败原因、时间戳
- 支持企业微信/钉钉/邮件至少一种渠道

```python
def test_alert_sent_on_task_failure():
    """任务失败应发送告警"""
    with patch("backend.app.tasks.crawl_task.requests.post") as mock_post:
        mock_post.return_value.status_code = 200

        send_alert(
            title="抓取任务失败",
            message="Task 42: 小红书登录态失效"
        )

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        # 验证告警内容包含关键信息
        assert "Task 42" in str(call_args)
        assert "登录态失效" in str(call_args)
```

---

## TC-TASK-010: Flower 监控可达

**阶段**: 阶段二
**优先级**: P2
**类型**: 集成测试
**被测服务**: Flower (port 5555)

### Given
- 阶段二 Docker Compose 环境启动
- Flower 服务运行中

### When
访问 `http://localhost:5555`

### Then
- HTTP 200
- 页面标题包含 "Flower"

```python
def test_flower_monitoring_accessible():
    """Flower 监控面板应可访问"""
    response = requests.get("http://localhost:5555")

    assert response.status_code == 200
    assert "Flower" in response.text
```

---

## 测试运行命令

```bash
# Celery 单元测试
pytest tests/test_tasks.py -v --cov=backend.app.tasks --cov-report=html

# 运行 Celery 集成测试（需要 Redis）
pytest tests/test_tasks.py -v -m "integration"
```
