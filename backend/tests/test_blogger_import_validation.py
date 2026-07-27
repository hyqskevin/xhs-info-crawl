"""博主批量导入文件校验测试。"""
import io

import pytest
from openpyxl import Workbook

from app.services.blogger_import import (
    BloggerImportError,
    HEADERS,
    MAX_ROWS,
    generate_blogger_template,
    import_bloggers,
    parse_blogger_import,
)


def _xlsx_bytes(rows: list[list[str]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(HEADERS)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_template_has_expected_headers() -> None:
    payload = generate_blogger_template()
    assert payload[:2] == b"PK"  # xlsx 魔数


def test_parse_valid_xlsx_returns_dataclass_rows() -> None:
    payload = _xlsx_bytes([
        ["小红", "u-1", "https://xhs.example/u-1", "上海", "是"],
        ["小蓝", "", "", "杭州", "否"],
    ])
    parsed = parse_blogger_import(payload, "bloggers.xlsx")
    assert [r.username for r in parsed] == ["小红", "小蓝"]
    assert parsed[1].enabled is False


def test_parse_rejects_missing_username() -> None:
    payload = _xlsx_bytes([["", "u-1", "https://xhs/u-1", "上海", "是"]])
    with pytest.raises(BloggerImportError):
        parse_blogger_import(payload, "bloggers.xlsx")


def test_parse_rejects_wrong_header() -> None:
    # 表头缺失，期望拒收
    payload = _xlsx_bytes([["Username", "ID"]])
    with pytest.raises(BloggerImportError):
        parse_blogger_import(payload, "bloggers.xlsx")


def test_parse_rejects_too_many_rows() -> None:
    big = [["u" + str(i), "", "", "上海", "是"] for i in range(MAX_ROWS + 1)]
    payload = _xlsx_bytes(big)
    with pytest.raises(BloggerImportError):
        parse_blogger_import(payload, "bloggers.xlsx")


def test_parse_rejects_invalid_enabled_value() -> None:
    payload = _xlsx_bytes([["小红", "u-1", "https://xhs/u-1", "上海", "随便"]])
    with pytest.raises(BloggerImportError):
        parse_blogger_import(payload, "bloggers.xlsx")


def test_parse_rejects_unknown_file_suffix() -> None:
    payload = b"just some text"
    with pytest.raises(BloggerImportError):
        parse_blogger_import(payload, "bloggers.txt")


def test_import_bloggers_writes_to_db(tmp_path) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.database import Base
    from app.models.config import Blogger, City

    engine = create_engine(f"sqlite:///{tmp_path / 'imp.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with SessionLocal() as db:
        db.add(City(name="上海", code="sh", enabled=True))
        db.commit()

    payload = _xlsx_bytes([["小红", "u-1", "https://xhs/u-1", "上海", "是"]])
    with SessionLocal() as db:
        result = import_bloggers(db, payload, "bloggers.xlsx")
    assert result["created"] == 1
    assert result["updated"] == 0

    with SessionLocal() as db:
        names = {b.username for b in db.query(Blogger).all()}
        assert names == {"小红"}
