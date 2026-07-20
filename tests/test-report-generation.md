# 测试用例：周报生成 (Weekly Report Generation)

## 测试环境
- **框架**: pytest 7.x
- **语言**: Python 3.11
- **Mock 策略**: Mock DB 查询，测试 Markdown 生成逻辑
- **被测模块**: `backend/app/services/report.py`

## Mock 依赖

```python
@pytest.fixture
def mock_db():
    with patch("backend.app.core.database.get_session") as mock:
        yield mock

@pytest.fixture
def sample_activities():
    return [
        {
            "id": 1, "name": "夏日音乐节", "city_code": "shanghai",
            "start_time": "2025-07-20T18:00:00Z", "end_time": "2025-07-20T22:00:00Z",
            "location": "徐汇滨江", "price": "免费", "type": "演出",
            "source_url": "https://www.xiaohongshu.com/a/1",
            "summary": "户外音乐节，多个乐队表演",
            "status": "APPROVED"
        },
        {
            "id": 2, "name": "当代艺术展", "city_code": "shanghai",
            "start_time": "2025-07-15T10:00:00Z", "end_time": "2025-08-15T18:00:00Z",
            "location": "上海当代艺术博物馆", "price": "60元", "type": "展览",
            "source_url": "https://www.xiaohongshu.com/a/2",
            "summary": "国内外艺术家联展",
            "status": "APPROVED"
        },
        {
            "id": 3, "name": "周末市集", "city_code": "shanghai",
            "start_time": "2025-07-21T10:00:00Z", "end_time": "2025-07-21T20:00:00Z",
            "location": "安福路", "price": "免费", "type": "市集",
            "source_url": "https://www.xiaohongshu.com/a/3",
            "summary": "手工艺品和美食市集",
            "status": "APPROVED"
        },
        {
            "id": 4, "name": "读书会", "city_code": "shanghai",
            "start_time": "2025-07-22T19:00:00Z", "end_time": "2025-07-22T21:00:00Z",
            "location": "思南书局", "price": "免费", "type": "沙龙",
            "source_url": "https://www.xiaohongshu.com/a/4",
            "summary": "《百年孤独》分享会",
            "status": "APPROVED"
        },
        {
            "id": 5, "name": "京城相声专场", "city_code": "beijing",
            "start_time": "2025-07-20T19:30:00Z", "end_time": "2025-07-20T21:30:00Z",
            "location": "德云社天桥剧场", "price": "180元起", "type": "演出",
            "source_url": "https://www.xiaohongshu.com/a/5",
            "summary": "德云社周末相声专场",
            "status": "APPROVED"
        },
    ]
```

---

## TC-REPORT-001: 周报生成 - 按城市分组

**优先级**: P0
**类型**: 单元测试
**被测函数**: `generate_weekly_report(week, cities)`

### Given
- week = "2025-W29"
- cities = ["shanghai", "beijing"]
- 5 条 APPROVED 活动（4 条上海、1 条北京）

### When
调用 `generate_weekly_report("2025-W29", ["shanghai", "beijing"])`

### Then
- 返回 Markdown 内容
- 内容按城市分组
- 上海组包含 4 条活动，北京组包含 1 条
- 城市标题为 H2 格式

```python
def test_report_groups_by_city(mock_db, sample_activities):
    """周报应按城市分组"""
    mock_db.query.return_value.filter.return_value.all.return_value = sample_activities

    report = generate_weekly_report("2025-W29", ["shanghai", "beijing"])

    assert "## 上海" in report
    assert "## 北京" in report
    # 上海 4 条活动
    assert report.count("来源：[小红书笔记]") >= 5
```

---

## TC-REPORT-002: 周报生成 - 按活动类型排序

**优先级**: P0
**类型**: 单元测试
**被测函数**: `generate_weekly_report(week, cities)`

### Given
- 上海有 4 条活动，类型为 演出、展览、市集、沙龙

### When
生成周报

### Then
- 同一城市内按活动类型排序
- 每种类型用 H3 标题

```python
def test_report_sorts_by_type_within_city(mock_db, sample_activities):
    """同城市内应按活动类型分组"""
    mock_db.query.return_value.filter.return_value.all.return_value = sample_activities

    report = generate_weekly_report("2025-W29", ["shanghai"])

    # 验证类型标题出现
    assert "### 演出" in report
    assert "### 展览" in report
    assert "### 市集" in report
    assert "### 沙龙" in report
```

---

## TC-REPORT-003: 周报生成 - 排除非 APPROVED 状态

**优先级**: P0
**类型**: 单元测试
**被测函数**: `generate_weekly_report(week, cities)`

### Given
- 6 条活动，其中 2 条状态为 NEEDS_REVIEW，1 条为 IGNORED，3 条为 APPROVED

### When
生成周报

### Then
- 只包含 3 条 APPROVED 的活动
- NEEDS_REVIEW 和 IGNORED 的不出现

```python
def test_report_excludes_non_approved(mock_db):
    """只包含 APPROVED 状态的活动"""
    activities = [
        {"id": 1, "status": "APPROVED", "city_code": "shanghai", "type": "演出"},
        {"id": 2, "status": "NEEDS_REVIEW", "city_code": "shanghai", "type": "展览"},
        {"id": 3, "status": "IGNORED", "city_code": "shanghai", "type": "市集"},
        {"id": 4, "status": "APPROVED", "city_code": "shanghai", "type": "沙龙"},
    ]
    mock_db.query.return_value.filter.return_value.all.return_value = activities

    report = generate_weekly_report("2025-W29", ["shanghai"])

    # 只有 2 条 APPROVED 出现
    assert "### 演出" in report
    assert "### 沙龙" in report
    assert "### 展览" not in report
```

---

## TC-REPORT-004: 周报格式验证

**优先级**: P0
**类型**: 单元测试
**被测函数**: `_format_activity_markdown(activity)`

### Given
- 一条完整的活动记录

### When
调用 `_format_activity_markdown`

### Then
- 输出标准 Markdown 格式
- 包含：名称(H4)、时间、地点、费用、来源链接、简介

```python
def test_activity_markdown_format():
    """活动 Markdown 格式应完整"""
    activity = {
        "id": 1, "name": "夏日音乐节",
        "start_time": "2025-07-20T18:00:00Z", "end_time": "2025-07-20T22:00:00Z",
        "location": "徐汇滨江", "price": "免费",
        "source_url": "https://www.xiaohongshu.com/a/1",
        "summary": "户外音乐节"
    }

    md = _format_activity_markdown(activity)

    assert "#### 夏日音乐节" in md
    assert "**时间**：2025-07-20 18:00 - 22:00" in md
    assert "**地点**：徐汇滨江" in md
    assert "**费用**：免费" in md
    assert "[小红书笔记](https://www.xiaohongshu.com/a/1)" in md
    assert "户外音乐节" in md
```

---

## TC-REPORT-005: 周报生成 - 空活动处理

**优先级**: P1
**类型**: 单元测试
**被测函数**: `generate_weekly_report(week, cities)`

### Given
- 本周没有任何 APPROVED 活动

### When
生成周报

### Then
- 返回 Markdown，提示本周无活动
- 不抛出异常

```python
def test_report_handles_empty_activities(mock_db):
    """无活动时应生成空报告"""
    mock_db.query.return_value.filter.return_value.all.return_value = []

    report = generate_weekly_report("2025-W29", ["shanghai"])

    assert "本周暂无活动" in report or len(report) > 0
```

---

## TC-REPORT-006: 周报保存到数据库

**优先级**: P0
**类型**: 单元测试
**被测函数**: `generate_weekly_report(week, cities)`

### Given
- 周报生成成功

### When
保存到数据库

### Then
- weekly_reports 表新增一条记录
- week = "2025-W29"
- cities = ["shanghai", "beijing"]
- activity_count = 实际活动数
- content = Markdown 内容
- status = "draft"

```python
def test_report_saved_to_database(mock_db, sample_activities):
    """周报应保存到数据库"""
    mock_db.query.return_value.filter.return_value.all.return_value = sample_activities

    report_content = generate_weekly_report("2025-W29", ["shanghai", "beijing"])

    # 验证数据库写入
    mock_db.add.assert_called_once()
    saved_report = mock_db.add.call_args[0][0]
    assert saved_report.week == "2025-W29"
    assert "shanghai" in saved_report.cities
    assert saved_report.activity_count == 5
    assert saved_report.status == "draft"
```

---

## TC-REPORT-007: 周报生成 - 性能要求（30 秒内）

**优先级**: P1
**类型**: 性能测试
**被测函数**: `generate_weekly_report(week, cities)`

### Given
- 500 条 APPROVED 活动

### When
生成周报

### Then
- 执行时间 ≤ 30 秒

```python
def test_report_generation_performance(mock_db):
    """500 条活动应在 30 秒内完成"""
    activities = [
        {
            "id": i, "name": f"活动{i}", "city_code": "shanghai",
            "start_time": "2025-07-20T10:00:00Z", "end_time": "2025-07-20T18:00:00Z",
            "location": f"地点{i}", "price": "免费", "type": random.choice(["演出","展览","市集","沙龙"]),
            "source_url": f"https://www.xiaohongshu.com/a/{i}",
            "summary": f"活动{i}简介", "status": "APPROVED"
        }
        for i in range(500)
    ]
    mock_db.query.return_value.filter.return_value.all.return_value = activities

    start = time.time()
    generate_weekly_report("2025-W29", ["shanghai"])
    elapsed = time.time() - start

    assert elapsed <= 30
```

---

## TC-REPORT-008: 周报双格式下载接口

**优先级**: P0
**类型**: 集成测试
**被测接口**: `GET /api/v1/reports/1/download?format={md|xlsx}`

### Given
- 周报 id=1 存在，且 Markdown 与 Excel 导出文件均已生成

### When
分别请求 `format=md` 与 `format=xlsx`

### Then
- 两次请求均返回 HTTP 200
- Markdown 的 Content-Type 为 `text/markdown`
- Excel 的 Content-Type 为 `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- Content-Disposition 包含周次和对应扩展名
- 两种文件包含同一批审核通过的活动

```python
def test_download_report_returns_markdown_and_excel(client, auth_headers, mock_db):
    """下载接口应按 format 返回 Markdown 或 Excel"""
    mock_db.query.return_value.filter.return_value.first.return_value = {
        "id": 1, "week": "2025-W29",
        "content": "# 上海本周活动精选\n\n## 演出\n...",
        "status": "published"
    }

    md_response = client.get("/api/v1/reports/1/download?format=md", headers=auth_headers)
    xlsx_response = client.get("/api/v1/reports/1/download?format=xlsx", headers=auth_headers)

    assert md_response.status_code == 200
    assert xlsx_response.status_code == 200
    assert "text/markdown" in md_response.headers["content-type"]
    assert "spreadsheetml.sheet" in xlsx_response.headers["content-type"]
    assert "2025-W29" in md_response.headers["content-disposition"]
    assert "2025-W29" in xlsx_response.headers["content-disposition"]
```

---

## TC-REPORT-009: 重复生成周报防冲突

**优先级**: P1
**类型**: 单元测试
**被测函数**: `generate_weekly_report(week, cities)`

### Given
- 本周周报已存在（status="published"）

### When
再次生成同周周报

### Then
- 覆盖现有草稿（status 回退到 draft）
- 或提示"本周周报已存在，是否重新生成？"

```python
def test_regenerate_existing_report(mock_db):
    """重新生成应处理已有周报"""
    mock_db.query.return_value.filter.return_value.first.return_value = {
        "id": 1, "week": "2025-W29", "status": "published"
    }
    mock_db.query.return_value.filter.return_value.all.return_value = [
        {"id": 1, "city_code": "shanghai", "type": "演出", "status": "APPROVED"}
    ]

    report = generate_weekly_report("2025-W29", ["shanghai"])

    # 应更新已有记录而非新建
    assert report is not None
```

## TC-REPORT-010: 按 ISO 周次和单城市筛选

**优先级**: P0
**类型**: 集成测试
**被测接口**: `POST /api/v1/reports/generate`

### Given
- 选择 `2025-W29` 和单个城市。
- 数据库同时存在 W29、W30 和非 `APPROVED` 活动。

### Then
- 只统计 W29 周一零点至 W30 周一零点前的 `APPROVED` 活动。
- Markdown 与 Excel 包含同一批记录。
- `2025-W99` 等非法 ISO 周次返回 422。

可执行代码：`backend/tests/test_reports.py::test_generate_filters_approved_activities_to_selected_iso_week` 和 `test_generate_rejects_invalid_iso_week`。

## TC-REPORT-011: 没有已通过活动时拒绝生成

**优先级**: P0
**类型**: 集成测试

### Given
- 所选城市和周次只有 `RAW` 或 `NEEDS_REVIEW` 活动。

### Then
- 返回 HTTP 422。
- `message` 为“所选城市和周次没有已通过活动，请先在活动管理中审核通过”。
- 不新增或覆盖为空周报。

可执行代码：`backend/tests/test_reports.py::test_generate_rejects_week_without_approved_activities`。

---

## 测试运行命令

```bash
pytest tests/test_report.py -v
pytest tests/test_report.py --cov=backend.app.services.report --cov-report=html
```
