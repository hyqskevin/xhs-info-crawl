from datetime import date, datetime, time, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.activity import Activity
from app.models.config import City
from app.models.note import Note, NoteImage
from app.schemas.activity import ActivityRead


router = APIRouter(prefix="/notes", tags=["notes"])
Auth = Annotated[dict[str, str], Depends(get_current_user)]
DB = Annotated[Session, Depends(get_db)]


class BatchRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=100)


class NoteUpdate(BaseModel):
    title: str = Field(max_length=512)
    content: str
    city_code: str = Field(min_length=1, max_length=32)
    published_at: datetime | None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("标题不能为空")
        return value


class NoteReviewRequest(BaseModel):
    status: Literal["APPROVED", "REJECTED"]


def _visible_note(db: Session, note_id: int) -> Note:
    note = db.scalar(select(Note).where(Note.id == note_id, Note.review_status.notin_(["DELETED", "MERGED"])))
    if note is None:
        raise HTTPException(404, "推文不存在")
    return note


def _summary(note: Note, activity_count: int, ocr_texts: list[str] | None = None) -> dict:
    """为列表行构造轻量级 summary；超过 4 KiB 会被截断，并附 `summary_truncated=True`。

    详情接口 `_detail_data` 不走此函数，仍返回全部 OCR。
    """
    MAX_OCR_BLOCKS = 5
    MAX_SUMMARY_BYTES = 4096
    ocr_list = ocr_texts or []
    parts: list[str] = []
    if note.content:
        parts.append(f"正文：{note.content}")
    ocr_count = 0
    for index, text in enumerate(ocr_list, 1):
        if not text:
            continue
        if ocr_count >= MAX_OCR_BLOCKS:
            break
        parts.append(f"[图片 {index} OCR] {text}")
        ocr_count += 1
    text = "\n".join(parts)
    encoded = text.encode("utf-8")
    truncated = False
    if len(encoded) > MAX_SUMMARY_BYTES:
        truncated = True
        omission = "…(摘要已截断" + ("，共省略多张图片 OCR)" if ocr_count < len([t for t in ocr_list if t]) else ")")
        omission_bytes = omission.encode("utf-8")
        keep_bytes = max(0, MAX_SUMMARY_BYTES - len(omission_bytes) - 1)  # 留 1 byte 给前缀换行
        truncated_body = encoded[:keep_bytes].decode("utf-8", errors="ignore")
        text = truncated_body + "\n" + omission
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
        "summary": text,
        "summary_truncated": truncated,
    }


def _detail_data(db: Session, note: Note) -> dict:
    activities = list(db.scalars(select(Activity).where(Activity.note_id == note.id, Activity.deleted_at.is_(None)).order_by(Activity.id)).all())
    images = list(db.scalars(select(NoteImage).where(NoteImage.note_id == note.id).order_by(NoteImage.id)).all())
    ocr_texts = [image.ocr_text for image in images]
    data = _summary(note, len(activities), ocr_texts)
    data.update({
        "content": note.content,
        "activities": [ActivityRead.model_validate(item).model_dump(mode="json") for item in activities],
        "images": [{"id": image.id, "ocr_status": image.ocr_status, "ocr_text": image.ocr_text, "url": f"/notes/{note.id}/images/{image.id}"} for image in images],
    })
    return data


@router.get("")
def list_notes(
    _: Auth,
    db: DB,
    city: str | None = None,
    review_status: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    keyword: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    filters = [Note.review_status.notin_(["DELETED", "MERGED"])]
    if city:
        filters.append(Note.city_code == city)
    if review_status:
        filters.append(Note.review_status == review_status)
    published = Note.published_at
    if start_date:
        filters.append(Note.published_at >= datetime.combine(start_date, time.min, tzinfo=timezone.utc))
    if end_date:
        filters.append(Note.published_at <= datetime.combine(end_date, time.max, tzinfo=timezone.utc))
    if keyword:
        stripped = keyword.strip()
        if stripped:
            pattern = f"%{stripped}%"
            filters.append(or_(Note.title.ilike(pattern), Note.content.ilike(pattern)))

    total = db.scalar(select(func.count()).select_from(Note).where(*filters)) or 0
    activity_counts = (
        select(Activity.note_id, func.count(Activity.id).label("activity_count"))
        .where(Activity.deleted_at.is_(None))
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
    note_ids = [note.id for note, _ in rows]
    ocr_map: dict[int, list[str]] = {}
    if note_ids:
        try:
            image_rows = db.execute(
                select(NoteImage.note_id, NoteImage.ocr_text)
                .where(NoteImage.note_id.in_(note_ids))
                .order_by(NoteImage.note_id, NoteImage.id)
            ).all()
            for note_id, ocr_text in image_rows:
                ocr_map.setdefault(note_id, []).append(ocr_text)
        except Exception:
            # OCR 聚合失败不影响主列表读取
            ocr_map = {}
    return {"code": 200, "message": "success", "data": {"items": [_summary(note, count, ocr_map.get(note.id, [])) for note, count in rows]}, "pagination": {"page": page, "page_size": page_size, "total": total}}


@router.get("/{note_id}")
def get_note(note_id: int, _: Auth, db: DB):
    note = _visible_note(db, note_id)
    return {"code": 200, "message": "success", "data": _detail_data(db, note)}


@router.put("/{note_id}")
def update_note(note_id: int, payload: NoteUpdate, _: Auth, db: DB):
    note = _visible_note(db, note_id)
    city = db.scalar(select(City).where(City.code == payload.city_code, City.enabled.is_(True)))
    if city is None:
        raise HTTPException(status_code=422, detail="城市不存在或未启用")
    note.title = payload.title
    note.content = payload.content
    note.city_code = payload.city_code
    note.published_at = payload.published_at
    db.commit()
    db.refresh(note)
    return {"code": 200, "message": "success", "data": _detail_data(db, note)}


@router.post("/{note_id}/review")
def review_note(note_id: int, payload: NoteReviewRequest, _: Auth, db: DB):
    note = _visible_note(db, note_id)
    if payload.status == "APPROVED":
        # 校验至少 1 条有效子活动
        has_activity = db.scalar(select(func.count(Activity.id)).where(
            Activity.note_id == note.id, Activity.deleted_at.is_(None))) or 0
        if has_activity == 0:
            raise HTTPException(status_code=422, detail="推文无有效子活动，请先重新处理")
    note.review_status = payload.status
    db.commit()
    return {"code": 200, "message": "success", "data": {"id": note.id, "review_status": note.review_status}}


@router.post("/{note_id}/reprocess")
def reprocess_note(note_id: int, _: Auth, db: DB):
    """将状态异常的推文标记为可重跑。

    适用：note.status in (NO_ACTIVITIES, EMPTY_RESULT_RETRYABLE)。
    实际重新抓取需要走 /api/v1/tasks/{id}/restart 重新触发 worker。
    """
    note = db.get(Note, note_id)
    if note is None or note.review_status in {"DELETED", "MERGED"}:
        raise HTTPException(status_code=404, detail="推文不存在")
    if note.status not in {"NO_ACTIVITIES", "EMPTY_RESULT_RETRYABLE"}:
        raise HTTPException(status_code=409, detail=f"推文状态 {note.status} 不需要重新处理")
    # 清除 OCR/详情/活动记录，重新走抓取阶段
    from app.models.note import NoteImage
    db.execute(delete(NoteImage).where(NoteImage.note_id == note_id))
    db.execute(delete(Activity).where(Activity.note_id == note_id))
    note.status = "PENDING"
    note.published_at = None
    db.commit()
    return {"code": 202, "message": "success", "data": {"id": note.id, "status": note.status}}


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
