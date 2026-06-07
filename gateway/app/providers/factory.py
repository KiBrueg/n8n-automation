"""Фабрики провайдеров — выбирают реализацию по конфигу."""
from __future__ import annotations

from ..config import Settings
from .base import ChatProvider, ProviderError, Transcriber
from .chat import OllamaChat, OpenRouterChat
from .stub import StubChat
from .transcribe import OpenAIWhisper, WhisperLocal

_CHAT = {"stub": StubChat, "ollama": OllamaChat, "openrouter": OpenRouterChat}
_TRANSCRIBE = {"whisper_local": WhisperLocal, "openai_whisper": OpenAIWhisper}


def get_chat_provider(settings: Settings, name: str | None = None) -> ChatProvider:
    key = name or settings.llm_provider
    cls = _CHAT.get(key)
    if cls is None:
        raise ProviderError("неизвестный chat-провайдер: " + str(key))
    return cls(settings)


def get_transcriber(settings: Settings) -> Transcriber | None:
    if settings.transcribe_provider == "none":
        return None
    cls = _TRANSCRIBE.get(settings.transcribe_provider)
    if cls is None:
        raise ProviderError("неизвестный транскрайбер: " + str(settings.transcribe_provider))
    return cls(settings)
