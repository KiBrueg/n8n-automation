"""FastAPI gateway — точка входа ядра AI Automation Hub.

Эндпоинты:
  GET  /health          — liveness (без авторизации, для healthcheck)
  POST /v1/process      — основной: ConversationEvent → Decision
  GET  /v1/config       — какие провайдеры активны (для диагностики, под ключом)

Авторизация: заголовок X-API-Key == GATEWAY_API_KEY.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, status

from . import __version__, db
from .config import Settings, get_settings
from .engine import process_event
from .providers import ProviderError
from .schemas import ConversationEvent, ProcessResponse

logging.basicConfig(level=get_settings().log_level)
log = logging.getLogger("hub")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_pool(get_settings())
    yield
    await db.close_pool()


app = FastAPI(title="AI Automation Hub — Core Gateway", version=__version__, lifespan=lifespan)


async def require_api_key(
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if x_api_key != settings.gateway_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing X-API-Key")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/v1/config", dependencies=[Depends(require_api_key)])
async def show_config(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "llm_provider": settings.llm_provider,
        "llm_fallback_provider": settings.llm_fallback_provider or None,
        "transcribe_provider": settings.transcribe_provider,
        "default_trust_level": settings.default_trust_level,
    }


@app.post("/v1/process", response_model=ProcessResponse, dependencies=[Depends(require_api_key)])
async def process(
    event: ConversationEvent,
    settings: Settings = Depends(get_settings),
) -> ProcessResponse:
    try:
        resp = await process_event(event, settings)
    except ProviderError as e:
        await db.log_interaction(event, None, error=str(e))  # type: ignore[arg-type]
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"provider error: {e}") from e
    except Exception as e:  # noqa: BLE001
        await db.log_interaction(event, None, error=str(e))  # type: ignore[arg-type]
        log.exception("необработанная ошибка")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal error") from e

    await db.log_interaction(event, resp)
    return resp
