from typing import Annotated
from fastapi import APIRouter,Depends,HTTPException,Query,status
from pydantic import BaseModel
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import require_admin
from app.models.task import CrawlTask,TaskLog
router=APIRouter(prefix='/tasks',tags=['tasks']); Admin=Annotated[dict,Depends(require_admin)]; DB=Annotated[Session,Depends(get_db)]
class CrawlIn(BaseModel): type:str='keyword'; cities:list[str]; keywords:list[str]=[]
def dump(t): return {c.name:getattr(t,c.name) for c in t.__table__.columns}
@router.get('')
def tasks(_:Admin,db:DB,page:int=1,page_size:Annotated[int,Query(le=100)]=20):
    total=db.scalar(select(func.count()).select_from(CrawlTask)) or 0; rows=db.scalars(select(CrawlTask).order_by(CrawlTask.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
    return {'code':200,'message':'success','data':{'items':[dump(x) for x in rows]},'pagination':{'page':page,'page_size':page_size,'total':total}}
@router.post('/crawl',status_code=status.HTTP_202_ACCEPTED)
def crawl(payload:CrawlIn,_:Admin,db:DB):
    running=db.scalar(select(CrawlTask).where(CrawlTask.status.in_(['PENDING','RUNNING','SEARCH_DONE','DOWNLOADING','PROCESSING','DEDUPING'])))
    if running: raise HTTPException(409,'TASK_IN_PROGRESS')
    task=CrawlTask(type=payload.type,status='PENDING',params=payload.model_dump()); db.add(task); db.commit(); db.refresh(task)
    from app.tasks.crawl_task import run_crawl
    run_crawl.delay(task.id)
    return {'code':202,'message':'success','data':dump(task)}
@router.get('/{task_id}/logs')
def logs(task_id:int,_:Admin,db:DB): return {'code':200,'message':'success','data':[dump(x) for x in db.scalars(select(TaskLog).where(TaskLog.task_id==task_id).order_by(TaskLog.id)).all()]}
