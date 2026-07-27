"""OPENCLI_BIN 配置化与 run_crawl 启动预检测试。

关联 spec: docs/superpowers/specs/2026-07-27-opencli-bin-config-and-preflight-design.md
关联事件：2026-07-27 worker 重启环境 PATH 缺 nvm bin 导致定时任务全部 Errno 2
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.config import City
from app.models.task import CrawlTask, TaskLog
from app.services.crawler import OpenCLIError
from app.services.opencli_adapter import OpenCLIAdapter
from app.tasks import crawl_task as crawl_task_module
from app.tasks.crawl_task import run_crawl


def _settings(**overrides) -> Settings:
    base = {"secret_key": "pytest-only-jwt-secret-at-least-32-bytes"}
    base.update(overrides)
    return Settings(**base)


def test_settings_opencli_bin_defaults_and_overrides() -> None:
    assert _settings().opencli_bin == "opencli"
    assert _settings(opencli_bin="/custom/bin/opencli").opencli_bin == "/custom/bin/opencli"


def test_adapter_uses_configured_bin(monkeypatch) -> None:
    popen_calls: list[list[str]] = []

    class FakeProc:
        returncode = 0

        def communicate(self, timeout=None):
            return ("{}", "")

    monkeypatch.setattr("app.services.opencli_adapter.subprocess.Popen", lambda argv, **kw: popen_calls.append(argv) or FakeProc())

    adapter = OpenCLIAdapter(_settings(opencli_bin="/custom/bin/opencli"))
    adapter.run(["xiaohongshu", "whoami"], enforce_execution=False)

    assert popen_calls[0][0] == "/custom/bin/opencli"


def test_adapter_missing_binary_raises_actionable_error(monkeypatch) -> None:
    def raise_not_found(argv, **kw):
        raise FileNotFoundError(2, "No such file or directory", argv[0])

    monkeypatch.setattr("app.services.opencli_adapter.subprocess.Popen", raise_not_found)

    adapter = OpenCLIAdapter(_settings(opencli_bin="/nonexistent/opencli-xyz"))
    try:
        adapter.run(["xiaohongshu", "whoami"], enforce_execution=False)
    except OpenCLIError as exc:
        message = str(exc)
    else:
        raise AssertionError("应抛出 OpenCLIError")
    assert "opencli 不可用" in message
    assert "/nonexistent/opencli-xyz" in message
    assert "OPENCLI_BIN" in message


def _seed_task(db: Session, token: str) -> CrawlTask:
    if db.scalar(select(City).where(City.code == "nb")) is None:
        db.add(City(name="宁波", code="nb", enabled=True, recent_filter="一周内"))
    task = CrawlTask(
        type="keyword",
        status="PENDING",
        run_token=token,
        params={"city": "nb", "keywords": ["活动"], "recent_filter": "一周内", "blogger_ids": []},
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def test_run_crawl_preflight_fails_fast_when_opencli_missing(db_session: Session, monkeypatch) -> None:
    task = _seed_task(db_session, "preflight-token")
    monkeypatch.setattr(crawl_task_module, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(crawl_task_module, "find_opencli", lambda _bin: None)
    constructed: list = []
    monkeypatch.setattr(
        crawl_task_module, "OpenCLIAdapter", lambda *a, **kw: constructed.append(1) or None
    )

    run_crawl.run(task.id, "preflight-token")

    current = db_session.get(CrawlTask, task.id)
    assert current.status == "FAILED"
    assert "opencli 不可用" in current.error_message
    assert "OPENCLI_BIN" in current.error_message
    assert current.finished_at is not None
    assert constructed == []  # 预检失败不应创建 adapter
    logs = list(db_session.scalars(select(TaskLog.message).where(TaskLog.task_id == task.id)))
    assert any("opencli 不可用" in message for message in logs)


def test_run_crawl_preflight_invokes_find_opencli(db_session: Session, monkeypatch) -> None:
    task = _seed_task(db_session, "preflight-ok-token")
    seen: list[str] = []
    monkeypatch.setattr(crawl_task_module, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(crawl_task_module, "find_opencli", lambda bin_name: seen.append(bin_name) or "/fake/opencli")

    class FakeAdapter:
        def __init__(self, _settings):
            pass

        def check_login(self):
            return {"logged_in": True}

        def search_recent(self, _query, _recent_filter):
            return []

    monkeypatch.setattr(crawl_task_module, "OpenCLIAdapter", FakeAdapter)

    run_crawl.run(task.id, "preflight-ok-token")

    assert seen == ["opencli"]
    assert db_session.get(CrawlTask, task.id).status == "COMPLETED"
