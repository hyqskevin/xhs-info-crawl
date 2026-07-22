"""poster_tasks CRUD + preview + candidates + render tests."""
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.poster import PosterTask, PosterTemplate


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def _seed_template(db: Session, name: str = "TPL") -> PosterTemplate:
    tpl = PosterTemplate(
        name=name,
        html_template='<div class="poster"><h1>{{title}}</h1>{{items}}</div>',
        css_text='.poster{background:#F26B2C;color:#fff;padding:60px;font-family:sans-serif;}',
    )
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return tpl


def test_create_poster_task_minimal(client: TestClient, db_session: Session) -> None:
    tpl = _seed_template(db_session)
    resp = client.post(
        "/api/v1/poster-tasks",
        json={"name": "营销海报-7月", "template_id": tpl.id, "items": []},
        headers=_auth(),
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["name"] == "营销海报-7月"
    assert body["status"] == "draft"
    assert body["output_format"] == "png"


def test_create_poster_task_invalid_template(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/poster-tasks",
        json={"name": "x", "template_id": 99999, "items": []},
        headers=_auth(),
    )
    assert resp.status_code == 422


def test_update_poster_task_items(client: TestClient, db_session: Session) -> None:
    tpl = _seed_template(db_session, "TPL2")
    create = client.post(
        "/api/v1/poster-tasks",
        json={"name": "T2", "template_id": tpl.id, "items": []},
        headers=_auth(),
    )
    tid = create.json()["data"]["id"]
    items = [{
        "type": "note", "id": 1, "title": "宁波周末活动",
        "fields": {"time_range": "7.4 16:00", "location": "宁波万象汇", "fee": "免费", "content": "卷被子大赛"},
        "image_url": "/api/v1/posters/note-image-by-id/1",
    }, {
        "type": "activity", "id": 5, "note_id": 1, "title": "卷被子",
        "fields": {"time_range": "7.4 16:00-17:00", "location": "宁波万象汇L1小中庭", "fee": "免费|需报名", "content": ""},
        "image_url": "",
    }]
    upd = client.put(
        f"/api/v1/poster-tasks/{tid}",
        json={"items": items},
        headers=_auth(),
    )
    assert upd.status_code == 200
    assert len(upd.json()["data"]["items"]) == 2
    fetched = db_session.get(PosterTask, tid)
    assert fetched.items[1]["note_id"] == 1


def test_preview_renders_items(client: TestClient, db_session: Session) -> None:
    tpl = _seed_template(db_session, "PREVIEW")
    create = client.post(
        "/api/v1/poster-tasks",
        json={
            "name": "宁波周末活动",
            "template_id": tpl.id,
            "items": [{
                "type": "note", "id": 1, "title": "卷被子大赛",
                "fields": {"time_range": "7.4 16:00", "location": "宁波万象汇", "fee": "免费", "content": ""},
                "image_url": "",
            }],
        },
        headers=_auth(),
    )
    tid = create.json()["data"]["id"]
    preview = client.get(f"/api/v1/poster-tasks/{tid}/preview", headers=_auth())
    assert preview.status_code == 200
    html = preview.json()["data"]["html"]
    assert "宁波周末活动" in html
    assert "🕐" in html  # emoji present
    assert "卷被子大赛" in html


def test_candidates_returns_notes(client: TestClient, db_session: Session) -> None:
    from app.models.note import Note

    for i in range(3):
        db_session.add(Note(
            task_id=0,
            platform_note_id=f"platform-{i}",
            title=f"候选推文 {i}",
            content="content",
            source_url=f"https://xhs.demo/{i}",
            city_code="nb",
            status="PROCESSED",
            review_status="APPROVED",
            raw_data={},
        ))
    db_session.commit()

    resp = client.get("/api/v1/poster-tasks/candidates?city_code=nb", headers=_auth())
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) >= 3
    for item in items:
        assert item["type"] == "note"


def test_delete_poster_task(client: TestClient, db_session: Session) -> None:
    tpl = _seed_template(db_session, "DEL_T")
    create = client.post(
        "/api/v1/poster-tasks",
        json={"name": "DEL_TASK", "template_id": tpl.id, "items": []},
        headers=_auth(),
    )
    tid = create.json()["data"]["id"]
    resp = client.delete(f"/api/v1/poster-tasks/{tid}", headers=_auth())
    assert resp.status_code == 200
    get_resp = client.get(f"/api/v1/poster-tasks/{tid}", headers=_auth())
    assert get_resp.status_code == 404


def test_render_with_mocked_opencli(client: TestClient, db_session: Session, monkeypatch) -> None:
    import subprocess
    from pathlib import Path

    tpl = _seed_template(db_session, "RENDER_MOCK")
    create = client.post(
        "/api/v1/poster-tasks",
        json={
            "name": "RENDER-TASK",
            "template_id": tpl.id,
            "items": [{
                "type": "note", "id": 1, "title": "卷被子",
                "fields": {"time_range": "7.4 16:00", "location": "宁波", "fee": "免费", "content": ""},
                "image_url": "",
            }],
        },
        headers=_auth(),
    )
    tid = create.json()["data"]["id"]

    # 让 playwright unavailable，强制 fallback opencli；
    # 同时 mock subprocess.run 让 opencli 写一个合法 png。
    from app.services import poster_renderer as renderer_module

    monkeypatch.setattr(renderer_module, "_playwright_available", lambda: False)

    def fake_run(cmd, capture_output, text, timeout):
        # cmd = ['opencli', 'screenshot', '--html', tmp, '--output', path, '--full-page']
        path = cmd[5]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        class R:
            returncode = 0
            stderr = ""
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)

    render = client.post(f"/api/v1/poster-tasks/{tid}/render", headers=_auth())
    assert render.status_code == 200
    body = render.json()["data"]
    assert body["url"].endswith("/download")
    # 下载文件
    resp = client.get(f"/api/v1/poster-tasks/{tid}/download", headers=_auth())
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/png")
