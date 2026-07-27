"""海报渲染器测试：外框 + 三列布局 + 图片 URL 解析。

关联 spec: docs/superpowers/specs/2026-07-22-poster-format-fix-design.md
"""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.models.note import Note, NoteImage
from app.models.poster import PosterTask, PosterTemplate
from app.services.poster_renderer import (
    _render_html_to_png,
    _render_item_html,
    render_poster_preview_html,
    render_task_to_png,
    resolve_item_image_urls,
)


# ── _render_item_html ──────────────────────────────────────────────


def test_render_item_html_with_image_shows_card() -> None:
    """有 image_url 时渲染卡片：文字在左 + 图片在右。"""
    item = {
        "type": "note",
        "id": 1,
        "title": "卷被子大赛",
        "fields": {
            "time_range": "7.4 16:00",
            "location": "宁波万象汇",
            "fee": "免费",
            "content": "快来参加",
        },
        "image_url": "/api/v1/posters/note-image-by-id/1",
    }
    html = _render_item_html(item, 400, bg_color="#FDF5EE")
    assert "card-img" in html
    assert "card-body" in html
    assert "card-image" in html
    assert "card-title" in html
    assert "卷被子大赛" in html
    assert "宁波万象汇" in html
    assert "免费" in html
    assert "快来参加" in html
    assert "/api/v1/posters/note-image-by-id/1" in html
    assert 'width="240"' in html  # 图片列
    # 图片在文字之后（右侧）
    body_pos = html.index("card-body")
    img_pos = html.index("card-img")
    assert body_pos < img_pos, "文字应在左，图片在右"


def test_render_item_html_without_image_no_img_cell() -> None:
    """image_url 为空时不渲染图片列。"""
    item = {
        "type": "note",
        "id": 2,
        "title": "无图活动",
        "fields": {"time_range": "", "location": "", "fee": "", "content": ""},
        "image_url": "",
    }
    html = _render_item_html(item, 400)
    assert "card-body" in html
    assert "card-title" in html
    assert "card-img" not in html


def test_render_item_html_escapes_html() -> None:
    """标题中的 HTML 标签应被转义。"""
    item = {
        "type": "note",
        "id": 3,
        "title": '<script>alert("xss")</script>',
        "fields": {"time_range": "", "location": "", "fee": "", "content": ""},
        "image_url": "",
    }
    html = _render_item_html(item, 400)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


# ── render_poster_preview_html ─────────────────────────────────────


def test_preview_html_has_outer_frame() -> None:
    """生成的 HTML 包含 poster-outer 外框和 poster 内白卡片。"""
    tpl = PosterTemplate(
        name="test", html_template='<div class="poster">{{items}}</div>', css_text=""
    )
    task = PosterTask(name="测试海报", template_id=1, items=[])
    html = render_poster_preview_html(tpl, task)
    assert "poster-outer" in html
    assert 'class="poster"' in html
    assert "background:#F26B2C" in html  # 外框色


def test_preview_html_items_override() -> None:
    """items_override 参数应覆盖 task.items。"""
    tpl = PosterTemplate(
        name="test", html_template='<div class="poster">{{items}}</div>', css_text=""
    )
    task = PosterTask(
        name="原任务",
        template_id=1,
        items=[
            {
                "type": "note",
                "id": 1,
                "title": "原始标题",
                "fields": {"time_range": "", "location": "", "fee": "", "content": ""},
                "image_url": "",
            }
        ],
    )
    override = [
        {
            "type": "note",
            "id": 2,
            "title": "覆盖标题",
            "fields": {"time_range": "", "location": "", "fee": "", "content": ""},
            "image_url": "/override.png",
        }
    ]
    html = render_poster_preview_html(tpl, task, items_override=override)
    assert "覆盖标题" in html
    assert "/override.png" in html
    assert "原始标题" not in html


def test_preview_html_title_block() -> None:
    """当模板不含 {{title}} 时，自动生成 title_block。"""
    tpl = PosterTemplate(
        name="test", html_template='<div class="poster">{{items}}</div>', css_text=""
    )
    task = PosterTask(name="周末活动合集", template_id=1, items=[])
    html = render_poster_preview_html(tpl, task)
    assert "poster-header" in html
    assert "周末活动合集" in html


# ── resolve_item_image_urls ────────────────────────────────────────


def test_resolve_image_urls_converts_api_path(db_session: Session) -> None:
    """API 路径应解析为本地 file:// 路径。"""
    note = Note(
        task_id=1,
        platform_note_id="test-platform-1",
        title="test",
        source_url="http://x.com/1",
        city_code="330200",
        status="PUBLISHED",
    )
    db_session.add(note)
    db_session.commit()
    db_session.refresh(note)

    image = NoteImage(note_id=note.id, storage_key="test-images/img.jpg", original_url="http://x.com/1.jpg")
    db_session.add(image)
    db_session.commit()
    db_session.refresh(image)

    items = [
        {
            "type": "note",
            "id": 1,
            "title": "test",
            "fields": {},
            "image_url": f"/api/v1/posters/note-image-by-id/{image.id}",
        }
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir) / "data"
        img_dir = data_dir / "test-images"
        img_dir.mkdir(parents=True)
        (img_dir / "img.jpg").write_text("fake image")

        resolved = resolve_item_image_urls(items, db_session, str(data_dir))
        assert resolved[0]["image_url"].startswith("file://")
        assert "img.jpg" in resolved[0]["image_url"]


def test_resolve_image_urls_skips_non_api_paths(db_session: Session) -> None:
    """非 API 路径的 image_url 保持不变。"""
    items = [
        {
            "type": "note",
            "id": 1,
            "title": "test",
            "fields": {},
            "image_url": "https://example.com/img.jpg",
        }
    ]
    resolved = resolve_item_image_urls(items, db_session, "/tmp")
    assert resolved[0]["image_url"] == "https://example.com/img.jpg"


def test_resolve_image_urls_empty_image_url(db_session: Session) -> None:
    """空 image_url 保持为空。"""
    items = [
        {
            "type": "note",
            "id": 1,
            "title": "test",
            "fields": {},
            "image_url": "",
        }
    ]
    resolved = resolve_item_image_urls(items, db_session, "/tmp")
    assert resolved[0]["image_url"] == ""


def test_resolve_image_urls_empty_items(db_session: Session) -> None:
    """空列表返回空列表。"""
    resolved = resolve_item_image_urls([], db_session, "/tmp")
    assert resolved == []


# ── _render_html_to_png ────────────────────────────────────────────


def test_render_html_to_png_writes_file() -> None:
    """_render_html_to_png 应写入 PNG 文件。"""
    html = "<html><body><h1>test</h1></body></html>"
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "test.png"
        with patch(
            "app.services.poster_renderer._opencli_render",
            side_effect=lambda h, p: Path(p).write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            ),
        ):
            path = _render_html_to_png(html, str(out))
            assert path == str(out)
            assert out.exists()
            magic = out.read_bytes()[:8]
            assert magic == b"\x89PNG\r\n\x1a\n"


def test_render_html_to_png_creates_parent_dirs() -> None:
    """输出目录不存在时自动创建。"""
    html = "<html><body><h1>test</h1></body></html>"
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "sub" / "deep" / "test.png"
        assert not out.parent.exists()
        with patch(
            "app.services.poster_renderer._opencli_render",
            side_effect=lambda h, p: Path(p).write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            ),
        ):
            path = _render_html_to_png(html, str(out))
            assert path == str(out)
            assert out.exists()


# ── render_task_to_png ─────────────────────────────────────────────


def test_render_task_to_png_basic() -> None:
    """基本渲染流程。"""
    tpl = PosterTemplate(
        name="test", html_template='<div class="poster">{{items}}</div>', css_text=""
    )
    task = PosterTask(
        name="test",
        template_id=1,
        items=[
            {
                "type": "note",
                "id": 1,
                "title": "活动1",
                "fields": {"time_range": "7.4", "location": "宁波", "fee": "免费", "content": ""},
                "image_url": "",
            }
        ],
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "poster.png"
        with patch(
            "app.services.poster_renderer._opencli_render",
            side_effect=lambda h, p: Path(p).write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            ),
        ):
            path = render_task_to_png(tpl, task, str(out))
            assert path == str(out)
            assert out.exists()
            magic = out.read_bytes()[:8]
            assert magic == b"\x89PNG\r\n\x1a\n"