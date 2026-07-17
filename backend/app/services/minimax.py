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
        return self._request(text, "Extract event fields and return one JSON object.", 1024)

    def extract_many(self, text: str) -> dict[str, Any]:
        instruction = (
            "Extract every distinct concrete event from the note and OCR text. Return one JSON object with an activities array. "
            "Each activity must contain name, start_time, end_time, location, price, type, summary, confidence, and source_image_indexes. "
            "Use ISO 8601 date-time strings for start_time and end_time. "
            "Do not create one summary event for the whole note. IMAGE markers identify source image indexes. Use null for unknown values."
        )
        tools=[{"type":"function","function":{"name":"emit_activities","description":"Return every distinct concrete activity found in the note and OCR images.","parameters":{"type":"object","properties":{"activities":{"type":"array","items":{"type":"object","properties":{"name":{"type":"string"},"start_time":{"type":["string","null"]},"end_time":{"type":["string","null"]},"location":{"type":["string","null"]},"price":{"type":["string","null"]},"type":{"type":["string","null"]},"summary":{"type":["string","null"]},"confidence":{"type":["number","string"]},"source_image_indexes":{"type":"array","items":{"type":"integer"}}},"required":["name","start_time","location","source_image_indexes"]}}},"required":["activities"]}}}]
        return self._request(text, instruction+" You must call emit_activities exactly once.", 16384, tools)

    def _request(self, text: str, instruction: str, max_tokens: int, tools: list[dict[str,Any]] | None = None) -> dict[str, Any]:
        if not self.settings.minimax_api_key:
            raise MiniMaxError("MINIMAX_API_KEY is not configured")
        url = f"{self.settings.minimax_base_url.rstrip('/')}/{self.settings.minimax_chat_path.lstrip('/')}"
        payload = {
            "model": self.settings.minimax_model,
            "messages": [
                {"role": "system", "name": "extractor", "content": instruction},
                {"role": "user", "name": "user", "content": text},
            ],
            "max_completion_tokens": max_tokens,
        }
        if tools:
            payload["tools"]=tools; payload["tool_choice"]="auto"
        with httpx.Client(transport=self.transport, timeout=self.settings.minimax_timeout_seconds) as client:
            response = client.post(url, headers={"Authorization": f"Bearer {self.settings.minimax_api_key}", "Content-Type": "application/json"}, json=payload)
        if response.status_code != 200:
            raise MiniMaxError(f"MiniMax HTTP {response.status_code}")
        body = response.json()
        base_resp = body.get("base_resp") or {}
        if base_resp.get("status_code") not in (None, 0):
            raise MiniMaxError(str(base_resp.get("status_msg") or base_resp.get("status_code")))
        try:
            message=body["choices"][0]["message"]
            tool_calls=message.get("tool_calls") or []
            content=tool_calls[0]["function"]["arguments"] if tool_calls else message["content"]
            if isinstance(content,dict): return content
            if content.startswith("```json"):
                content = content.removeprefix("```json").removesuffix("```").strip()
            result = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise MiniMaxError("MiniMax returned invalid structured output") from exc
        if not isinstance(result, dict):
            raise MiniMaxError("MiniMax returned non-object output")
        return result
