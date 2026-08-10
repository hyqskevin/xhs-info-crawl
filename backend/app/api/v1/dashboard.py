from datetime import datetime, timedelta, timezone
from typing import Annotated
from fastapi import APIRouter,Depends
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.activity import Activity
from app.models.duplicate import NoteDuplicateCandidate
from app.models.note import Note
from app.models.schedule import ScheduledCrawl
from app.models.task import CrawlTask, TaskLog
router=APIRouter(prefix='/dashboard',tags=['dashboard'])

_SHANGHAI = timezone(timedelta(hours=8))


def _iso_week_start_utc_naive() -> datetime:
    """本周一 00:00（北京）对应的 UTC naive 时间点，用于匹配 UTC naive 存储的 created_at。"""
    now_sh = datetime.now(_SHANGHAI)
    monday_sh = (now_sh - timedelta(days=now_sh.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday_sh.astimezone(timezone.utc).replace(tzinfo=None)

_KNOWN_STATUSES={'COMPLETED','COMPLETED_WITH_ERRORS','FAILED','STOPPED'}

def _task_source(task:CrawlTask)->str:
    params=task.params or {}
    return 'scheduled' if params.get('type')=='scheduled' or params.get('schedule_id') else 'manual'

@router.get('/analytics')
def analytics(_:Annotated[dict,Depends(get_current_user)],db:Annotated[Session,Depends(get_db)]):
    recent=list(db.scalars(select(CrawlTask).order_by(CrawlTask.id.desc()).limit(20)).all())
    recent.reverse()
    recent_tasks=[{'id':t.id,'source':_task_source(t),'schedule_name':(t.params or {}).get('schedule_name'),'status':t.status,'started_at':t.started_at,'total_notes':t.total_notes,'success_notes':t.success_notes,'failed_notes':t.failed_notes} for t in recent]
    last50=list(db.scalars(select(CrawlTask).order_by(CrawlTask.id.desc()).limit(50)).all())
    status_counts:dict[str,int]={}
    for t in last50:
        key=t.status if t.status in _KNOWN_STATUSES else 'OTHER'
        status_counts[key]=status_counts.get(key,0)+1
    scheduled_tasks=list(db.scalars(select(CrawlTask).order_by(CrawlTask.id.desc()).limit(500)).all())
    schedules=[]
    for s in db.scalars(select(ScheduledCrawl).order_by(ScheduledCrawl.id)).all():
        last_task=None
        for t in scheduled_tasks:
            if (t.params or {}).get('schedule_id')==s.id:
                last_task={'id':t.id,'status':t.status,'started_at':t.started_at}
                break
        schedules.append({'id':s.id,'name':s.name,'enabled':s.enabled,'day_of_week':s.day_of_week,'hour':s.hour,'minute':s.minute,'city_code':s.city_code,'last_task':last_task})
    return {'code':200,'message':'success','data':{'recent_tasks':recent_tasks,'status_counts':status_counts,'schedules':schedules}}
@router.get('/summary')
def summary(_:Annotated[dict,Depends(get_current_user)],db:Annotated[Session,Depends(get_db)]):
    last=db.scalar(select(CrawlTask).order_by(CrawlTask.id.desc()).limit(1))
    last_task=None
    if last:
        progress=round((last.extracted_notes+last.failed_notes+last.skipped_notes)*100/last.total_notes,1) if last.total_notes else None
        last_task={'id':last.id,'status':last.status,'total_notes':last.total_notes,'downloaded_notes':last.downloaded_notes,'ocr_notes':last.ocr_notes,'extracted_notes':last.extracted_notes,'success_notes':last.success_notes,'failed_notes':last.failed_notes,'skipped_notes':last.skipped_notes,'skipped_activities':last.skipped_activities,'current_stage':last.current_stage,'current_note':last.current_note,'error_message':last.error_message,'progress_percent':progress}
    week_start = _iso_week_start_utc_naive()
    recent_logs = [
        {'id': log.id, 'task_id': log.task_id, 'level': log.level, 'message': log.message, 'created_at': log.created_at}
        for log in db.scalars(select(TaskLog).order_by(TaskLog.id.desc()).limit(5)).all()
    ]
    note_a_alias = Note.__table__.alias("note_a_alias")
    note_b_alias = Note.__table__.alias("note_b_alias")
    pending_dup_total = db.scalar(
        select(func.count())
        .select_from(NoteDuplicateCandidate)
        .join(note_a_alias, note_a_alias.c.id == NoteDuplicateCandidate.note_a_id)
        .join(note_b_alias, note_b_alias.c.id == NoteDuplicateCandidate.note_b_id)
        .where(
            NoteDuplicateCandidate.status == 'pending',
            note_a_alias.c.review_status.notin_(['DELETED', 'MERGED']),
            note_b_alias.c.review_status.notin_(['DELETED', 'MERGED']),
        )
    ) or 0
    return {'code':200,'message':'success','data':{'weekly_notes_count':db.scalar(select(func.count()).select_from(Note).where(Note.review_status.notin_(['DELETED','MERGED']), Note.created_at >= week_start)) or 0,'weekly_activities_count':db.scalar(select(func.count()).select_from(Activity).where(Activity.deleted_at.is_(None), Activity.created_at >= week_start)) or 0,'pending_duplicates':pending_dup_total,'pending_review':db.scalar(select(func.count()).select_from(Note).where(Note.review_status=='PENDING')) or 0,'last_task':last_task,'recent_logs':recent_logs}}
