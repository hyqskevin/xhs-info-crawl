from datetime import date, datetime, time, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.activity import Activity
from app.models.note import Note, NoteImage
from app.schemas.activity import ActivityRead


router = APIRouter(prefix="/notes", tags=["notes"])
Auth = Annotated[dict[str, str], Depends(get_current_user)]
DB = Annotated[Session, Depends(get_db)]


class BatchRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=100)


def _visible_note(db: Session, note_id: int) -> Note:
    note = db.scalar(select(Note).where(Note.id == note_id, Note.review_status.notin_(["DELETED", "MERGED"])))
    if note is None:
        raise HTTPException(404, "推文不存在")
    return note


def _summary(note: Note, activity_count: int) -> dict:
    return {
        "id": note.id,
        "title": note.title,
        "city_code": note.city_code,
        "published_at": note.published_at,
        "created_at": note.created_at,
        "processing_status": note.status,
        "review_status": note.review_status,
        "activity_count": activity_count,
        "source_url": note.source_url,
    }


@router.get("")
def list_notes(
    _: Auth,
    db: DB,
    city: str | None = None,
    review_status: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    filters = [Note.review_status.notin_(["DELETED", "MERGED"])]
    if city:
        filters.append(Note.city_code == city)
    if review_status:
        filters.append(Note.review_status == review_status)
    published = func.coalesce(Note.published_at, Note.created_at)
    if start_date:
        filters.append(published >= datetime.combine(start_date, time.min, tzinfo=timezone.utc))
    if end_date:
        filters.append(published <= datetime.combine(end_date, time.max, tzinfo=timezone.utc))
    total = db.scalar(select(func.count()).select_from(Note).where(*filters)) or 0
    activity_counts = (
        select(Activity.note_id, func.count(Activity.id).label("activity_count"))
        .where(Activity.status.notin_(["DELETED", "MERGED"]))
        .group_by(Activity.note_id)
        .subquery()
    )
    rows = db.execute(
        select(Note, func.coalesce(activity_counts.c.activity_count, 0))
        .outerjoin(activity_counts, activity_counts.c.note_id == Note.id)
        .where(*filters)
        .order_by(published.desc(), Note.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {"code": 200, "message": "success", "data": {"items": [_summary(note, count) for note, count in rows]}, "pagination": {"page": page, "page_size": page_size, "total": total}}


@router.get("/{note_id}")
def get_note(note_id: int, _: Auth, db: DB):
    note = _visible_note(db, note_id)
    activities = list(db.scalars(select(Activity).where(Activity.note_id == note.id, Activity.status.notin_(["DELETED", "MERGED"])).order_by(Activity.id)).all())
    images = list(db.scalars(select(NoteImage).where(NoteImage.note_id == note.id).order_by(NoteImage.id)).all())
    data = _summary(note, len(activities))
    data.update({
        "content": note.content,
        "activities": [ActivityRead.model_validate(item).model_dump(mode="json") for item in activities],
        "images": [{"id": image.id, "ocr_status": image.ocr_status, "ocr_text": image.ocr_text, "url": f"/notes/{note.id}/images/{image.id}"} for image in images],
    })
    return {"code": 200, "message": "success", "data": data}


@router.get("/{note_id}/images/{image_id}")
def get_note_image(note_id: int, image_id: int, _: Auth, db: DB):
    _visible_note(db, note_id)
    image = db.scalar(select(NoteImage).where(NoteImage.id == image_id, NoteImage.note_id == note_id))
    if image is None or not image.storage_key:
        raise HTTPException(404, "图片不存在")
    data_root = get_settings().data_dir.resolve()
    path = (data_root / image.storage_key).resolve()
    if not path.is_relative_to(data_root) or not path.is_file():
        raise HTTPException(404, "图片不存在")
    return FileResponse(path)


def _batch_status(db: Session, ids: list[int], target: str) -> list[int]:
    notes = list(db.scalars(select(Note).where(Note.id.in_(set(ids)), Note.review_status.notin_(["DELETED", "MERGED"]))).all())
    if not notes:
        raise HTTPException(404, "没有可操作的推文")
    for note in notes:
        note.review_status = target
    db.commit()
    return [note.id for note in notes]


@router.post("/batch/approve")
def approve_notes(payload: BatchRequest, _: Auth, db: DB):
    ids = _batch_status(db, payload.ids, "APPROVED")
    return {"code": 200, "message": "success", "data": {"approved_ids": ids, "approved_count": len(ids)}}


@router.delete("/batch")
def delete_notes(payload: BatchRequest, _: Auth, db: DB):
    ids = _batch_status(db, payload.ids, "DELETED")
    return {"code": 200, "message": "success", "data": {"deleted_ids": ids, "deleted_count": len(ids)}}
