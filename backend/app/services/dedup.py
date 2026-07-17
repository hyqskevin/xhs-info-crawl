from difflib import SequenceMatcher
from typing import Any, Literal
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.activity import Activity
from app.models.duplicate import DuplicateCandidate


def similarity_score(left: dict[str, Any], right: dict[str, Any]) -> float:
    if left.get("city_code") != right.get("city_code"):
        return 0.0
    name = SequenceMatcher(None, str(left.get("name", "")), str(right.get("name", ""))).ratio()
    location = SequenceMatcher(None, str(left.get("location", "")), str(right.get("location", ""))).ratio()
    left_start = left.get("start_time")
    right_start = right.get("start_time")
    date_match = bool(left_start and right_start and str(left_start)[:10] == str(right_start)[:10])
    return round(name * 0.55 + location * 0.2 + (0.25 if date_match else 0), 4)


def classify_similarity(score: float) -> Literal["auto_merge", "manual_review", "distinct"]:
    if score >= 0.7:
        return "auto_merge"
    if score >= 0.4:
        return "manual_review"
    return "distinct"


def merge_activities(left: dict[str, Any], right: dict[str, Any], keep: Literal["a", "b"] = "a") -> dict[str, Any]:
    selected = dict(left if keep == "a" else right)
    note_ids = list(dict.fromkeys([*left.get("related_note_ids", []), *right.get("related_note_ids", [])]))
    selected["related_note_ids"] = note_ids
    selected["status"] = "APPROVED"
    return selected


def create_duplicate_candidates(db: Session, activity: Activity) -> list[DuplicateCandidate]:
    """Create review candidates for same-city activities; exact/high matches are surfaced, not silently deleted."""
    created=[]
    rows=db.scalars(select(Activity).where(Activity.id != activity.id,Activity.city_code == activity.city_code,Activity.status.notin_(['DELETED','MERGED']))).all()
    left={c.name:getattr(activity,c.name) for c in activity.__table__.columns}
    for other in rows:
        right={c.name:getattr(other,c.name) for c in other.__table__.columns}; score=similarity_score(left,right)
        if classify_similarity(score)=='distinct': continue
        a,b=sorted((activity.id,other.id))
        exists=db.scalar(select(DuplicateCandidate).where(DuplicateCandidate.activity_a_id==a,DuplicateCandidate.activity_b_id==b))
        if exists: continue
        matched=[]
        if activity.city_code==other.city_code: matched.append('city')
        if activity.start_time and other.start_time and activity.start_time.date()==other.start_time.date(): matched.append('date')
        candidate=DuplicateCandidate(activity_a_id=a,activity_b_id=b,similarity=score,matched_fields=','.join(matched),status='pending')
        db.add(candidate); created.append(candidate)
    return created
