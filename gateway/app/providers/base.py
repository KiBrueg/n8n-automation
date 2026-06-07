"""Базовые интерфейсы провайдеров."""
from __future__ import annotations

from abc import ABC, abstractmethod


class ProviderError(RuntimeError):
    """Ошибка провайдера — триггерит retry/fallback в ядре."""


class ChatProvider(ABC):
    name: str

    def __init__(self, settings=None) -> None:
        # Фабрика вызывает cls(settings) единообразно. Провайдерам вроде stub
        # settings не нужен, но общая сигнатура обязательна, иначе TypeError.
        self.settings = settings

    @abstractmethod
    async def complete_json(self, system_prompt: str, user_content: str) -> str:
        """Вернуть СЫРОЙ текст ответа модели (ожидается JSON по схеме Decision).

        Реализация просит модель отвечать строго JSON. Валидацию делает ядро.
        """
        raise NotImplementedError


class Transcriber(ABC):
    name: str

    def __init__(self, settings=None) -> None:
        self.settings = settings

    @abstractmethod
    async def transcribe(self, audio_url: str) -> str:
        """Скачать/принять аудио по URL и вернуть распознанный текст."""
        raise NotImplementedError
