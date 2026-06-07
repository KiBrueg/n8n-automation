"""Чат-провайдеры: Ollama (локально) и OpenRouter (облако)."""
from __future__ import annotations

import httpx

from ..config import Settings
from .base import ChatProvider, ProviderError

_JSON_GUARD = (
    "Отвечай СТРОГО одним JSON-объектом по схеме Decision, без markdown, "
    "без пояснений вне JSON."
)


class OllamaChat(ChatProvider):
    name = "ollama"

    def __init__(self, settings: Settings):
        self._url = settings.ollama_base_url.rstrip("/") + "/api/chat"
        self._model = settings.ollama_model
        self._timeout = settings.llm_timeout_seconds

    async def complete_json(self, system_prompt: str, user_content: str) -> str:
        payload = {
            "model": self._model,
            "format": "json",  # Ollama: принудительный JSON
            "stream": False,
            "messages": [
                {"role": "system", "content": f"{system_prompt}\n{_JSON_GUARD}"},
                {"role": "user", "content": user_content},
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(self._url, json=payload)
                r.raise_for_status()
                return r.json()["message"]["content"]
        except (httpx.HTTPError, KeyError) as e:
            raise ProviderError(f"ollama: {e}") from e


class OpenRouterChat(ChatProvider):
    name = "openrouter"

    def __init__(self, settings: Settings):
        if not settings.openrouter_api_key:
            raise ProviderError("openrouter: OPENROUTER_API_KEY не задан")
        self._url = settings.openrouter_base_url.rstrip("/") + "/chat/completions"
        self._model = settings.openrouter_model
        self._key = settings.openrouter_api_key
        self._timeout = settings.llm_timeout_seconds

    async def complete_json(self, system_prompt: str, user_content: str) -> str:
        payload = {
            "model": self._model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": f"{system_prompt}\n{_JSON_GUARD}"},
                {"role": "user", "content": user_content},
            ],
        }
        headers = {"Authorization": f"Bearer {self._key}"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(self._url, json=payload, headers=headers)
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError) as e:
            raise ProviderError(f"openrouter: {e}") from e
