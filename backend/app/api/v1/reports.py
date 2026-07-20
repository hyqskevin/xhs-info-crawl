import json
import re
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.activity import Activity
from app.models.note import Note, NoteImage
from app.models.report import WeeklyReport
from app.services.report import generate_note_markdown, generate_note_xlsx


router = APIRouter(prefix="/reports", tags=["reports"])


class GenerateRequest(BaseModel):
    week: str
    cities: list[str] = Field(min_length=1, max_length=1)


def week_bounds(week: str) -> tuple[datetime, datetime]:
    match = re.fullmatch(r"(\d{4})-W(\d{2})", week)
    if match is None:
        raise ValueError("invalid ISO week")
    try:
        start = datetime.fromisocalendar(int(match.group(1)), int(match.group(2)), 1).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError("invalid ISO week") from exc
    return start, start + timedelta(days=7)


def select_activities(db: Session, cities: list[str], week: str) -> list[Activity]:
    start, end = week_bounds(week)
    return list(db.scalars(select(Activity).where(
        Activity.city_code.in_(cities),
        Activity.status == "APPROVED",
        Activity.start_time >= start,
        Activity.start_time < end,
    ).order_by(Activity.start_time, Activity.id)).all())


def select_notes(db: Session, cities: list[str], week: str):
    start, end = week_bounds(week)
    published = func.coalesce(Note.published_at, Note.created_at)
    notes = list(db.scalars(select(Note).where(
        Note.city_code.in_(cities),
        Note.review_status == "APPROVED",
        published >= start,
        published < end,
    ).order_by(published, Note.id)).all())
    entries = []
    for note in notes:
        activities = list(db.scalars(select(Activity).where(Activity.note_id == note.id, Activity.status.notin_(["DELETED", "MERGED"])).order_by(Activity.id)).all())
        images = list(db.scalars(select(NoteImage).where(NoteImage.note_id == note.id).order_by(NoteImage.id)).all())
        entries.append((note, activities, images))
    return entries

@router.get("")
def list_reports(_: Annotated[dict[str,str],Depends(get_current_user)],db:Annotated[Session,Depends(get_db)]):
    rows=db.scalars(select(WeeklyReport).order_by(WeeklyReport.id.desc())).all()
    return {'code':200,'message':'success','data':[{'id':x.id,'week':x.week,'cities':json.loads(x.cities),'note_count':x.note_count,'activity_count':x.activity_count,'status':x.status,'created_at':x.created_at.isoformat()} for x in rows]}

@router.get("/{report_id}")
def get_report(report_id:int,_:Annotated[dict[str,str],Depends(get_current_user)],db:Annotated[Session,Depends(get_db)]):
    report=db.get(WeeklyReport,report_id)
    if not report: raise HTTPException(404,'周报不存在')
    return {'code':200,'message':'success','data':{'id':report.id,'week':report.week,'cities':json.loads(report.cities),'activity_count':report.activity_count,'status':report.status,'content':report.content}}


@router.post("/generate")
def generate_report(payload: GenerateRequest, _: Annotated[dict[str, str], Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    try:
        entries = select_notes(db, payload.cities, payload.week)
    except ValueError:
        raise HTTPException(status_code=422, detail="周次格式无效，请使用 YYYY-Www") from None
    if not entries:
        raise HTTPException(status_code=422, detail="所选城市和周次没有已审核推文，请先在活动管理中审核通过")
    note_count = len(entries)
    activity_count = sum(len(activities) for _, activities, _ in entries)
    content = generate_note_markdown(payload.week, payload.cities, entries)
    report = db.scalar(select(WeeklyReport).where(WeeklyReport.week == payload.week))
    if report is None:
        report = WeeklyReport(week=payload.week, cities=json.dumps(payload.cities), note_count=note_count, activity_count=activity_count, content=content, status="draft")
        db.add(report)
    else:
        report.cities = json.dumps(payload.cities)
        report.note_count = note_count
        report.activity_count = activity_count
        report.content = content
        report.status = "draft"
        report.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(report)
    return {"code": 200, "message": "success", "data": {"id": report.id, "week": report.week, "cities": payload.cities, "note_count": report.note_count, "activity_count": report.activity_count, "status": report.status}}


@router.get("/{report_id}/download")
def download_report(report_id: int, _: Annotated[dict[str, str], Depends(get_current_user)], db: Annotated[Session, Depends(get_db)], format: Annotated[Literal["md", "xlsx"], Query()] = "md"):
    report = db.get(WeeklyReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="周报不存在")
    filename = f"{report.week}.{format}"
    if format == "md":
        return Response(report.content, media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    entries = select_notes(db, json.loads(report.cities), report.week)
    return Response(generate_note_xlsx(entries), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
