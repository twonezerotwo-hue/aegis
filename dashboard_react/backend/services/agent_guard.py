"""Safety metadata guard for AEGIS agent API responses.

This mirrors the useful e-yay pattern: every agent response is explicitly
marked as signal-only and human-authority. It does not change runtime behavior.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

CANONICAL_DECISION_PERMISSION = "SIGNAL_ONLY_NOT_FINAL"
SAFETY_MODE = "SIGNAL_ONLY / NO_EXECUTION"

_FORBIDDEN_TEXT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(execute|place)\s+(this\s+)?(trade|order|buy|sell)\b", "EN_EXECUTION_VERB"),
    (r"\bopen\s+(a\s+)?(long|short)\s+position\b", "EN_OPEN_POSITION"),
    (r"\bclose\s+(your|the)\s+position\s+now\b", "EN_CLOSE_POSITION"),
    (r"\b(al|sat)\s+emri\s+(ver|gönder|aç)\b", "TR_ORDER_VERB"),
    (r"\bpozisyon\s+(aç|kapat)\s+(şimdi|hemen)\b", "TR_POSITION_NOW"),
)


def _scan_text(value: str) -> list[str]:
    hits: list[str] = []
    for pattern, label in _FORBIDDEN_TEXT_PATTERNS:
        if re.search(pattern, value, flags=re.IGNORECASE):
            hits.append(label)
    return hits


def _collect_text_hits(payload: Any) -> list[str]:
    hits: list[str] = []
    if isinstance(payload, str):
        hits.extend(_scan_text(payload))
    elif isinstance(payload, dict):
        for value in payload.values():
            hits.extend(_collect_text_hits(value))
    elif isinstance(payload, list):
        for value in payload:
            hits.extend(_collect_text_hits(value))
    return list(dict.fromkeys(hits))


def guard_agent_response(payload: dict[str, Any], *, source: str) -> dict[str, Any]:
    """Attach non-final decision metadata to an agent response."""
    if not isinstance(payload, dict):
        payload = {"payload": payload}

    if payload.get("final_decision") is True:
        logger.warning("agent_guard final_decision blocked: source=%s", source)

    warnings = _collect_text_hits(payload)
    payload["decision_permission"] = CANONICAL_DECISION_PERMISSION
    payload["final_decision"] = False
    payload["execution_authority"] = "human"
    payload["safety_mode"] = SAFETY_MODE
    if warnings:
        payload.setdefault("guard_warnings", []).extend(warnings)
    return payload


__all__ = [
    "CANONICAL_DECISION_PERMISSION",
    "SAFETY_MODE",
    "guard_agent_response",
]
