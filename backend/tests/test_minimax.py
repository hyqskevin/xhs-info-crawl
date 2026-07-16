import json

import httpx
import pytest

from app.core.config import Settings
from app.services.minimax import MiniMaxClient, MiniMaxError


def test_minimax_client_uses_env_configuration_and_parses_json(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.minimaxi.com/v1/text/chatcompletion_v2"
        assert request.headers["authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "MiniMax-M2.7"
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"name":"活动"}'}}], "base_resp": {"status_code": 0}})

    settings = Settings(project_root=tmp_path, minimax_api_key="test-key", minimax_base_url="https://api.minimaxi.com/v1", minimax_chat_path="/text/chatcompletion_v2", minimax_model="MiniMax-M2.7")
    assert MiniMaxClient(settings, httpx.MockTransport(handler)).extract("活动文本") == {"name": "活动"}


@pytest.mark.parametrize("status,body", [(401, {}), (200, {"base_resp": {"status_code": 1008, "status_msg": "余额不足"}}), (200, {"choices": []})])
def test_minimax_client_raises_typed_error(status: int, body: dict, tmp_path) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(status, json=body))
    settings = Settings(project_root=tmp_path, minimax_api_key="test-key")
    with pytest.raises(MiniMaxError):
        MiniMaxClient(settings, transport).extract("活动文本")
