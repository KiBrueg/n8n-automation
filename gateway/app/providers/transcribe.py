"""Транскрайберы голоса: локальный Whisper-совместимый сервис или OpenAI Whisper."""
from __future__ import annotations

import httpx

from ..config import Settings
from .base import ProviderError, Transcriber


async def _fetch_audio(url: str, timeout: float) -> bytes:
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.content


class WhisperLocal(Transcriber):
    """Локальный Whisper-совместимый HTTP-сервис (например, faster-whisper /asr)."""

    name = "whisper_local"

    def __init__(self, settings: Settings):
        self._url = settings.whisper_base_url.rstrip("/") + "/asr"
        self._model = settings.whisper_model
        self._timeout = settings.llm_timeout_seconds

    async def transcribe(self, audio_url: str) -> str:
        try:
            audio = await _fetch_audio(audio_url, self._timeout)
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(
                    self._url,
                    params={"model": self._model, "output": "text"},
                    files={"audio_file": ("audio", audio)},
                )
                r.raise_for_status()
                return r.text.strip()
        except httpx.HTTPError as e:
            raise ProviderError(f"whisper_local: {e}") from e


class OpenAIWhisper(Transcriber):
    name = "openai_whisper"

    def __init__(self, settings: Settings):
        if not settings.openai_api_key:
            raise ProviderError("openai_whisper: OPENAI_API_KEY не задан")
        self._key = settings.openai_api_key
        self._timeout = settings.llm_timeout_seconds

    async def transcribe(self, audio_url: str) -> str:
        try:
            audio = await _fetch_audio(audio_url, self._timeout)
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self._key}"},
                    data={"model": "whisper-1"},
                    files={"file": ("audio.ogg", audio)},
                )
                r.raise_for_status()
                return r.json().get("text", "").strip()
        except (httpx.HTTPError, KeyError) as e:
            raise ProviderError(f"openai_whisper: {e}") from e
