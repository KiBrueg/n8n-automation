"""Офлайн-тесты ядра: санитайзер, контракты, конвейер с фейковым провайдером."""
import json

import pytest

from app.config import Settings
from app.engine import _extract_json, process_event
from app.providers.base import ChatProvider
from app.sanitizer import restore, sanitize
from app.schemas import ConversationEvent


def test_sanitizer_masks_and_restores():
    text = "Пиши на a@b.com или +49 170 1234567, ключ sk-ABCDEF1234567890XYZ"
    res = sanitize(text)
    assert res.had_pii
    assert "a@b.com" not in res.text
    assert "[EMAIL_1]" in res.text
    assert restore(res.text, res.replacements) == text


def test_extract_json_from_noisy_output():
    raw = 'Вот ответ: {"reply_text":"ok","escalate":false,"actions":[]} спасибо'
    assert _extract_json(raw)["reply_text"] == "ok"


def test_conversation_event_defaults():
    ev = ConversationEvent.model_validate(
        {"channel": "telegram", "user": {"user_id": "u1"}, "message": {"type": "text", "text": "hi"}}
    )
    assert ev.schema_version == "conversation_event.v1"
    assert ev.event_id  # автогенерация


class _FakeProvider(ChatProvider):
    name = "fake"

    async def complete_json(self, system_prompt: str, user_content: str) -> str:
        return json.dumps(
            {
                "reply_text": "Здравствуйте! Чем помочь?",
                "escalate": False,
                "confidence": 0.9,
                "actions": [{"type": "none", "params": {}}],
                "log": {"intent": "greeting", "summary": "приветствие"},
            }
        )


@pytest.mark.asyncio
async def test_process_event_with_fake_provider(monkeypatch):
    import app.engine as engine

    monkeypatch.setattr(engine, "get_chat_provider", lambda s, name=None: _FakeProvider())
    monkeypatch.setattr(engine.actions, "execute_all", _noop)
    settings = Settings(transcribe_provider="none")
    ev = ConversationEvent.model_validate(
        {"channel": "webform", "mode_hint": "assistant", "user": {"user_id": "u1"},
         "message": {"type": "text", "text": "Привет"}}
    )
    resp = await process_event(ev, settings)
    assert resp.mode == "ASSISTANT"
    assert resp.provider_used == "fake"
    assert resp.decision.actions[0].idempotency_key  # ядро проставило ключ
    assert resp.decision.reply_text.startswith("Здравствуйте")


async def _noop(*args, **kwargs):
    return None


def test_mode_loads_and_policy_filters():
    from app.modes import load_mode

    m = load_mode("support_triage")
    assert m.mode == "SUPPORT_TRIAGE"
    assert "create_ticket" in m.allowed_actions
    permitted = m.actions_permitted_now()  # trust_level=draft
    assert "create_ticket" in permitted and "none" in permitted


@pytest.mark.asyncio
async def test_stub_provider_escalates_complaint(monkeypatch):
    import app.engine as engine
    from app.providers.stub import StubChat

    monkeypatch.setattr(engine, "get_chat_provider", lambda s, name=None: StubChat())
    monkeypatch.setattr(engine.actions, "execute_all", _noop)
    settings = Settings(llm_provider="stub", transcribe_provider="none")

    complaint = ConversationEvent.model_validate(
        {"channel": "email", "mode_hint": "support_triage", "user": {"user_id": "x"},
         "message": {"type": "text", "text": "Это ужас, верните деньги и дайте оператора"}}
    )
    resp = await process_event(complaint, settings)
    assert resp.decision.escalate is True
    # при эскалации автономных действий нет
    assert [a.type.value for a in resp.decision.actions] == ["none"]

    sales = ConversationEvent.model_validate(
        {"channel": "webform", "mode_hint": "support_triage", "user": {"user_id": "y"},
         "message": {"type": "text", "text": "Сколько стоит тариф Pro и есть ли trial?"}}
    )
    resp2 = await process_event(sales, settings)
    types = {a.type.value for a in resp2.decision.actions}
    assert types <= set(load_mode_actions()) and types  # все действия разрешены режимом


def load_mode_actions():
    from app.modes import load_mode
    return load_mode("support_triage").allowed_actions
