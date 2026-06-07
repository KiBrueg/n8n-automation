"""Санитайзер PII: вырезает чувствительные данные ДО отправки в LLM.

Возвращает очищенный текст + карту замен (на случай восстановления плейсхолдеров
в ответе). Список паттернов намеренно консервативный — лучше пере-замаскировать.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# порядок важен: более специфичные паттерны раньше общих
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("PHONE", re.compile(r"(?<!\w)\+?\d[\d\s\-().]{7,}\d(?!\w)")),
    # секреты/ключи: длинные base64-подобные токены и распространённые префиксы
    ("APIKEY", re.compile(r"\b(?:sk|pk|rk|api|key|token|bearer)[-_]?[A-Za-z0-9]{16,}\b", re.I)),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")),
]


@dataclass
class SanitizeResult:
    text: str
    replacements: dict[str, str] = field(default_factory=dict)  # placeholder -> original

    @property
    def had_pii(self) -> bool:
        return bool(self.replacements)


def sanitize(text: str | None) -> SanitizeResult:
    if not text:
        return SanitizeResult(text=text or "")

    replacements: dict[str, str] = {}
    counters: dict[str, int] = {}
    out = text

    for label, pattern in _PATTERNS:
        def _repl(m: re.Match[str], label: str = label) -> str:
            original = m.group(0)
            counters[label] = counters.get(label, 0) + 1
            placeholder = f"[{label}_{counters[label]}]"
            replacements[placeholder] = original
            return placeholder

        out = pattern.sub(_repl, out)

    return SanitizeResult(text=out, replacements=replacements)


def restore(text: str | None, replacements: dict[str, str]) -> str:
    """Вернуть оригинальные значения вместо плейсхолдеров (для ответа пользователю)."""
    if not text:
        return text or ""
    for placeholder, original in replacements.items():
        text = text.replace(placeholder, original)
    return text
