from difflib import SequenceMatcher
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.duplicate import NoteDuplicateCandidate
from app.models.note import Note


def create_note_duplicate_candidates(db: Session, note: Note) -> list[NoteDuplicateCandidate]:
    created = []
    others = db.scalars(select(Note).where(Note.id != note.id, Note.city_code == note.city_code, Note.review_status.notin_(["DELETED", "MERGED"]))).all()
    for other in others:
        title_score = SequenceMatcher(None, note.title or "", other.title or "").ratio()
        content_score = SequenceMatcher(None, note.content or "", other.content or "").ratio()
        score = round(title_score * 0.65 + content_score * 0.35, 4)
        if score < 0.55:
            continue
        a, b = sorted((note.id, other.id))
        exists = db.scalar(select(NoteDuplicateCandidate).where(NoteDuplicateCandidate.note_a_id == a, NoteDuplicateCandidate.note_b_id == b))
        if exists:
            continue
        matched = [field for field, value in (("title", title_score), ("content", content_score)) if value >= 0.6]
        candidate = NoteDuplicateCandidate(note_a_id=a, note_b_id=b, similarity=score, matched_fields=matched, status="pending")
        db.add(candidate); created.append(candidate)
    return created
