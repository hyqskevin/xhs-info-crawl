"""仪表盘与周报需求对齐（spec: 2026-07-27-dashboard-and-report-alignment-design.md）。

- summary 的 weekly_* 口径修正为「本周」（北京 ISO 周）；
- summary 新增 recent_logs（最新 5 条任务日志）；
- DELETE /reports/{id} 删除周报，404 幂等。
"""
from datetime import datetime, timedelta, timezone

from app.core.security import create_access_token
from app.models.activity import Activity
from app.models.note import Note
from app.models.report import WeeklyReport
from app.models.task import TaskLog


def _auth() -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def _note(db, platform_id: str, created_at: datetime) -> Note:
    note = Note(
        task_id=1,
        platform_note_id=platform_id,
        title="t",
        content="",
        source_url=f"https://xhs.demo/{platform_id}",
        city_code="nb",
        status="DONE",
        created_at=created_at,
    )
    db.add(note)
    db.flush()
    return note


def test_summary_weekly_counts_only_this_iso_week(client, db_session):
    now = datetime.now(timezone.utc)
    this_week = _note(db_session, "a1" * 12, now)
    last_week = _note(db_session, "b2" * 12, now - timedelta(days=10))
    recent_activity = Activity(note_id=this_week.id, name="本周活动", city_code="nb", type="市集", created_at=now)
    old_activity = Activity(note_id=last_week.id, name="上周活动", city_code="nb", type="市集", created_at=now - timedelta(days=10))
    db_session.add_all([recent_activity, old_activity])
    db_session.commit()

    resp = client.get("/api/v1/dashboard/summary", headers=_auth())
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["weekly_notes_count"] == 1
    assert data["weekly_activities_count"] == 1


def test_summary_recent_logs_returns_latest_five(client, db_session):
    base = datetime.now(timezone.utc)
    for i in range(7):
        db_session.add(TaskLog(task_id=100 + i, level="INFO", message=f"log-{i}", created_at=base + timedelta(seconds=i)))
    db_session.commit()

    resp = client.get("/api/v1/dashboard/summary", headers=_auth())
    assert resp.status_code == 200
    logs = resp.json()["data"]["recent_logs"]
    assert len(logs) == 5
    # 最新在前
    assert [log["message"] for log in logs] == ["log-6", "log-5", "log-4", "log-3", "log-2"]
    assert logs[0]["task_id"] == 106
    assert logs[0]["level"] == "INFO"
    assert "created_at" in logs[0]


def test_delete_report_removes_row_and_is_404_idempotent(client, db_session):
    report = WeeklyReport(week="2026-W30", cities='["nb"]', note_count=1, activity_count=2, content="# 周报")
    db_session.add(report)
    db_session.commit()

    resp = client.delete(f"/api/v1/reports/{report.id}", headers=_auth())
    assert resp.status_code == 200
    assert db_session.get(WeeklyReport, report.id) is None

    again = client.delete(f"/api/v1/reports/{report.id}", headers=_auth())
    assert again.status_code == 404

    detail = client.get(f"/api/v1/reports/{report.id}", headers=_auth())
    assert detail.status_code == 404
