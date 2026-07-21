from collections import defaultdict
from io import BytesIO

from openpyxl import Workbook

from app.models.activity import Activity
from app.models.note import Note, NoteImage


CITY_NAMES = {"shanghai": "上海", "beijing": "北京"}


def format_activity_markdown(activity: Activity) -> str:
    start = activity.start_time.strftime("%Y-%m-%d %H:%M") if activity.start_time else "待确认"
    end = activity.end_time.strftime("%H:%M") if activity.end_time else ""
    time_text = f"{start} - {end}" if end else start
    return f"#### {activity.name}\n- **时间**：{time_text}\n- **地点**：{activity.location}\n- **费用**：{activity.price}\n- **来源**：[小红书笔记]({activity.source_url})\n- **简介**：{activity.summary}\n"


def visible_activities(activities: list[Activity]) -> list[Activity]:
    """Return activities that are not soft-deleted; weekly reports include every visible activity without status filtering."""
    return [item for item in activities if item.deleted_at is None]


def generate_markdown(week: str, cities: list[str], activities: list[Activity]) -> str:
    selected = visible_activities(activities)
    lines = [f"# 本周活动精选（{week}）", ""]
    if not selected:
        return "\n".join(lines + ["本周暂无活动", ""])
    grouped: dict[str, dict[str, list[Activity]]] = defaultdict(lambda: defaultdict(list))
    for item in selected:
        grouped[item.city_code][item.type].append(item)
    for city in cities:
        if city not in grouped:
            continue
        lines.extend([f"## {CITY_NAMES.get(city, city)}", ""])
        for kind in sorted(grouped[city]):
            lines.extend([f"### {kind}", ""])
            for item in sorted(grouped[city][kind], key=lambda value: (value.start_time or datetime.max, value.id or 0)):
                lines.extend([format_activity_markdown(item), ""])
    lines.append("*本内容由系统自动抓取，仅供内部参考，请以主办方信息为准。*")
    return "\n".join(lines)


def generate_xlsx(activities: list[Activity]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "活动"
    sheet.append(["活动名称", "城市", "开始时间", "结束时间", "地点", "费用", "类型", "来源", "简介"])
    for item in visible_activities(activities):
        sheet.append([item.name, CITY_NAMES.get(item.city_code, item.city_code), item.start_time.isoformat() if item.start_time else "", item.end_time.isoformat() if item.end_time else "", item.location, item.price, item.type, item.source_url, item.summary])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


NoteReportEntry = tuple[Note, list[Activity], list[NoteImage]]


def _activity_lines(activities: list[Activity]) -> str:
    return "\n".join(
        f"{item.name} | {item.start_time.isoformat() if item.start_time else '时间待确认'} | {item.location} | {item.price} | {item.summary}"
        for item in activities
    )


def generate_note_markdown(week: str, cities: list[str], entries: list[NoteReportEntry]) -> str:
    lines = [f"# 本周推文周报（{week}）", "", f"城市：{'、'.join(CITY_NAMES.get(city, city) for city in cities)}", ""]
    for note, activities, images in entries:
        published = note.published_at.isoformat() if note.published_at else f"{note.created_at.isoformat()}（发布时间待确认）"
        links = [image.original_url or image.storage_key for image in images if image.original_url or image.storage_key]
        ocr = "\n\n".join(image.ocr_text for image in images if image.ocr_text)
        lines.extend([
            f"## {note.title}", "",
            f"- 发布时间：{published}",
            f"- 原文链接：{note.source_url}",
            f"- 图片链接：{'、'.join(links) if links else '无'}", "",
            "### 推文正文", "", note.content or "无", "",
            "### 图片 OCR", "", ocr or "无", "",
            f"### 识别活动（{len(activities)}）", "",
        ])
        if activities:
            for item in activities:
                lines.extend([format_activity_markdown(item), ""])
        else:
            lines.extend(["未识别到活动", ""])
    return "\n".join(lines)


def generate_note_xlsx(entries: list[NoteReportEntry]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "本周推文"
    sheet.append(["推文标题", "发布时间", "城市", "原文链接", "正文", "OCR", "图片链接", "活动数", "活动详情"])
    for note, activities, images in entries:
        published = note.published_at.isoformat() if note.published_at else f"{note.created_at.isoformat()}（待确认）"
        links = "\n".join(image.original_url or image.storage_key for image in images if image.original_url or image.storage_key)
        ocr = "\n".join(image.ocr_text for image in images if image.ocr_text)
        sheet.append([note.title, published, CITY_NAMES.get(note.city_code, note.city_code), note.source_url, note.content, ocr, links, len(activities), _activity_lines(activities)])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
