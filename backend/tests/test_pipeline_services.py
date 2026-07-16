from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services.crawler import AuthenticationRequired, OpenCLIError, OpenCLITimeout, check_login, filter_recent_notes, map_opencli_error, search_notes
from app.services.dedup import classify_similarity, merge_activities, similarity_score
from app.services.extraction import extract_activity_fields
from app.services.ocr import OCRService
from app.services.task_lock import TaskAlreadyRunning, TaskLock


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
    assert extract_activity_fields("详情见海报", now=datetime(2025, 7, 1), llm=None)["status"] == "NEEDS_REVIEW"


def test_ocr_success_empty_failure_batch_and_confidence(tmp_path: Path) -> None:
    images = [tmp_path / "a.jpg", tmp_path / "b.jpg"]
    for image in images:
        image.write_bytes(b"image")
    service = OCRService(lambda path: [(f"文字-{path.stem}", 0.95), ("噪声", 0.2)], min_confidence=0.5)
    assert service.process(images[0])["text"] == "文字-a"
    assert len(service.process_many(images)) == 2
    assert OCRService(lambda _: [], 0.5).process(images[0])["text"] == ""
    assert OCRService(lambda _: (_ for _ in ()).throw(RuntimeError("fail")), 0.5).process(images[0])["status"] == "failed"


def test_crawler_filters_recent_notes_and_maps_typed_errors() -> None:
    now = datetime.now(timezone.utc)
    notes = [{"id": 1, "published_at": now.isoformat()}, {"id": 2, "published_at": (now - timedelta(days=8)).isoformat()}]
    assert [item["id"] for item in filter_recent_notes(notes, now=now, days=7)] == [1]
    assert isinstance(map_opencli_error(75), OpenCLITimeout)
    assert isinstance(map_opencli_error(77), AuthenticationRequired)
    assert isinstance(map_opencli_error(78), OpenCLIError)


def test_crawler_checks_login_before_search_and_pauses_on_auth_error() -> None:
    calls: list[list[str]] = []

    def runner(command: list[str]) -> dict[str, object]:
        calls.append(command)
        return {"ok": False, "error": {"exitCode": 77, "code": "AUTH_REQUIRED"}}

    with pytest.raises(AuthenticationRequired):
        search_notes("上海 周末活动", 3, runner)
    assert len(calls) == 1
    assert calls[0][1:3] == ["xiaohongshu", "whoami"]


def test_crawler_searches_only_after_login_check_passes() -> None:
    calls: list[list[str]] = []

    def runner(command: list[str]) -> dict[str, object]:
        calls.append(command)
        if command[2] == "whoami":
            return {"ok": True, "data": {"logged_in": True}}
        return {"ok": True, "data": [{"title": "周末活动"}]}

    assert check_login(runner) is True
    result = search_notes("上海 周末活动", 3, runner)
    assert result == [{"title": "周末活动"}]
    assert calls[-2][2] == "whoami"
    assert calls[-1][2] == "search"


def test_task_lock_prevents_concurrent_runs_and_releases() -> None:
    lock = TaskLock()
    with lock.acquire():
        with pytest.raises(TaskAlreadyRunning):
            with lock.acquire():
                pass
    with lock.acquire():
        assert lock.running
