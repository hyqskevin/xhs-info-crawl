from app.tasks.celery_app import celery_app


def test_pytest_uses_an_in_memory_celery_broker() -> None:
    assert celery_app.conf.broker_url == "memory://"
