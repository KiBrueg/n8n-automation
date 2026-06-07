"""Ядро обработки события: единый конвейер для всех будущих режимов.

Поток: voice→транскрипция → санитайзер PII → LLM(JSON) → валидация Decision
       → retry → fallback-провайдер → проставить idempotency_key → восстановить PII.

Режимы (support/sales/...) сюда НЕ зашиты — они приходят как system_prompt + mode.
"""
from __future__ import annotations

import json
import logging
import time
from uuid import uuid4

from pydantic import ValidationError

from . import actions
from .config import Settings
from .modes import ModeConfig, load_mode
from .providers import ProviderError, get_chat_provider, get_transcriber
from .sanitizer import restore, sanitize
from .schemas import Action, ActionType, ConversationEvent, Decision, ProcessResponse

log = logging.getLogger("hub.engine")

# Базовый системный промпт ядра. Конкретный режим добавляет свои инструкции поверх.
_BASE_SYSTEM = (
    "Ты — ядро AI Automation Hub. Канал: '{channel}', режим: '{mode}'.\n"
    "Верни ОДИН JSON-объект строго по схеме Decision:\n"
    '{{"schema_version":"decision.v1","reply_text":str|null,"escalate":bool,'
    '"confidence":0..1,"actions":[{{"type":"<action>","params":{{}}}}],'
    '"log":{{"intent":str,"summary":str}}}}\n'
    "Разрешённые типы действий в этом режиме: {allowed}. Другие использовать нельзя.\n"
    "Эскалируй (escalate=true) при: {escalate_when}.\n"
)


def _build_system(mode: ModeConfig, channel: str) -> str:
    parts = [
        _BASE_SYSTEM.format(
            channel=channel,
            mode=mode.mode,
            allowed=", ".join(mode.allowed_actions),
            escalate_when="; ".join(mode.escalate_when) or "сомнении",
        )
    ]
    if mode.prompt:
        parts.append("\n--- Инструкции режима ---\n" + mode.prompt)
    return "".join(parts)


def _enforce_policy(decision: Decision, mode: ModeConfig) -> Decision:
    """Отфильтровать действия по allowed + trust_level. Дисквалификация → эскалация."""
    permitted = mode.actions_permitted_now()
    kept: list[Action] = []
    dropped = False
    for a in decision.actions:
        if a.type.value in permitted:
            kept.append(a)
        else:
            dropped = True
            log.info("действие '%s' не разрешено в режиме %s — отброшено", a.type.value, mode.mode)
    if dropped:
        decision.escalate = True  # модель предложила запрещённое → перестраховка
    decision.actions = kept or [Action(type=ActionType.none)]
    return decision


def _extract_json(raw: str) -> dict:
    """Достать JSON из ответа модели (на случай обрамления текстом)."""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(raw[start : end + 1])
        raise


def _resolve_mode(event: ConversationEvent) -> str:
    return (event.mode_hint or "ASSISTANT").upper()


async def _maybe_transcribe(event: ConversationEvent, settings: Settings) -> tuple[str, bool]:
    """Вернуть текст для LLM и флаг, была ли транскрипция."""
    msg = event.message
    if msg.type.value == "voice":
        transcriber = get_transcriber(settings)
        if transcriber is None:
            raise ProviderError("пришёл voice, но TRANSCRIBE_PROVIDER=none")
        audio = next((a for a in msg.attachments if a.kind == "audio"), None)
        if audio is None:
            raise ProviderError("voice-событие без audio-вложения")
        return await transcriber.transcribe(audio.url), True
    return msg.text or "", False


async def _call_with_retry(provider, system: str, content: str, settings: Settings) -> Decision:
    """Вызвать провайдера, провалидировать Decision, повторить при ошибке."""
    last_err: Exception | None = None
    for attempt in range(settings.llm_max_retries + 1):
        try:
            raw = await provider.complete_json(system, content)
            return Decision.model_validate(_extract_json(raw))
        except (ValidationError, json.JSONDecodeError) as e:
            last_err = e
            log.warning("provider=%s невалидный JSON (попытка %s): %s", provider.name, attempt, e)
            content += "\n\nОТВЕТ БЫЛ НЕВАЛИДЕН. Верни ТОЛЬКО корректный JSON по схеме Decision."
        except ProviderError as e:
            last_err = e
            log.warning("provider=%s ошибка (попытка %s): %s", provider.name, attempt, e)
    raise ProviderError(f"{provider.name}: исчерпаны попытки: {last_err}")


async def process_event(event: ConversationEvent, settings: Settings) -> ProcessResponse:
    t0 = time.perf_counter()
    mode = load_mode(_resolve_mode(event))

    # 1. голос → текст
    text, transcribed = await _maybe_transcribe(event, settings)

    # 2. вырезать PII перед LLM
    clean = sanitize(text)

    # 3. системный промпт = ядро + промпт режима + разрешённые действия
    system = _build_system(mode, event.channel.value)
    user_content = clean.text

    # 4. основной провайдер → fallback
    provider = get_chat_provider(settings)
    provider_used = provider.name
    try:
        decision = await _call_with_retry(provider, system, user_content, settings)
    except ProviderError:
        if not settings.llm_fallback_provider:
            raise
        fb = get_chat_provider(settings, settings.llm_fallback_provider)
        provider_used = fb.name
        log.info("fallback → %s", fb.name)
        decision = await _call_with_retry(fb, system, user_content, settings)

    # 5. политика режима: отфильтровать действия по allowed + trust_level
    decision = _enforce_policy(decision, mode)

    # 6. восстановить PII в ответе пользователю + гарантировать idempotency_key
    if decision.reply_text:
        decision.reply_text = restore(decision.reply_text, clean.replacements)
    for action in decision.actions:
        if not action.idempotency_key:
            action.idempotency_key = f"{event.event_id}:{action.type.value}:{uuid4().hex[:8]}"

    # 7. выполнить разрешённые действия (best-effort, идемпотентно)
    await actions.execute_all(event, decision)

    return ProcessResponse(
        event_id=event.event_id,
        mode=mode.mode,
        provider_used=provider_used,
        transcribed=transcribed,
        decision=decision,
        latency_ms=int((time.perf_counter() - t0) * 1000),
    )
