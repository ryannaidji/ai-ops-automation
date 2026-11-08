"""Minimal client for an OpenAI-compatible chat endpoint (local Ollama by default).

Uses JSON-schema structured output (`response_format`), which Ollama supports on /v1.
"""
from __future__ import annotations

import json
from typing import Any, Protocol

import httpx


class LLMError(RuntimeError):
    pass


class ChatLLM(Protocol):
    def chat_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]: ...


class OpenAICompatLLM:
    def __init__(self, base_url: str, model: str, timeout_s: float = 120.0, api_key: str = "ollama"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = httpx.Client(timeout=timeout_s, headers={"Authorization": f"Bearer {api_key}"})

    def chat_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "out", "schema": schema, "strict": True},
            },
        }
        try:
            r = self.client.post(f"{self.base_url}/chat/completions", json=body)
            r.raise_for_status()
            return json.loads(r.json()["choices"][0]["message"]["content"])
        except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as e:
            raise LLMError(f"LLM call failed: {e}") from e
