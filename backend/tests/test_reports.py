from datetime import datetime, timezone
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.activity import Activity
from app.models.note import Note, NoteImage
from app.api.v1.reports import GenerateRequest, select_notes
from app.services.report import format_activity_markdown, generate_note_markdown


@pytest.fixture
def headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin', 'permissions': ['*']})}"}


def activity(index: int, city: str = "shanghai", kind: str = "演出") -> Activity:
    return Activity(name=f"活动{index}", city_code=city, start_time=datetime(2025, 7, 20, 18, tzinfo=timezone.utc), end_time=datetime(2025, 7, 20, 22, tzinfo=timezone.utc), location="徐汇滨江", price="免费", type=kind, source_url=f"https://www.xiaohongshu.com/a/{index}", summary=f"活动{index}简介")


def post(db: Session, index: int, *, published_at: datetime | None = None, review_status: str = "APPROVED", title: str | None = None, city: str = "shanghai") -> Note:
    note = Note(task_id=1, platform_note_id=f"post-{index}", title=title or f"推文{index}", content="正文", source_url=f"https://www.xiaohongshu.com/explore/post-{index}", city_code=city, status="PROCESSED", review_status=review_status, published_at=published_at or datetime(2025, 7, 20, 12, tzinfo=timezone.utc), raw_data={})
    db.add(note); db.flush()
    item = activity(index); item.note_id = note.id; db.add(item)
    return note


def test_report_markdown_embeds_inline_image_and_no_raw_link_line(db_session: Session) -> None:
    note = post(db_session, 1)
    db_session.add(NoteImage(note_id=note.id, storage_key="images/post.jpg", original_url="", ocr_text="", ocr_status="success"))
    db_session.commit()
    entries = [select_notes(db_session, GenerateRequest(week="2025-W29", cities=["shanghai"]))[0]]
    md = generate_note_markdown("2025-W29", ["shanghai"], entries)
    assert "图片链接" not in md
    assert "![图片 1](/api/v1/reports/image/images/post.jpg)" in md


def test_report_markdown_falls_back_to_original_url_when_no_storage_key(db_session: Session) -> None:
    note = post(db_session, 2)
    db_session.add(NoteImage(note_id=note.id, storage_key="", original_url="https://img.example/direct.jpg", ocr_text="", ocr_status="success"))
    db_session.commit()
    entries = [select_notes(db_session, GenerateRequest(week="2025-W29", cities=["shanghai"]))[0]]
    md = generate_note_markdown("2025-W29", ["shanghai"], entries)
    assert "![图片 1](https://img.example/direct.jpg)" in md


def test_report_md_download_returns_zip_with_images(client: TestClient, db_session: Session, headers: dict[str, str]) -> None:
    """2026-08-18 行为变更：md 下载返回 zip（含 md + images/note_<id>/）。详见 test_report_zip_and_xlsx.py。"""
    note = post(db_session, 1)
    db_session.add(NoteImage(note_id=note.id, storage_key="images/post.jpg", original_url="", ocr_text="", ocr_status="success"))
    db_session.commit()
    report_id = client.post("/api/v1/reports/generate", json={"week": "2025-W29", "cities": ["shanghai"]}, headers=headers).json()["data"]["id"]
    response = client.get(f"/api/v1/reports/{report_id}/download?format=md", headers=headers)
    assert response.headers["content-type"].startswith("application/zip")
    assert ".zip" in response.headers["content-disposition"]


def test_report_image_route_serves_file_and_blocks_traversal(client: TestClient, db_session: Session, headers: dict[str, str]) -> None:
    from app.core.config import get_settings
    data_root = get_settings().data_dir.resolve()
    key = "reports_test_img.jpg"
    target = data_root / key
    target.write_bytes(b"\xff\xd8\xff\xe0fakejpeg")
    try:
        ok = client.get(f"/api/v1/reports/image/{key}")
        assert ok.status_code == 200
        assert ok.headers["content-type"].startswith("image/")
        traversal = client.get("/api/v1/reports/image/%2e%2e%2fapp.db")
        assert traversal.status_code == 404
    finally:
        target.unlink(missing_ok=True)


def test_activity_markdown_format() -> None:
    text = format_activity_markdown(activity(1))
    assert "#### 活动1" in text
    assert "**时间**：2025-07-20 18:00 - 22:00" in text
    assert "**地点**：徐汇滨江" in text and "**费用**：免费" in text
    assert "[小红书笔记](https://www.xiaohongshu.com/a/1)" in text


def test_generate_persists_and_regenerates_single_report(client: TestClient, db_session: Session, headers: dict[str, str]) -> None:
    post(db_session, 1)
    db_session.commit()
    payload = {"week": "2025-W29", "cities": ["shanghai"]}
    first = client.post("/api/v1/reports/generate", json=payload, headers=headers)
    second = client.post("/api/v1/reports/generate", json=payload, headers=headers)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert second.json()["data"]["note_count"] == 1
    assert second.json()["data"]["activity_count"] == 1


def test_generate_filters_approved_activities_to_selected_iso_week(client: TestClient, db_session: Session, headers: dict[str, str]) -> None:
    post(db_session, 10)
    post(db_session, 11, published_at=datetime(2025, 7, 21, 10, tzinfo=timezone.utc))
    post(db_session, 12, review_status="PENDING")
    db_session.commit()

    response = client.post("/api/v1/reports/generate", json={"week": "2025-W29", "cities": ["shanghai"]}, headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["activity_count"] == 1
    report_id = response.json()["data"]["id"]
    workbook = load_workbook(BytesIO(client.get(f"/api/v1/reports/{report_id}/download?format=xlsx", headers=headers).content), read_only=True)
    rows = list(workbook.active.iter_rows(values_only=True))
    assert [row[0] for row in rows[1:]] == ["推文10"]


def test_generate_rejects_week_without_approved_activities(client: TestClient, db_session: Session, headers: dict[str, str]) -> None:
    post(db_session, 20, review_status="PENDING")
    db_session.commit()

    response = client.post("/api/v1/reports/generate", json={"week": "2025-W29", "cities": ["shanghai"]}, headers=headers)

    assert response.status_code == 422
    assert response.json()["message"] == "所选城市和周次没有已审核推文，请先在活动管理中审核通过"


def test_generate_rejects_invalid_iso_week(client: TestClient, headers: dict[str, str]) -> None:
    response = client.post("/api/v1/reports/generate", json={"week": "2025-W99", "cities": ["shanghai"]}, headers=headers)

    assert response.status_code == 422
    assert response.json()["message"] == "周次格式无效，请使用 YYYY-Www"


def test_report_generation_city_is_optional(client: TestClient, db_session: Session, headers: dict[str, str]) -> None:
    # 城市可选：不传城市时按其它筛选条件（或全量）生成，不强制至少一个城市
    post(db_session, 1, city="nb")
    post(db_session, 2, city="shanghai")
    db_session.commit()
    assert client.post("/api/v1/reports/generate", json={"week": "2025-W29", "cities": []}, headers=headers).status_code == 200
    assert client.post("/api/v1/reports/generate", json={"week": "2025-W29", "cities": ["nb", "shanghai"]}, headers=headers).status_code == 200


def test_download_report_returns_zip_and_excel(client: TestClient, db_session: Session, headers: dict[str, str]) -> None:
    """2026-08-18 行为变更：md 下载返回 zip。"""
    post(db_session, 1)
    db_session.commit()
    report_id = client.post("/api/v1/reports/generate", json={"week": "2025-W29", "cities": ["shanghai"]}, headers=headers).json()["data"]["id"]
    md = client.get(f"/api/v1/reports/{report_id}/download?format=md", headers=headers)
    xlsx = client.get(f"/api/v1/reports/{report_id}/download?format=xlsx", headers=headers)
    assert md.status_code == 200 and md.headers["content-type"].startswith("application/zip")
    assert xlsx.status_code == 200 and "spreadsheetml.sheet" in xlsx.headers["content-type"]
    assert "2025-W29" in md.headers["content-disposition"] and "2025-W29" in xlsx.headers["content-disposition"]


def test_generate_same_filter_combination_updates_same_report(client: TestClient, db_session: Session, headers: dict[str, str]) -> None:
    post(db_session, 1, title="独立咖啡店")
    db_session.commit()
    payload = {"week": "2025-W29", "cities": ["shanghai"], "keywords": ["咖啡"]}
    first = client.post("/api/v1/reports/generate", json=payload, headers=headers)
    second = client.post("/api/v1/reports/generate", json=payload, headers=headers)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["data"]["id"] == second.json()["data"]["id"]


def test_generate_different_filter_combination_creates_new_report(client: TestClient, db_session: Session, headers: dict[str, str]) -> None:
    post(db_session, 1, title="独立咖啡店")
    post(db_session, 2, title="手作奶茶店")
    db_session.commit()
    base = {"week": "2025-W29", "cities": ["shanghai"]}
    a = client.post("/api/v1/reports/generate", json={**base, "keywords": ["咖啡"]}, headers=headers)
    b = client.post("/api/v1/reports/generate", json={**base, "keywords": ["奶茶"]}, headers=headers)
    assert a.status_code == 200 and b.status_code == 200
    assert a.json()["data"]["id"] != b.json()["data"]["id"]
    assert a.json()["data"]["name"] != b.json()["data"]["name"]


def test_generate_report_name_is_auto_built(client: TestClient, db_session: Session, headers: dict[str, str]) -> None:
    post(db_session, 1, title="独立咖啡店")
    db_session.commit()
    resp = client.post("/api/v1/reports/generate", json={"week": "2025-W29", "cities": ["shanghai"], "keywords": ["咖啡", "奶茶"]}, headers=headers)
    assert resp.status_code == 200
    name = resp.json()["data"]["name"]
    assert "2025-W29" in name and "咖啡" in name and "奶茶" in name


def test_list_reports_returns_name_and_filter_conditions(client: TestClient, db_session: Session, headers: dict[str, str]) -> None:
    post(db_session, 1, title="独立咖啡店")
    db_session.commit()
    client.post("/api/v1/reports/generate", json={"week": "2025-W29", "cities": ["shanghai"], "keywords": ["咖啡"]}, headers=headers)
    rows = client.get("/api/v1/reports", headers=headers).json()["data"]
    assert len(rows) == 1
    assert rows[0]["name"]
    assert rows[0]["keywords"] == ["咖啡"]
