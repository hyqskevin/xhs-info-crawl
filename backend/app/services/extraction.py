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
