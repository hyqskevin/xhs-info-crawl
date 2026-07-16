from difflib import SequenceMatcher
from typing import Any, Literal


def similarity_score(left: dict[str, Any], right: dict[str, Any]) -> float:
    if left.get("city_code") != right.get("city_code"):
        return 0.0
    name = SequenceMatcher(None, str(left.get("name", "")), str(right.get("name", ""))).ratio()
    location = SequenceMatcher(None, str(left.get("location", "")), str(right.get("location", ""))).ratio()
    date_match = str(left.get("start_time", ""))[:10] == str(right.get("start_time", ""))[:10]
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
