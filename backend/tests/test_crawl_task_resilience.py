from app.services.crawler import AuthenticationRequired
from app.services.pipeline import deduplicate_results, process_with_isolation, run_stage


def test_run_stage_retries_a_temporary_failure():
    attempts = []
    def operation():
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("temporary")
        return "ok"

    assert run_stage(operation, attempts=2, delay_seconds=0) == "ok"
    assert len(attempts) == 2


def test_search_results_are_deduplicated_by_source_url():
    rows = [("nb", {"title": "A", "url": "https://xhs/1"}), ("nb", {"title": "A2", "url": "https://xhs/1"}), ("nb", {"title": "B", "url": "https://xhs/2"})]
    assert [item[1]["url"] for item in deduplicate_results(rows)] == ["https://xhs/1", "https://xhs/2"]


def test_one_item_failure_does_not_stop_the_remaining_items():
    completed = []
    failed = []
    def processor(item):
        if item == "broken":
            raise ValueError("bad note")
        completed.append(item)

    process_with_isolation(["broken", "good"], processor, lambda item, exc: failed.append((item, str(exc))))

    assert completed == ["good"]
    assert failed == [("broken", "bad note")]


def test_authentication_failure_still_stops_the_batch():
    def processor(_):
        raise AuthenticationRequired("login")

    try:
        process_with_isolation(["note"], processor, lambda *_: None)
    except AuthenticationRequired as exc:
        assert str(exc) == "login"
    else:
        raise AssertionError("AuthenticationRequired must escape item isolation")
