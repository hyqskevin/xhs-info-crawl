"""海报模型单元测试。"""
from sqlalchemy.orm import Session

from app.models.poster import PosterTask, PosterTemplate


def test_template_unique_name(db_session: Session) -> None:
    a = PosterTemplate(name="橙橙周末合集", html_template="<div/>")
    db_session.add(a)
    db_session.commit()
    b = PosterTemplate(name="橙橙周末合集", html_template="<p/>")
    db_session.add(b)
    try:
        db_session.commit()
        assert False, "应该 unique 失败"
    except Exception:
        db_session.rollback()


def test_template_parsed_meta_accepts_dict(db_session: Session) -> None:
    meta = {"fonts": ["PingFang"], "colors": {"primary": "#F26B2C"}, "emoji": ["🕐"]}
    t = PosterTemplate(name="带 meta 模板", html_template="<div/>", parsed_meta=meta, source="minimax-vision")
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    assert t.parsed_meta == meta


def test_task_status_default_draft(db_session: Session) -> None:
    tpl = PosterTemplate(name="t1", html_template="<div/>")
    db_session.add(tpl)
    db_session.commit()
    db_session.refresh(tpl)
    task = PosterTask(name="营销海报", template_id=tpl.id)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.status == "draft"
    assert task.output_format == "png"


def test_task_items_json_list(db_session: Session) -> None:
    tpl = PosterTemplate(name="t2", html_template="<div/>")
    db_session.add(tpl)
    db_session.commit()
    db_session.refresh(tpl)
    items = [
        {"type": "note", "id": 1, "title": "宁波周末活动",
         "fields": {"time_range": "7.4 16:00", "location": "宁波万象汇", "fee": "免费", "content": ""},
         "image_url": "/data/images/note-1/0.jpg"},
        {"type": "activity", "id": 5, "note_id": 1, "title": "卷被子大赛",
         "fields": {"time_range": "7.4 16:00-17:00", "location": "宁波万象汇L1小中庭", "fee": "免费", "content": ""},
         "image_url": "/data/images/note-1/1.jpg"},
    ]
    task = PosterTask(name="t2 任务", template_id=tpl.id, items=items)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert len(task.items) == 2
    assert task.items[1]["note_id"] == 1


def test_task_remove_template_restricted(db_session: Session) -> None:
    """FK ondelete=RESTRICT：删除被引用模板时 task 不应能删除。"""
    tpl = PosterTemplate(name="t3", html_template="<div/>")
    db_session.add(tpl)
    db_session.commit()
    db_session.refresh(tpl)
    task = PosterTask(name="depend", template_id=tpl.id)
    db_session.add(task)
    db_session.commit()

    db_session.delete(tpl)
    try:
        db_session.commit()
        assert False, "应该被 RESTRICT 阻止"
    except Exception:
        db_session.rollback()
