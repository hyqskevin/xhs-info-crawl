from datetime import date, datetime, time, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.activity import Activity
from app.schemas.activity import ActivityRead, ActivityUpdate


router = APIRouter(prefix="/activities", tags=["activities"])
auth = Annotated[dict[str, str], Depends(get_current_user)]
database = Annotated[Session, Depends(get_db)]


def serialize(activity: Activity) -> dict[str, object]:
    return ActivityRead.model_validate(activity).model_dump(mode="json")


def find_activity(db: Session, activity_id: int) -> Activity:
    activity = db.scalar(select(Activity).where(Activity.id == activity_id, Activity.status.notin_(["DELETED", "MERGED"])))
    if activity is None:
        raise HTTPException(status_code=404, detail="活动不存在")
    return activity


@router.get("")
def list_activities(
    _: auth,
    db: database,
    city: str | None = None,
    type: str | None = None,
    activity_status: Annotated[str | None, Query(alias="status")] = None,
    start_date: date | None = None,
    end_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    filters = [Activity.status.notin_(["DELETED", "MERGED"])]
    if city:
        filters.append(Activity.city_code == city)
    if type:
        filters.append(Activity.type == type)
    if activity_status:
        filters.append(Activity.status == activity_status)
    if start_date:
        filters.append(Activity.start_time >= datetime.combine(start_date, time.min, tzinfo=timezone.utc))
    if end_date:
        filters.append(Activity.start_time <= datetime.combine(end_date, time.max, tzinfo=timezone.utc))
    total = db.scalar(select(func.count()).select_from(Activity).where(*filters)) or 0
    items = db.scalars(select(Activity).where(*filters).order_by(Activity.start_time, Activity.id).offset((page - 1) * page_size).limit(page_size)).all()
    return {"code": 200, "message": "success", "data": {"items": [serialize(item) for item in items]}, "pagination": {"page": page, "page_size": page_size, "total": total}}


@router.get("/{activity_id}")
def get_activity(activity_id: int, _: auth, db: database):
    data = serialize(find_activity(db, activity_id))
    data.update({"note": None, "images": []})
    return {"code": 200, "message": "success", "data": data}


@router.put("/{activity_id}")
def update_activity(activity_id: int, payload: ActivityUpdate, _: auth, db: database):
    activity = find_activity(db, activity_id)
    changes = payload.model_dump(exclude_unset=True)
    if activity.status == "PUBLISHED" and changes.get("status") == "RAW":
        raise HTTPException(status_code=422, detail="无效的活动状态转换")
    for key, value in changes.items():
        setattr(activity, key, value)
    activity.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(activity)
    return {"code": 200, "message": "success", "data": serialize(activity)}


@router.delete("/{activity_id}")
def delete_activity(activity_id: int, _: auth, db: database):
    activity = find_activity(db, activity_id)
    activity.status = "DELETED"
    activity.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"code": 200, "message": "success", "data": {"id": activity_id}}
