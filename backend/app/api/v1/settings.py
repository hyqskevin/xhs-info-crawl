from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.security import require_admin


router = APIRouter(prefix="/settings", tags=["settings"])


@router.delete("/cities/{city_id}")
def delete_city(city_id: int, _: Annotated[dict[str, str], Depends(require_admin)]):
    return {"code": 200, "message": "success", "data": {"id": city_id}}
