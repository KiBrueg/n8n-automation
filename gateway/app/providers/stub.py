"""Stub chat-провайдер для demo без внешних ключей.

Простая rule-based классификация support_triage по ключевым словам.
Назначение: `docker compose up` показывает живой флоу сразу, без LLM-кредов.
В проде заменяется на ollama/openrouter одной переменной LLM_PROVIDER.
"""
from __future__ import annotations

import json

from .base import ChatProvider

_NEGATIVE = ("не работает", "ужас", "верните деньги", "отказ", "жалоба", "broken", "refund", "angry")
_HUMAN = ("оператор", "человек", "менеджер", "human", "agent")
_SALES = ("цена", "купить", "тариф", "стоимость", "demo", "trial", "price", "buy")
_BILLING = ("счёт", "оплата", "invoice", "billing", "платёж", "payment")


class StubChat(ChatProvider):
    name = "stub"

    async def complete_json(self, system_prompt: str, user_content: str) -> str:
        text = (user_content or "").lower()
        escalate = any(k in text for k in _NEGATIVE) or any(k in text for k in _HUMAN)

        if any(k in text for k in _BILLING):
            category, intent = "billing", "billing"
        elif any(k in text for k in _SALES):
            category, intent = "sales", "sales"
        elif escalate:
            category, intent = "support", "complaint"
        else:
            category, intent = "support", "general"

        if escalate:
            actions = [{"type": "none", "params": {}}]
            reply = "Спасибо за обращение. Передаю вопрос специалисту, он скоро свяжется с вами."
        elif category == "sales":
            actions = [
                {"type": "set_reminder", "params": {"when": "+1d", "text": "Follow-up по лиду"}},
                {"type": "send_email", "params": {"to": "lead", "subject": "Ваш запрос",
                                                   "body": "Спасибо за интерес! Вот детали…", "as_draft": True}},
            ]
            reply = "Спасибо за интерес! Подготовил для вас информацию, отправлю детали на почту."
        else:
            actions = [{"type": "create_ticket", "params": {
                "title": "Обращение клиента", "category": category, "priority": "normal",
                "body": user_content[:500]}}]
            reply = "Спасибо за обращение! Зарегистрировал заявку, разберёмся и ответим."

        return json.dumps({
            "schema_version": "decision.v1",
            "reply_text": reply,
            "escalate": escalate,
            "confidence": 0.55 if escalate else 0.8,
            "actions": actions,
            "log": {"intent": intent, "summary": user_content[:120]},
        }, ensure_ascii=False)
