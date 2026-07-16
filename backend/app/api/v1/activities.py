from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.security import get_current_user


router = APIRouter(prefix="/activities", tags=["activities"])


@router.get("")
def list_activities(_: Annotated[dict[str, str], Depends(get_current_user)]):
    return {"code": 200, "message": "success", "data": {"items": []}, "pagination": {"page": 1, "page_size": 20, "total": 0}}
