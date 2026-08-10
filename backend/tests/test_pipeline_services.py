from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.crawler import AuthenticationRequired, VerificationRequired, is_verification_required
from app.services.dedup import classify_similarity, merge_activities, similarity_score
from app.services.extraction import extract_activity_fields
from app.services.ocr import OCRService


def test_dedup_high_edge_and_low_similarity() -> None:
    base = {"name": "上海夏日音乐节", "city_code": "shanghai", "start_time": "2025-07-20T18:00:00", "location": "徐汇滨江"}
    high = {**base, "name": "上海夏日音乐节2025"}
    edge = {**base, "name": "夏日音乐现场", "location": "徐汇"}
    low = {"name": "北京艺术展", "city_code": "beijing", "start_time": "2025-08-01T10:00:00", "location": "朝阳"}
    assert classify_similarity(similarity_score(base, high)) == "auto_merge"
    assert classify_similarity(similarity_score(base, edge)) in {"manual_review", "auto_merge"}
    assert classify_similarity(similarity_score(base, low)) == "distinct"


def test_dedup_merge_keeps_selected_and_combines_sources() -> None:
    left = {"id": 1, "name": "活动A", "related_note_ids": [1], "summary": "左"}
    right = {"id": 2, "name": "活动B", "related_note_ids": [2], "summary": "右"}
    merged = merge_activities(left, right, keep="a")
    assert merged["name"] == "活动A"
    assert merged["related_note_ids"] == [1, 2]


@pytest.mark.parametrize("text", ["7月20日 18:00 上海中心 免费 夏日音乐节", "2025-07-20 18:00 徐汇滨江 50元 音乐演出"])
def test_rules_extract_date_location_price_and_type(text: str) -> None:
    result = extract_activity_fields(text, now=datetime(2025, 7, 1), llm=None)
    assert result["start_time"] is not None
    assert result["location"]
    assert result["price"]
    assert result["type"] == "演出"


def test_extraction_uses_llm_fallback_and_marks_missing_required_fields() -> None:
    llm = lambda _: {"name": "隐秘活动", "start_time": "2025-07-20T10:00:00", "location": "静安"}
    assert extract_activity_fields("详情见海报", now=datetime(2025, 7, 1), llm=llm)["name"] == "隐秘活动"
    assert "status" not in extract_activity_fields("详情见海报", now=datetime(2025, 7, 1), llm=None)


def test_ocr_success_empty_failure_batch_and_confidence(tmp_path: Path) -> None:
    images = [tmp_path / "a.jpg", tmp_path / "b.jpg"]
    for image in images:
        image.write_bytes(b"image")
    service = OCRService(lambda path: [(f"文字-{path.stem}", 0.95), ("噪声", 0.2)], min_confidence=0.5)
    assert service.process(images[0])["text"] == "文字-a"
    assert len(service.process_many(images)) == 2
    assert OCRService(lambda _: [], 0.5).process(images[0])["text"] == ""
    assert OCRService(lambda _: (_ for _ in ()).throw(RuntimeError("fail")), 0.5).process(images[0])["status"] == "failed"


@pytest.mark.parametrize("message", [
    "captcha challenge detected",
    "请完成安全验证后继续访问",
    "请扫码验证",
    "risk verification required",
])
def test_explicit_xhs_verification_signals_are_classified(message: str) -> None:
    assert is_verification_required(message) is True
    assert isinstance(VerificationRequired("verify"), AuthenticationRequired)


@pytest.mark.parametrize("message", [
    "opencli command timeout",
    "验证结果已保存",
    "参数验证失败",
    "network connection reset",
])
def test_unrelated_messages_are_not_verification_signals(message: str) -> None:
    assert is_verification_required(message) is False


# ============================================================
# 非法日期不崩溃（2026-08-10 修复 "day is out of range for month"）
# ============================================================


@pytest.mark.parametrize("text", [
    "2月30日 上海中心 免费 春日市集",       # 2月无30日
    "11月31日 徐汇滨江 30元 秋季展览",      # 11月无31日
    "4月31日 静安公园 免费 樱花节",         # 4月无31日
    "6月31日 世纪公园 免费 夏夜音乐会",     # 6月无31日
    "9月31日 陆家嘴 50元 秋季艺术展",       # 9月无31日
    "2月29日 上海大剧院 80元 舞剧",         # 2025非闰年2月无29日
    "13月1日 上海中心 免费 异常月份",       # 月份越界
    "0月15日 上海中心 免费 异常月份",       # 月份越界
    "1月32日 上海中心 免费 异常日期",       # 日期越界
    "2026-02-30 上海中心 免费 异常日期",    # ISO 格式非法
    "2026-13-01 上海中心 免费 异常月份",    # ISO 格式月份越界
    "2.30 上海中心 免费 短点格式非法",      # 短点格式非法
])
def test_extract_activity_fields_tolerates_invalid_date(text: str) -> None:
    """非法日期不应抛 ValueError，应返回 start_time=None。"""
    result = extract_activity_fields(text, now=datetime(2025, 7, 1), llm=None)
    # 非法日期应被容忍：start_time 为 None，但其他字段仍正常提取
    assert "status" not in result, "不应抛异常"
    assert result["start_time"] is None, f"非法日期应返回 None，实际：{result['start_time']!r}"


def test_extract_activity_fields_still_parses_valid_date() -> None:
    """修复后合法日期仍应正常解析（无回归）。"""
    result = extract_activity_fields("7月20日 18:00 上海中心 免费 夏日音乐节", now=datetime(2025, 7, 1), llm=None)
    assert result["start_time"] is not None
    assert result["start_time"].startswith("2025-07-20")
    assert result["location"] == "上海中心"
    assert result["price"] == "免费"
    assert result["type"] == "演出"
