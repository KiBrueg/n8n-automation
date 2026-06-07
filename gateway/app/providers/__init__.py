"""Провайдеры LLM и транскрипции за единым интерфейсом.

Ядро вызывает get_chat_provider()/get_transcriber() и не знает деталей.
Добавить нового провайдера = добавить класс + ветку в фабрике, роуты не трогаем.
"""
from .base import ChatProvider, Transcriber, ProviderError
from .factory import get_chat_provider, get_transcriber

__all__ = [
    "ChatProvider",
    "Transcriber",
    "ProviderError",
    "get_chat_provider",
    "get_transcriber",
]
