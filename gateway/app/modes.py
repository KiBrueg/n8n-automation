"""Mode-система: загрузка конфигов режимов и их промптов.

Режим = JSON-конфиг (modes/<name>.json) + промпт (prompts/<file>.md).
Ядро не знает деталей режима — оно получает ModeConfig и применяет его одинаково.
Добавить режим = добавить два файла, код не трогаем.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

log = logging.getLogger("hub.modes")

_ROOT = Path(__file__).resolve().parents[2]
MODES_DIR = Path(os.getenv("MODES_DIR", _ROOT / "modes"))
PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR", _ROOT / "prompts"))

_READONLY_ACTIONS = {"none"}
# действия с необратимым внешним эффектом — только на trust_level=prod
_PROD_ONLY_ACTIONS = {"update_lead_stage", "create_clip"}


@dataclass(frozen=True)
class ModeConfig:
    mode: str
    tone: str = ""
    prompt: str = ""
    allowed_actions: tuple[str, ...] = ("none",)
    trust_level: str = "draft"
    escalate_when: tuple[str, ...] = field(default_factory=tuple)

    def actions_permitted_now(self) -> set[str]:
        """Какие действия реально можно выполнять при текущем trust_level."""
        allowed = set(self.allowed_actions)
        if self.trust_level == "read":
            return allowed & _READONLY_ACTIONS or {"none"}
        if self.trust_level == "draft":
            return (allowed - _PROD_ONLY_ACTIONS) or {"none"}
        return allowed


_FALLBACK = ModeConfig(mode="GENERIC", allowed_actions=("none",), trust_level="read")


@lru_cache
def load_mode(name: str) -> ModeConfig:
    key = (name or "GENERIC").lower()
    path = MODES_DIR / (key + ".json")
    if not path.exists():
        log.warning("режим '%s' не найден (%s), использую GENERIC", name, path)
        return _FALLBACK
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
        prompt_file = cfg.get("prompt_file")
        prompt = ""
        if prompt_file:
            p = PROMPTS_DIR / prompt_file
            prompt = p.read_text(encoding="utf-8") if p.exists() else ""
        return ModeConfig(
            mode=cfg.get("mode", name).upper(),
            tone=cfg.get("tone", ""),
            prompt=prompt,
            allowed_actions=tuple(cfg.get("allowed_actions", ["none"])),
            trust_level=cfg.get("trust_level", "draft"),
            escalate_when=tuple(cfg.get("escalate_when", [])),
        )
    except (json.JSONDecodeError, OSError) as e:
        log.error("ошибка загрузки режима '%s': %s — использую GENERIC", name, e)
        return _FALLBACK
