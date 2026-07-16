import re
from datetime import datetime
from typing import Any, Callable


LLM = Callable[[str], dict[str, Any]]


def extract_activity_fields(text: str, now: datetime, llm: LLM | None) -> dict[str, Any]:
    iso = re.search(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?", text)
    cn = re.search(r"(\d{1,2})月(\d{1,2})日(?:\s*(\d{1,2}):(\d{2}))?", text)
    start_time = None
    if iso:
        start_time = datetime(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)), int(iso.group(4) or 0), int(iso.group(5) or 0)).isoformat()
    elif cn:
        start_time = datetime(now.year, int(cn.group(1)), int(cn.group(2)), int(cn.group(3) or 0), int(cn.group(4) or 0)).isoformat()
    price_match = re.search(r"(免费|\d+(?:\.\d+)?\s*元(?:起)?)", text)
    location_match = re.search(r"(?:地点[:：]?\s*)?([\u4e00-\u9fa5]{2,}(?:中心|滨江|广场|公园|书局|剧场|博物馆))", text)
    kind = "演出" if re.search(r"音乐|演出|相声|乐队", text) else "展览" if re.search(r"展览|艺术展", text) else "其他"
    result: dict[str, Any] = {"name": text.strip()[:30] or None, "start_time": start_time, "location": location_match.group(1) if location_match else None, "price": price_match.group(1) if price_match else None, "type": kind}
    if (not result["start_time"] or not result["location"]) and llm:
        result.update({key: value for key, value in llm(text).items() if value is not None})
    result["status"] = "RAW" if result.get("start_time") and result.get("location") else "NEEDS_REVIEW"
    return result


def extract_activities(text: str, now: datetime, llm: LLM | None) -> list[dict[str, Any]]:
    """Extract every concrete activity; retain a rules-only single result when no LLM is configured."""
    if llm is None:
        result = extract_activity_fields(text, now, None)
        result["source_image_indexes"] = []
        return [result]
    payload = llm(text)
    rows = payload.get("activities") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("MiniMax multi-activity response must contain an activities array")
    normalized = []
    for row in rows:
        if not isinstance(row, dict) or not str(row.get("name") or "").strip():
            continue
        item = dict(row)
        item["name"] = str(item["name"]).strip()
        item["source_image_indexes"] = sorted({int(value) for value in item.get("source_image_indexes", []) if str(value).isdigit()})
        confidence=item.get("confidence",0)
        if isinstance(confidence,str): confidence={"high":0.9,"medium":0.6,"low":0.3}.get(confidence.lower(),0)
        item["confidence"] = max(0.0,min(1.0,float(confidence or 0)))
        item["status"] = "RAW" if item.get("start_time") and item.get("location") else "NEEDS_REVIEW"
        normalized.append(item)
    return normalized
