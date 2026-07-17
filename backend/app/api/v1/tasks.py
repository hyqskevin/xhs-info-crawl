from datetime import datetime, timezone
from typing import Annotated, Literal
from fastapi import APIRouter,Depends,HTTPException,Query,status
from pydantic import BaseModel
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import require_admin
from app.models.task import CrawlTask,TaskLog
from app.models.config import Blogger, City, Keyword
router=APIRouter(prefix='/tasks',tags=['tasks']); Admin=Annotated[dict,Depends(require_admin)]; DB=Annotated[Session,Depends(get_db)]
class CrawlIn(BaseModel):
    type: str = 'mixed'
    city: str
    keywords: list[str] = []
    recent_filter: Literal['不限','一天内','一周内','半年内'] = '一周内'
    blogger_ids: list[int] = []
def dump(t): return {c.name:getattr(t,c.name) for c in t.__table__.columns}
@router.get('')
def tasks(_:Admin,db:DB,page:int=1,page_size:Annotated[int,Query(le=100)]=20):
    total=db.scalar(select(func.count()).select_from(CrawlTask)) or 0; rows=db.scalars(select(CrawlTask).order_by(CrawlTask.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
    return {'code':200,'message':'success','data':{'items':[dump(x) for x in rows]},'pagination':{'page':page,'page_size':page_size,'total':total}}
@router.post('/crawl',status_code=status.HTTP_202_ACCEPTED)
def crawl(payload:CrawlIn,_:Admin,db:DB):
    running=db.scalar(select(CrawlTask).where(CrawlTask.status.in_(['PENDING','RUNNING','SEARCH_DONE','DOWNLOADING','PROCESSING','DEDUPING'])))
    if running: raise HTTPException(409,'TASK_IN_PROGRESS')
    city=db.scalar(select(City).where(City.code==payload.city,City.enabled.is_(True)))
    if not city: raise HTTPException(422,'请选择已启用的城市')
    configured_keywords=set(db.scalars(select(Keyword.word).where(Keyword.city_code==city.code,Keyword.enabled.is_(True))).all())
    if any(keyword not in configured_keywords for keyword in payload.keywords): raise HTTPException(422,'关键词不属于所选城市')
    configured_bloggers=set(db.scalars(select(Blogger.id).where(Blogger.city_code==city.code,Blogger.enabled.is_(True))).all())
    if any(blogger_id not in configured_bloggers for blogger_id in payload.blogger_ids): raise HTTPException(422,'博主不属于所选城市')
    if not payload.keywords and not payload.blogger_ids: raise HTTPException(422,'请至少选择一个关键词或博主')
    task=CrawlTask(type=payload.type,status='PENDING',params=payload.model_dump()); db.add(task); db.commit(); db.refresh(task)
    from app.tasks.crawl_task import run_crawl
    run_crawl.delay(task.id)
    return {'code':202,'message':'success','data':dump(task)}

@router.post('/{task_id}/restart',status_code=status.HTTP_202_ACCEPTED)
def restart(task_id:int,_:Admin,db:DB):
    task=db.get(CrawlTask,task_id)
    if not task: raise HTTPException(404,'任务不存在')
    if task.status!='FAILED': raise HTTPException(409,'仅失败任务可以继续抓取')
    running=db.scalar(select(CrawlTask).where(CrawlTask.id!=task_id,CrawlTask.status.in_(['PENDING','RUNNING','SEARCH_DONE','DOWNLOADING','PROCESSING','DEDUPING'])))
    if running: raise HTTPException(409,'TASK_IN_PROGRESS')
    city_code=task.params.get('city')
    city=db.scalar(select(City).where(City.code==city_code,City.enabled.is_(True)))
    if not city: raise HTTPException(422,'原任务城市已停用')
    task.status='PENDING';task.failed_notes=0;task.error_message=None;task.current_stage=None;task.current_note=None;task.finished_at=None
    db.add(TaskLog(task_id=task.id,level='INFO',message='任务继续抓取',created_at=datetime.now(timezone.utc)))
    db.commit();db.refresh(task)
    from app.tasks.crawl_task import run_crawl
    run_crawl.delay(task.id)
    return {'code':202,'message':'success','data':dump(task)}
@router.get('/{task_id}/logs')
def logs(task_id:int,_:Admin,db:DB): return {'code':200,'message':'success','data':[dump(x) for x in db.scalars(select(TaskLog).where(TaskLog.task_id==task_id).order_by(TaskLog.id)).all()]}
