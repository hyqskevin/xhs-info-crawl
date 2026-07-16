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
    return {'code':200,'message':'success','data':{'weekly_notes_count':db.scalar(select(func.count()).select_from(Note)) or 0,'weekly_activities_count':db.scalar(select(func.count()).select_from(Activity).where(Activity.status!='DELETED')) or 0,'pending_duplicates':db.scalar(select(func.count()).select_from(DuplicateCandidate).where(DuplicateCandidate.status=='pending')) or 0,'pending_review':db.scalar(select(func.count()).select_from(Activity).where(Activity.status=='NEEDS_REVIEW')) or 0,'last_task':{'id':last.id,'status':last.status} if last else None}}
