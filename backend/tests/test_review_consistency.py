"""审核规则一致性修复包测试（spec: 2026-07-27-review-consistency-fixes-design.md）。

覆盖四节：
- 7.1 批量审核跳过无有效子活动的推文并返回 skipped 明细
- 7.2 duplicate merge 幂等（非 pending 候选 409）
- 7.3 删除城市/博主时级联清理关联表
- 7.4 时间口径统一为北京墙钟（parse/week_bounds）
"""
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select

from app.core.security import create_access_token
from app.models.activity import Activity
from app.models.blogger_city import BloggerCity
from app.models.blogger_group import BloggerGroup, BloggerGroupMember
from app.models.config import Blogger, City, Keyword
from app.models.duplicate import NoteDuplicateCandidate
from app.models.keyword_group import KeywordGroup, KeywordGroupCity
from app.models.note import Note
from app.services.published_at import SHANGHAI, parse_published_at


def _auth() -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def _note(db, platform_id: str, title: str = "推文") -> Note:
    note = Note(
        task_id=1,
        platform_note_id=platform_id,
        title=title,
        content="",
        source_url=f"https://www.xiaohongshu.com/explore/{platform_id}",
        city_code="nb",
        status="DONE",
    )
    db.add(note)
    db.flush()
    return note


# ---------- 7.1 批量审核校验 ----------


def test_batch_approve_skips_notes_without_activities(client, db_session):
    with_activity = _note(db_session, "a" * 24)
    without_activity = _note(db_session, "b" * 24)
    db_session.add(Activity(note_id=with_activity.id, name="活动", city_code="nb", type="市集"))
    db_session.commit()

    resp = client.post(
        "/api/v1/notes/batch/approve",
        json={"ids": [with_activity.id, without_activity.id]},
        headers=_auth(),
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["approved_ids"] == [with_activity.id]
    skipped = data["skipped"]
    assert [item["id"] for item in skipped] == [without_activity.id]
    assert "无有效子活动" in skipped[0]["reason"]

    db_session.refresh(with_activity)
    db_session.refresh(without_activity)
    assert with_activity.review_status == "APPROVED"
    assert without_activity.review_status != "APPROVED"


def test_batch_approve_all_valid_keeps_legacy_response(client, db_session):
    note = _note(db_session, "c" * 24)
    db_session.add(Activity(note_id=note.id, name="活动", city_code="nb", type="市集"))
    db_session.commit()
    resp = client.post("/api/v1/notes/batch/approve", json={"ids": [note.id]}, headers=_auth())
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["approved_ids"] == [note.id]
    assert data["approved_count"] == 1
    assert data["skipped"] == []


# ---------- 7.2 merge 幂等 ----------


def _candidate(db, status: str = "pending") -> NoteDuplicateCandidate:
    note_a = _note(db, "d" * 24, "A")
    note_b = _note(db, "e" * 24, "B")
    candidate = NoteDuplicateCandidate(note_a_id=note_a.id, note_b_id=note_b.id, similarity=0.9, status=status)
    db.add(candidate)
    db.commit()
    return candidate


def test_merge_twice_returns_409(client, db_session):
    candidate = _candidate(db_session)
    first = client.post(f"/api/v1/duplicates/{candidate.id}/merge", json={"keep": "a"}, headers=_auth())
    assert first.status_code == 200
    second = client.post(f"/api/v1/duplicates/{candidate.id}/merge", json={"keep": "a"}, headers=_auth())
    assert second.status_code == 409


def test_merge_non_pending_candidate_returns_409(client, db_session):
    candidate = _candidate(db_session, status="ignored")
    resp = client.post(f"/api/v1/duplicates/{candidate.id}/merge", json={"keep": "a"}, headers=_auth())
    assert resp.status_code == 409


# ---------- 7.3 删除级联清理 ----------


def test_delete_city_cascades_associations(client, db_session):
    city = City(name="宁波", code="nb")
    db_session.add(city)
    db_session.flush()
    db_session.add(Keyword(word="市集", city_code="nb"))
    blogger = Blogger(username="博主甲")
    db_session.add(blogger)
    db_session.flush()
    db_session.add(BloggerCity(blogger_id=blogger.id, city_code="nb", enabled=True))
    group = KeywordGroup(name="组")
    db_session.add(group)
    db_session.flush()
    db_session.add(KeywordGroupCity(keyword_group_id=group.id, city_code="nb"))
    db_session.commit()

    resp = client.delete(f"/api/v1/settings/cities/{city.id}", headers=_auth())
    assert resp.status_code == 200
    assert db_session.scalars(select(Keyword).where(Keyword.city_code == "nb")).all() == []
    assert db_session.scalars(select(BloggerCity).where(BloggerCity.city_code == "nb")).all() == []
    assert db_session.scalars(select(KeywordGroupCity).where(KeywordGroupCity.city_code == "nb")).all() == []
    # 博主与组本身不受影响
    assert db_session.get(Blogger, blogger.id) is not None
    assert db_session.get(KeywordGroup, group.id) is not None


def test_delete_blogger_cascades_associations(client, db_session):
    blogger = Blogger(username="博主乙")
    db_session.add(blogger)
    db_session.flush()
    db_session.add(BloggerCity(blogger_id=blogger.id, city_code="nb", enabled=True))
    group = BloggerGroup(name="白名单组")
    db_session.add(group)
    db_session.flush()
    db_session.add(BloggerGroupMember(group_id=group.id, blogger_id=blogger.id))
    db_session.commit()

    resp = client.delete(f"/api/v1/settings/bloggers/{blogger.id}", headers=_auth())
    assert resp.status_code == 200
    assert db_session.get(Blogger, blogger.id) is None
    assert db_session.scalars(select(BloggerCity).where(BloggerCity.blogger_id == blogger.id)).all() == []
    assert db_session.scalars(select(BloggerGroupMember).where(BloggerGroupMember.blogger_id == blogger.id)).all() == []
    assert db_session.get(BloggerGroup, group.id) is not None


# ---------- 7.4 时间口径：北京墙钟 ----------


def test_parse_published_at_returns_beijing_wall():
    now_local = datetime(2026, 8, 10, 12, 0, tzinfo=SHANGHAI)
    result = parse_published_at("2025-07-20 18:30", now_local=now_local)
    # 必须是北京墙钟（+08:00），不是同一瞬间的 UTC 表示
    assert result.value is not None
    assert result.value.utcoffset() == timedelta(hours=8)
    assert result.value.replace(tzinfo=None) == datetime(2025, 7, 20, 18, 30)


def test_parse_published_at_relative_returns_beijing_wall():
    now_local = datetime(2026, 8, 10, 12, 0, tzinfo=SHANGHAI)
    result = parse_published_at("2天前", now_local=now_local)
    assert result.value is not None
    assert result.value.utcoffset() == timedelta(hours=8)
    assert result.value.replace(tzinfo=None) == datetime(2026, 8, 8, 12, 0)


def test_week_bounds_naive_monday_boundary():
    from app.api.v1.reports import week_bounds

    start, end = week_bounds("2026-W31")  # 2026-07-27 是周一
    assert start.tzinfo is None and end.tzinfo is None
    assert start == datetime(2026, 7, 27, 0, 0, 0)
    assert end == datetime(2026, 8, 3, 0, 0, 0)


def test_notes_list_date_filter_naive_bound(client, db_session):
    """日期过滤对北京墙钟存储的笔记按当日 00:00 起命中。"""
    note = _note(db_session, "f" * 24)
    note.published_at = datetime(2026, 7, 27, 0, 30)  # 北京墙钟，当日凌晨
    db_session.commit()
    resp = client.get("/api/v1/notes", params={"start_date": "2026-07-27", "end_date": "2026-07-27"}, headers=_auth())
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["data"]["items"]]
    assert note.id in ids


def test_activities_list_date_filter_naive_bound(client, db_session):
    note = _note(db_session, "0a" * 12)
    activity = Activity(note_id=note.id, name="凌晨活动", city_code="nb", type="市集")
    activity.start_time = datetime(2026, 7, 27, 0, 30)
    db_session.add(activity)
    db_session.commit()
    resp = client.get(
        "/api/v1/activities",
        params={"start_date": "2026-07-27", "end_date": "2026-07-27"},
        headers=_auth(),
    )
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["data"]["items"]]
    assert activity.id in ids
