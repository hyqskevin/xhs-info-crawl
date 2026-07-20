from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.duplicate import NoteDuplicateCandidate
from app.models.note import Note


router = APIRouter(prefix="/duplicates", tags=["duplicates"])
User = Annotated[dict, Depends(get_current_user)]
DB = Annotated[Session, Depends(get_db)]


class MergeIn(BaseModel):
    keep: Literal["a", "b"] = "a"


def dump(value):
    return {column.name: getattr(value, column.name) for column in value.__table__.columns}


@router.get("")
def candidates(_: User, db: DB, status: str | None = None, page: int = 1, page_size: int = 20):
    filters = [NoteDuplicateCandidate.status == (status or "pending")]
    total = db.scalar(select(func.count()).select_from(NoteDuplicateCandidate).where(*filters)) or 0
    rows = db.scalars(select(NoteDuplicateCandidate).where(*filters).offset((page - 1) * page_size).limit(page_size)).all()
    return {"code": 200, "message": "success", "data": {"items": [dump(row) for row in rows]}, "pagination": {"page": page, "page_size": page_size, "total": total}}


@router.post("/{candidate_id}/merge")
def merge(candidate_id: int, payload: MergeIn, _: User, db: DB):
    candidate = db.get(NoteDuplicateCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(404, "去重候选不存在")
    kept_id = candidate.note_a_id if payload.keep == "a" else candidate.note_b_id
    removed_id = candidate.note_b_id if payload.keep == "a" else candidate.note_a_id
    kept, removed = db.get(Note, kept_id), db.get(Note, removed_id)
    if kept is None or removed is None:
        raise HTTPException(409, "候选推文已不存在")
    removed.review_status = "MERGED"
    removed.merged_into_note_id = kept.id
    now = datetime.now(timezone.utc)
    db.execute(update(NoteDuplicateCandidate).where(
        NoteDuplicateCandidate.status == "pending",
        or_(NoteDuplicateCandidate.note_a_id == removed.id, NoteDuplicateCandidate.note_b_id == removed.id),
    ).values(status="superseded", resolved_at=now))
    candidate.status = "merged"; candidate.resolution = f"keep_{payload.keep}"; candidate.kept_note_id = kept.id; candidate.resolved_at = now
    db.commit()
    return {"code": 200, "message": "success", "data": dump(candidate)}


@router.post("/{candidate_id}/ignore")
def ignore(candidate_id: int, _: User, db: DB):
    candidate = db.get(NoteDuplicateCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(404, "去重候选不存在")
    candidate.status = "ignored"; candidate.resolved_at = datetime.now(timezone.utc); db.commit()
    return {"code": 200, "message": "success", "data": dump(candidate)}
