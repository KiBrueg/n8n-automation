"""Конфигурация ядра. Все значения берутся из окружения (.env).

Провайдеры LLM/транскрипции переключаются здесь — код роутов их не знает.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- security ---
    gateway_api_key: str = "change_me_shared_secret"
    log_level: str = "INFO"

    # --- database ---
    postgres_db: str = "hub"
    postgres_user: str = "hub"
    postgres_password: str = "hub"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    # --- LLM routing ---
    # stub — rule-based провайдер для demo без ключей (docker compose up работает сразу)
    llm_provider: Literal["stub", "ollama", "openrouter"] = "stub"
    llm_fallback_provider: str = ""  # "", "stub", "ollama" или "openrouter"
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 2
    default_trust_level: Literal["read", "draft", "prod"] = "draft"

    # --- ollama ---
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "llama3.1:8b"

    # --- openrouter ---
    openrouter_api_key: str = ""
    openrouter_model: str = "anthropic/claude-3.5-sonnet"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # --- transcription ---
    transcribe_provider: Literal["none", "whisper_local", "openai_whisper"] = "none"
    whisper_base_url: str = "http://host.docker.internal:9000"
    whisper_model: str = "base"
    openai_api_key: str = ""

    @property
    def dsn(self) -> str:
        return (
            "postgresql://"
            + f"{self.postgres_user}:{self.postgres_password}"
            + f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
