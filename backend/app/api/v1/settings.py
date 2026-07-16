from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import require_admin
from app.models.config import Blogger, City, Keyword
from app.core.config import get_settings
from app.services.opencli_adapter import OpenCLIAdapter

router=APIRouter(prefix="/settings",tags=["settings"])
Admin=Annotated[dict[str,str],Depends(require_admin)]; DB=Annotated[Session,Depends(get_db)]
class CityIn(BaseModel): name:str; code:str; enabled:bool=True
class KeywordIn(BaseModel): word:str; city_code:str; enabled:bool=True
class BloggerIn(BaseModel): platform_user_id:str; username:str; profile_url:str; city_code:str; enabled:bool=True
MODELS={"cities":City,"keywords":Keyword,"bloggers":Blogger}
SCHEMAS={"cities":CityIn,"keywords":KeywordIn,"bloggers":BloggerIn}
def dump(x): return {c.name:getattr(x,c.name) for c in x.__table__.columns}

@router.get("/{kind}")
def list_settings(kind:Literal['cities','keywords','bloggers'],_:Admin,db:DB): return {"code":200,"message":"success","data":[dump(x) for x in db.scalars(select(MODELS[kind]).order_by(MODELS[kind].id)).all()]}
@router.post("/{kind}",status_code=status.HTTP_201_CREATED)
def create_setting(kind:Literal['cities','keywords','bloggers'],payload:dict,_:Admin,db:DB):
    data=SCHEMAS[kind].model_validate(payload); item=MODELS[kind](**data.model_dump()); db.add(item); db.commit(); db.refresh(item); return {"code":201,"message":"success","data":dump(item)}
@router.put("/{kind}/{item_id}")
def update_setting(kind:Literal['cities','keywords','bloggers'],item_id:int,payload:dict,_:Admin,db:DB):
    item=db.get(MODELS[kind],item_id)
    if not item: raise HTTPException(404,"配置不存在")
    for k,v in payload.items():
        if hasattr(item,k): setattr(item,k,v)
    db.commit(); db.refresh(item); return {"code":200,"message":"success","data":dump(item)}
@router.delete("/{kind}/{item_id}")
def delete_setting(kind:Literal['cities','keywords','bloggers'],item_id:int,_:Admin,db:DB):
    item=db.get(MODELS[kind],item_id)
    if item: db.delete(item); db.commit()
    return {"code":200,"message":"success","data":{"id":item_id}}

@router.get('/opencli/config')
def opencli_config(_:Admin):
    s=get_settings(); return {'code':200,'message':'success','data':{'endpoint':s.opencli_cdp_endpoint,'target_count':s.xhs_search_target_count,'scroll_rounds':s.xhs_search_scroll_max_rounds}}
@router.post('/opencli/test')
def opencli_test(_:Admin):
    try: data=OpenCLIAdapter(get_settings()).check_login(); return {'code':200,'message':'连接正常','data':data}
    except Exception as exc: raise HTTPException(503,str(exc))
