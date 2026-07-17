from collections import defaultdict
from io import BytesIO

from openpyxl import Workbook

from app.models.activity import Activity


CITY_NAMES = {"shanghai": "上海", "beijing": "北京"}


def format_activity_markdown(activity: Activity) -> str:
    start = activity.start_time.strftime("%Y-%m-%d %H:%M") if activity.start_time else "待确认"
    end = activity.end_time.strftime("%H:%M") if activity.end_time else ""
    time_text = f"{start} - {end}" if end else start
    return f"#### {activity.name}\n- **时间**：{time_text}\n- **地点**：{activity.location}\n- **费用**：{activity.price}\n- **来源**：[小红书笔记]({activity.source_url})\n- **简介**：{activity.summary}\n"


def approved(activities: list[Activity]) -> list[Activity]:
    return [item for item in activities if item.status == "APPROVED" and item.start_time is not None]


def generate_markdown(week: str, cities: list[str], activities: list[Activity]) -> str:
    selected = approved(activities)
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
            for item in sorted(grouped[city][kind], key=lambda value: (value.start_time, value.id or 0)):
                lines.extend([format_activity_markdown(item), ""])
    lines.append("*本内容由系统自动抓取，仅供内部参考，请以主办方信息为准。*")
    return "\n".join(lines)


def generate_xlsx(activities: list[Activity]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "活动"
    sheet.append(["活动名称", "城市", "开始时间", "结束时间", "地点", "费用", "类型", "来源", "简介"])
    for item in approved(activities):
        sheet.append([item.name, CITY_NAMES.get(item.city_code, item.city_code), item.start_time.isoformat() if item.start_time else "", item.end_time.isoformat() if item.end_time else "", item.location, item.price, item.type, item.source_url, item.summary])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
