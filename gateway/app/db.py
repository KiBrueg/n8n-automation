"""Логирование событий/решений в PostgreSQL (наблюдаемость ядра).

Если БД недоступна — ядро продолжает работать, лог пишется в stdout
(логирование не должно ронять обработку).
"""
from __future__ import annotations

import json
import logging

import asyncpg

from .config import Settings
from .schemas import ConversationEvent, ProcessResponse

log = logging.getLogger("hub.db")

_pool: asyncpg.Pool | None = None


async def init_pool(settings: Settings) -> None:
    global _pool
    try:
        _pool = await asyncpg.create_pool(dsn=settings.dsn, min_size=1, max_size=10)
        log.info("postgres pool готов")
    except Exception as e:  # noqa: BLE001
        log.error("postgres недоступен, логи только в stdout: %s", e)
        _pool = None


async def close_pool() -> None:
    if _pool is not None:
        await _pool.close()


def get_pool() -> asyncpg.Pool | None:
    """Доступ к пулу для других модулей (actions). None — БД недоступна."""
    return _pool


async def log_interaction(event: ConversationEvent, resp: ProcessResponse | None, error: str | None = None) -> None:
    record = {
        "event_id": event.event_id,
        "channel": event.channel.value,
        "mode": resp.mode if resp else None,
        "provider": resp.provider_used if resp else None,
        "escalate": resp.decision.escalate if resp else None,
        "latency_ms": resp.latency_ms if resp else None,
        "error": error,
    }
    if _pool is None:
        log.info("interaction %s", json.dumps(record, ensure_ascii=False))
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO interactions "
                "(event_id, channel, mode, provider, escalate, latency_ms, actions_count, intent, error) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) "
                "ON CONFLICT (event_id) DO NOTHING",
                event.event_id,
                event.channel.value,
                resp.mode if resp else None,
                resp.provider_used if resp else None,
                resp.decision.escalate if resp else None,
                resp.latency_ms if resp else None,
                len(resp.decision.actions) if resp else 0,
                resp.decision.log.intent if resp else None,
                error,
            )
    except Exception as e:  # noqa: BLE001
        log.error("не удалось записать лог в БД: %s", e)
