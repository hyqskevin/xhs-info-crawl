# 测试用例：字段提取管道 (Field Extraction Pipeline)

> 阶段一固定链路：PaddleOCR 负责图片逐字识别，MiniMax-M3 负责结合标题、正文与 OCR 文本进行结构化字段提取；MiniMax-M3 不替代 PaddleOCR。

## 测试环境
- **框架**: pytest 7.x
- **语言**: Python 3.11
- **Mock 策略**: Mock MiniMax API 调用，Mock DB 查询
- **被测模块**: `backend/app/services/extraction.py`

## Mock 依赖

```python
@pytest.fixture
def mock_minimax():
    with patch("backend.app.services.extraction.minimax_client") as mock:
        yield mock

@pytest.fixture
def mock_db():
    with patch("backend.app.core.database.get_session") as mock:
        yield mock
```

---

## TC-EXTRACT-001: 规则提取 - 日期识别

**优先级**: P0
**类型**: 单元测试
**被测函数**: `extract_date_from_text(text)`

### Given
- 文本: "活动时间：2025年7月20日 18:00-22:00"
- 无 LLM 调用

### When
调用 `extract_date_from_text(text)`

### Then
- 返回 `{"start_time": "2025-07-20T18:00:00", "end_time": "2025-07-20T22:00:00"}`
- 置信度 > 0.9

```python
def test_regex_extracts_full_date_range():
    """规则应能提取完整日期和时间范围"""
    text = "活动时间：2025年7月20日 18:00-22:00"

    result = extract_date_from_text(text)

    assert result["start_time"] == "2025-07-20T18:00:00"
    assert result["end_time"] == "2025-07-20T22:00:00"
    assert result["confidence"] > 0.9
```

---

## TC-EXTRACT-002: 规则提取 - 多种日期格式

**优先级**: P0
**类型**: 参数化测试
**被测函数**: `extract_date_from_text(text)`

### Given
多种日期格式的文本

### When
调用 `extract_date_from_text`

### Then
每种格式都能正确解析

```python
@pytest.mark.parametrize("text,expected_start,expected_end", [
    ("7.20 周六 18:00-22:00", "2025-07-20T18:00:00", "2025-07-20T22:00:00"),
    ("7月20日-7月22日", "2025-07-20T00:00:00", "2025-07-22T23:59:59"),
    ("本周六下午2点", "2025-07-19T14:00:00", None),
    ("2025/07/20 晚上8点开始", "2025-07-20T20:00:00", None),
    ("7.20 - 8.15 每日 10:00-18:00", "2025-07-20T10:00:00", "2025-08-15T18:00:00"),
    ("下周三", "2025-07-23T00:00:00", None),  # 假设当前为 2025-07-16
])
def test_multiple_date_formats(text, expected_start, expected_end):
    """应支持多种日期格式"""
    with patch("backend.app.services.extraction.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2025, 7, 16)
        result = extract_date_from_text(text)

    assert result["start_time"] == expected_start
    if expected_end:
        assert result["end_time"] == expected_end
```

---

## TC-EXTRACT-003: 规则提取 - 地点和费用

**优先级**: P0
**类型**: 单元测试
**被测函数**: `extract_location(text)`, `extract_price(text)`

### Given
- 文本: "地点：徐汇滨江龙腾大道，免费入场，无需预约"

### When
调用 `extract_location` 和 `extract_price`

### Then
- location = "徐汇滨江龙腾大道"
- price = "免费"

```python
def test_extract_location_and_price():
    """应提取地点和费用信息"""
    text = "地点：徐汇滨江龙腾大道，免费入场，无需预约"

    location = extract_location(text)
    price = extract_price(text)

    assert "徐汇滨江" in location
    assert price == "免费"
```

---

## TC-EXTRACT-004: 规则提取失败 → LLM 兜底

**优先级**: P0
**类型**: 单元测试
**被测函数**: `extract_activity_fields(note_id)`

### Given
- 正文 + OCR 文字中包含不规范的日期表述
- 规则提取返回低置信度（< 0.5）
- MiniMax API 可用

### When
调用 `extract_activity_fields(note_id)`

### Then
- 规则提取先执行
- 置信度低时自动调用 MiniMax API
- LLM 返回结构化的活动字段
- 最终置信度取 LLM 返回的置信度

```python
def test_llm_fallback_when_rules_low_confidence(mock_minimax, mock_db):
    """规则置信度低时应调用 LLM 兜底"""
    mock_db.query.return_value.filter.return_value.first.return_value = {
        "id": 1,
        "title": "周末好去处推荐",
        "content": "这周六下午有个超棒的活动在滨江那边，不要钱！",
        "ocr_combined_text": ""
    }
    mock_minimax.chat.return_value = {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "name": "滨江周末活动",
                    "start_time": "2025-07-19T14:00:00",
                    "location": "徐汇滨江",
                    "price": "免费",
                    "type": "户外活动",
                    "confidence": 0.75
                })
            }
        }]
    }

    result = extract_activity_fields(1)

    assert result["name"] == "滨江周末活动"
    assert result["confidence"] == 0.75
    mock_minimax.chat.assert_called_once()
```

---

## TC-EXTRACT-005: 关键字段缺失 → NEEDS_REVIEW

**优先级**: P0
**类型**: 单元测试
**被测函数**: `extract_activity_fields(note_id)`

### Given
- 正文只提到"有一个活动"，无日期、无地点
- 规则和 LLM 都无法提取日期

### When
调用 `extract_activity_fields(note_id)`

### Then
- 活动状态 = "NEEDS_REVIEW"
- 缺失字段列表：["start_time", "location"]
- 活动仍被创建，但标记需人工审核

```python
def test_missing_key_fields_marks_needs_review(mock_minimax):
    """关键字段缺失应标记为 NEEDS_REVIEW"""
    mock_minimax.chat.return_value = {
        "choices": [{"message": {"content": json.dumps({
            "name": "神秘活动",
            "start_time": None,
            "location": None,
            "price": "未知",
            "type": "其他",
            "confidence": 0.3
        })}}]
    }

    result = extract_activity_fields(1)

    assert result["status"] == "NEEDS_REVIEW"
    assert "start_time" in result["missing_fields"]
    assert "location" in result["missing_fields"]
```

---

## TC-EXTRACT-006: MiniMax API 调用失败处理

**优先级**: P1
**类型**: 单元测试
**被测函数**: `extract_activity_fields(note_id)`

### Given
- 规则提取置信度低
- MiniMax API 调用超时或返回 5xx

### When
调用 `extract_activity_fields(note_id)`

### Then
- 降级使用规则提取的结果
- 活动状态 = "NEEDS_REVIEW"
- 日志记录 LLM 调用失败
- 不抛出异常中断管道

```python
def test_llm_failure_falls_back_to_rules(mock_minimax):
    """LLM 失败应降级使用规则结果"""
    mock_minimax.chat.side_effect = MiniMaxAPIError("timeout")

    result = extract_activity_fields(1)

    assert result["status"] == "NEEDS_REVIEW"
    assert result["extraction_method"] == "rules_only"
    # 不抛出异常
```

---

## TC-EXTRACT-007: 活动类型分类

**优先级**: P0
**类型**: 参数化测试
**被测函数**: `classify_activity_type(name, content)`

### Given
不同类型活动的名称和内容

### When
调用 `classify_activity_type`

### Then
正确分类

```python
@pytest.mark.parametrize("name,content,expected_type", [
    ("夏日音乐节", "live house 乐队", "演出"),
    ("当代艺术展", "美术馆 画廊", "展览"),
    ("周末市集", "手工 摊位 摆摊", "市集"),
    ("读书分享会", "书店 分享 讲座", "沙龙"),
    ("瑜伽体验课", "健身 运动 课程", "运动"),
    ("亲子烘焙", "亲子 儿童 手工", "亲子"),
])
def test_activity_type_classification(name, content, expected_type):
    """应正确分类活动类型"""
    result = classify_activity_type(name, content)
    assert result == expected_type
```

---

## TC-EXTRACT-008: 完整管道 - 从笔记到多个具体活动

**优先级**: P0
**类型**: 集成测试
**被测函数**: `process_note_to_activity(note_id)`

### Given
- 一篇合集笔记，包含标题、正文、3 张图片的 OCR 文字
- 图片分别描述音乐会、市集和讲座

### When
调用 `process_note_to_activities(note_id)`

### Then
- 创建 3 条 activity 记录，不创建“合集笔记”占位活动
- 每条记录写入 `note_id`、原文 `source_url` 和 `source_image_indexes`
- 信息完整的记录为 `RAW`，缺少时间或地点的记录为 `NEEDS_REVIEW`

## TC-EXTRACT-009: MiniMax-M3 多活动结构化输出

**Given**：标题、正文和带 `[IMAGE n]` 标记的 OCR 文本包含多个活动。

**Then**：MiniMax-M3 返回 `{ "activities": [...] }`；系统拒绝非数组根结构，并对每个元素单独校验和归一化。
- confidence >= 0.5

```python
def test_full_pipeline_creates_activity(mock_db):
    """端到端：笔记 → 活动"""
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        {  # note
            "id": 1, "title": "周末音乐节推荐",
            "content": "7月20日徐汇滨江，免费户外音乐节，18:00开始",
            "source_url": "https://www.xiaohongshu.com/...",
            "city_code": "shanghai"
        },
        [  # note_images with ocr
            {"id": 1, "ocr_text": "音乐节 徐汇滨江 7.20"},
            {"id": 2, "ocr_text": "免费入场"},
            {"id": 3, "ocr_text": ""}
        ]
    ]

    activity = process_note_to_activity(1)

    assert activity.name == "周末音乐节推荐"
    assert activity.city_code == "shanghai"
    assert activity.status == "RAW"
```

---

## 测试运行命令

```bash
pytest tests/test_extraction.py -v
pytest tests/test_extraction.py --cov=backend.app.services.extraction --cov-report=html
```
# 活动日期有效窗口补充案例

## TC-EXTRACT-DATE-WINDOW：活动日期有效窗口

- 任务参考日与未来第 60 天均允许入库，第 61 天与已结束历史活动跳过。
- 无年份日期仅在可推断到未来 60 天时补年，不能可靠推断时返回空值。
- 明确年份绝不擅自改年；明确越界时由窗口校验跳过。
- 日期为空的活动保存为 `NEEDS_REVIEW`，不回填当前时间，不进入周报。
- 同一笔记包含有效、历史、远期和未知日期活动时，逐活动隔离，不能中断整篇笔记。
