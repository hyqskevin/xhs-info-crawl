from datetime import datetime,timezone
from typing import Annotated,Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.activity import Activity
from app.models.duplicate import DuplicateCandidate
router=APIRouter(prefix='/duplicates',tags=['duplicates']); User=Annotated[dict,Depends(get_current_user)]; DB=Annotated[Session,Depends(get_db)]
class MergeIn(BaseModel): keep:Literal['a','b']='a'
def dump(x): return {c.name:getattr(x,c.name) for c in x.__table__.columns}
@router.get('')
def candidates(_:User,db:DB,status:str|None=None,page:int=1,page_size:int=20):
    filters=[] if not status else [DuplicateCandidate.status==status]; total=db.scalar(select(func.count()).select_from(DuplicateCandidate).where(*filters)) or 0; rows=db.scalars(select(DuplicateCandidate).where(*filters).offset((page-1)*page_size).limit(page_size)).all()
    return {'code':200,'message':'success','data':{'items':[dump(x) for x in rows]},'pagination':{'page':page,'page_size':page_size,'total':total}}
@router.post('/{candidate_id}/merge')
def merge(candidate_id:int,payload:MergeIn,_:User,db:DB):
    c=db.get(DuplicateCandidate,candidate_id)
    if not c: raise HTTPException(404,'去重候选不存在')
    kept=db.get(Activity,c.activity_a_id if payload.keep=='a' else c.activity_b_id); removed=db.get(Activity,c.activity_b_id if payload.keep=='a' else c.activity_a_id)
    kept.status='APPROVED'; removed.status='MERGED'; c.status='merged'; c.resolution=f'keep_{payload.keep}'; c.merged_activity_id=kept.id; c.resolved_at=datetime.now(timezone.utc); db.commit()
    return {'code':200,'message':'success','data':dump(c)}
@router.post('/{candidate_id}/ignore')
def ignore(candidate_id:int,_:User,db:DB):
    c=db.get(DuplicateCandidate,candidate_id)
    if not c: raise HTTPException(404,'去重候选不存在')
    c.status='ignored'; c.resolved_at=datetime.now(timezone.utc); db.commit(); return {'code':200,'message':'success','data':dump(c)}
