"""Lightweight Data Integrity Gate for AEGIS Core.

This module provides a non-final validation layer intended for E-yAy /
BrainChain integration. It never emits trade intent and only reports whether
signal generation may proceed safely.
"""

from __future__ import annotations

from typing import Any


def _clamp_score(value: float) -> int:
    return max(0, min(100, int(round(float(value)))))


def validate_data_integrity(payload: dict | None) -> dict:
    """Validate optional data integrity metadata for signal generation."""
    warnings: list[str] = []
    status = "PASS"
    hard_block = False
    score = 100.0

    if not isinstance(payload, dict) or not payload:
        return {
            "status": "DEGRADED_PASS",
            "data_quality_score": 70,
            "hard_block": False,
            "warnings": ["data_integrity_missing"],
            "decision_permission": "DATA_GATE_ONLY_NOT_FINAL",
        }

    source = str(payload.get("source", "")).strip()
    if not source:
        warnings.append("source_missing")
        status = "FAIL"
        hard_block = True

    available_timestamp = str(payload.get("available_timestamp", "")).strip()
    if not available_timestamp:
        warnings.append("available_timestamp_missing")
        status = "FAIL"
        hard_block = True

    if payload.get("critical_fields_present") is False:
        warnings.append("critical_fields_missing")
        status = "FAIL"
        hard_block = True

    raw_confidence = payload.get("data_confidence")
    if raw_confidence is None:
        warnings.append("data_confidence_missing")
        score -= 20
        if status == "PASS":
            status = "DEGRADED_PASS"
    else:
        try:
            confidence = float(raw_confidence)
        except (TypeError, ValueError):
            confidence = 0.0

        if confidence < 0.50:
            warnings.append("low_data_confidence")
            status = "FAIL"
            hard_block = True
            score = min(score, max(confidence, 0.0) * 100.0)
        else:
            score = min(score, confidence * 100.0)

    if bool(payload.get("is_stale")):
        warnings.append("data_is_stale")
        score -= 20
        if status == "PASS":
            status = "DEGRADED_PASS"

    if bool(payload.get("fallback_used")):
        warnings.append("fallback_used")
        score -= 15
        if status == "PASS":
            status = "DEGRADED_PASS"

    if hard_block:
        score = min(score, 49.0)

    return {
        "status": status,
        "data_quality_score": _clamp_score(score),
        "hard_block": hard_block,
        "warnings": warnings,
        "decision_permission": "DATA_GATE_ONLY_NOT_FINAL",
    }
