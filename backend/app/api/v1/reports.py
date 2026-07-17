import json
import re
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.activity import Activity
from app.models.report import WeeklyReport
from app.services.report import generate_markdown, generate_xlsx


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

@router.get("")
def list_reports(_: Annotated[dict[str,str],Depends(get_current_user)],db:Annotated[Session,Depends(get_db)]):
    rows=db.scalars(select(WeeklyReport).order_by(WeeklyReport.id.desc())).all()
    return {'code':200,'message':'success','data':[{'id':x.id,'week':x.week,'cities':json.loads(x.cities),'activity_count':x.activity_count,'status':x.status,'created_at':x.created_at.isoformat()} for x in rows]}

@router.get("/{report_id}")
def get_report(report_id:int,_:Annotated[dict[str,str],Depends(get_current_user)],db:Annotated[Session,Depends(get_db)]):
    report=db.get(WeeklyReport,report_id)
    if not report: raise HTTPException(404,'周报不存在')
    return {'code':200,'message':'success','data':{'id':report.id,'week':report.week,'cities':json.loads(report.cities),'activity_count':report.activity_count,'status':report.status,'content':report.content}}


@router.post("/generate")
def generate_report(payload: GenerateRequest, _: Annotated[dict[str, str], Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    try:
        activities = select_activities(db, payload.cities, payload.week)
    except ValueError:
        raise HTTPException(status_code=422, detail="周次格式无效，请使用 YYYY-Www") from None
    if not activities:
        raise HTTPException(status_code=422, detail="所选城市和周次没有已通过活动，请先在活动管理中审核通过")
    content = generate_markdown(payload.week, payload.cities, activities)
    report = db.scalar(select(WeeklyReport).where(WeeklyReport.week == payload.week))
    if report is None:
        report = WeeklyReport(week=payload.week, cities=json.dumps(payload.cities), activity_count=len(activities), content=content, status="draft")
        db.add(report)
    else:
        report.cities = json.dumps(payload.cities)
        report.activity_count = len(activities)
        report.content = content
        report.status = "draft"
        report.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(report)
    return {"code": 200, "message": "success", "data": {"id": report.id, "week": report.week, "cities": payload.cities, "activity_count": report.activity_count, "status": report.status}}


@router.get("/{report_id}/download")
def download_report(report_id: int, _: Annotated[dict[str, str], Depends(get_current_user)], db: Annotated[Session, Depends(get_db)], format: Annotated[Literal["md", "xlsx"], Query()] = "md"):
    report = db.get(WeeklyReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="周报不存在")
    filename = f"{report.week}.{format}"
    if format == "md":
        return Response(report.content, media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    activities = select_activities(db, json.loads(report.cities), report.week)
    return Response(generate_xlsx(activities), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
