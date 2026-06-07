"""Action Executor — выполняет разрешённые действия Decision.

Сейчас реализованы «безопасные» приёмники: тикеты/черновики/напоминания
пишутся в PostgreSQL (через пул из db.py). Внешние эффекты (реальная отправка
почты, CRM) намеренно оставлены как draft/запись — это соответствует trust_level
'draft' и принципу прогрессивного доверия.

Идемпотентность: запись по уникальному idempotency_key, повтор не дублирует.
Best-effort: ошибка одного действия логируется и не роняет обработку события.
"""
from __future__ import annotations

import json
import logging

from . import db
from .schemas import Action, ConversationEvent, Decision

log = logging.getLogger("hub.actions")


async def _persist(table: str, idem: str, user_id: str, payload: dict) -> None:
    pool = db.get_pool()
    if pool is None:
        log.info("[no-db] %s %s %s", table, idem, json.dumps(payload, ensure_ascii=False))
        return
    async with pool.acquire() as conn:
        await conn.execute(
            f"""
            INSERT INTO {table} (idempotency_key, user_id, payload)
            VALUES ($1, $2, $3::jsonb)
            ON CONFLICT (idempotency_key) DO NOTHING
            """,
            idem,
            user_id,
            json.dumps(payload, ensure_ascii=False),
        )


# реестр обработчиков: type -> (table)
_TABLES = {
    "create_ticket": "tickets",
    "send_email": "drafts",
    "set_reminder": "reminders",
    "save_record": "records",
    "upsert_note": "notes",
}


async def execute_one(event: ConversationEvent, action: Action) -> None:
    t = action.type.value
    if t == "none":
        return
    table = _TABLES.get(t)
    if table is None:
        log.info("действие '%s' без приёмника — пропуск (ещё не реализовано)", t)
        return
    try:
        await _persist(table, action.idempotency_key or f"{event.event_id}:{t}",
                       event.user.user_id, action.params)
    except Exception as e:  # noqa: BLE001 — best-effort
        log.error("действие '%s' не выполнено: %s", t, e)


async def execute_all(event: ConversationEvent, decision: Decision) -> None:
    for action in decision.actions:
        await execute_one(event, action)
