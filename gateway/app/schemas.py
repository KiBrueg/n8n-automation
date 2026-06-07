"""Контракты данных ядра — единственная точка, к которой цепляются дополнения.

ConversationEvent — нормализованный вход из любого канала.
Decision         — строгий выход LLM (reply_text + actions[] + escalate).

Менять эти схемы = менять контракт для ВСЕХ режимов, поэтому версионируем (v1).
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- #
#  Вход: ConversationEvent
# --------------------------------------------------------------------------- #
class Channel(StrEnum):
    telegram = "telegram"
    email = "email"
    twitch = "twitch"
    youtube = "youtube"
    voip = "voip"
    webform = "webform"


class MessageType(StrEnum):
    text = "text"
    voice = "voice"
    file = "file"
    event = "event"


class Attachment(BaseModel):
    kind: Literal["pdf", "image", "audio", "other"] = "other"
    url: str
    mime: str | None = None


class EventUser(BaseModel):
    user_id: str
    display_name: str | None = None
    locale: str | None = None


class EventMessage(BaseModel):
    type: MessageType = MessageType.text
    text: str | None = None
    attachments: list[Attachment] = Field(default_factory=list)


class ConversationEvent(BaseModel):
    """v1 — единый формат входящего события."""

    schema_version: Literal["conversation_event.v1"] = "conversation_event.v1"
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    received_at: datetime = Field(default_factory=_now)
    channel: Channel
    mode_hint: str | None = None  # подсказка режима (по endpoint/каналу), может быть None
    user: EventUser
    message: EventMessage
    metadata: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
#  Выход: Decision
# --------------------------------------------------------------------------- #
class ActionType(StrEnum):
    create_ticket = "create_ticket"
    update_lead_stage = "update_lead_stage"
    save_record = "save_record"
    send_email = "send_email"
    upsert_note = "upsert_note"
    create_clip = "create_clip"
    set_reminder = "set_reminder"
    none = "none"


class Action(BaseModel):
    type: ActionType
    params: dict[str, Any] = Field(default_factory=dict)
    # ядро проставляет ключ идемпотентности, если LLM не дал — защита от дублей
    idempotency_key: str | None = None


class DecisionLog(BaseModel):
    intent: str | None = None
    summary: str | None = None


class Decision(BaseModel):
    """v1 — то, что обязан вернуть LLM (валидируется; невалидное → retry)."""

    schema_version: Literal["decision.v1"] = "decision.v1"
    reply_text: str | None = None
    escalate: bool = False
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    actions: list[Action] = Field(default_factory=list)
    log: DecisionLog = Field(default_factory=DecisionLog)


# --------------------------------------------------------------------------- #
#  Ответ ядра вызывающей стороне (n8n)
# --------------------------------------------------------------------------- #
class ProcessResponse(BaseModel):
    event_id: str
    mode: str
    provider_used: str
    transcribed: bool = False
    decision: Decision
    latency_ms: int
