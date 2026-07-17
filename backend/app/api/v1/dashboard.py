from typing import Annotated
from fastapi import APIRouter,Depends
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.activity import Activity
from app.models.duplicate import DuplicateCandidate
from app.models.note import Note
from app.models.task import CrawlTask
router=APIRouter(prefix='/dashboard',tags=['dashboard'])
@router.get('/summary')
def summary(_:Annotated[dict,Depends(get_current_user)],db:Annotated[Session,Depends(get_db)]):
    last=db.scalar(select(CrawlTask).order_by(CrawlTask.id.desc()).limit(1))
    last_task=None
    if last:
        progress=round((last.extracted_notes+last.failed_notes+last.skipped_notes)*100/last.total_notes,1) if last.total_notes else None
        last_task={'id':last.id,'status':last.status,'total_notes':last.total_notes,'downloaded_notes':last.downloaded_notes,'ocr_notes':last.ocr_notes,'extracted_notes':last.extracted_notes,'success_notes':last.success_notes,'failed_notes':last.failed_notes,'skipped_notes':last.skipped_notes,'current_stage':last.current_stage,'current_note':last.current_note,'error_message':last.error_message,'progress_percent':progress}
    return {'code':200,'message':'success','data':{'weekly_notes_count':db.scalar(select(func.count()).select_from(Note)) or 0,'weekly_activities_count':db.scalar(select(func.count()).select_from(Activity).where(Activity.status!='DELETED')) or 0,'pending_duplicates':db.scalar(select(func.count()).select_from(DuplicateCandidate).where(DuplicateCandidate.status=='pending')) or 0,'pending_review':db.scalar(select(func.count()).select_from(Activity).where(Activity.status=='NEEDS_REVIEW')) or 0,'last_task':last_task}}
