import json
from typing import Any

import httpx

from app.core.config import Settings


class MiniMaxError(RuntimeError):
    pass


class MiniMaxClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self.transport = transport

    def extract(self, text: str) -> dict[str, Any]:
        if not self.settings.minimax_api_key:
            raise MiniMaxError("MINIMAX_API_KEY is not configured")
        url = f"{self.settings.minimax_base_url.rstrip('/')}/{self.settings.minimax_chat_path.lstrip('/')}"
        payload = {
            "model": self.settings.minimax_model,
            "messages": [
                {"role": "system", "name": "extractor", "content": "Extract event fields and return one JSON object."},
                {"role": "user", "name": "user", "content": text},
            ],
            "max_completion_tokens": 1024,
        }
        with httpx.Client(transport=self.transport, timeout=30) as client:
            response = client.post(url, headers={"Authorization": f"Bearer {self.settings.minimax_api_key}", "Content-Type": "application/json"}, json=payload)
        if response.status_code != 200:
            raise MiniMaxError(f"MiniMax HTTP {response.status_code}")
        body = response.json()
        base_resp = body.get("base_resp") or {}
        if base_resp.get("status_code") not in (None, 0):
            raise MiniMaxError(str(base_resp.get("status_msg") or base_resp.get("status_code")))
        try:
            content = body["choices"][0]["message"]["content"]
            if content.startswith("```json"):
                content = content.removeprefix("```json").removesuffix("```").strip()
            result = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise MiniMaxError("MiniMax returned invalid structured output") from exc
        if not isinstance(result, dict):
            raise MiniMaxError("MiniMax returned non-object output")
        return result
