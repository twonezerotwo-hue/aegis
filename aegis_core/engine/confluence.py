"""Multi-timeframe confluence helpers for signal-only AEGIS Core.

Inspired by:
- consensus_engine/src/multi_tf_validator.py
- strategies/touche_ai/src/engine/multi_timeframe_analyzer.py
"""

from __future__ import annotations


def _normalize_score(score: float) -> float:
    value = float(score)
    if 0.0 <= value <= 1.0:
        value *= 100.0
    return max(0.0, min(100.0, value))


def _direction(score: float) -> str:
    if score > 50.0:
        return "bullish"
    if score < 50.0:
        return "bearish"
    return "neutral"


def apply_multi_tf_confluence(base_score: float, higher_tf_scores: dict[str, float]) -> dict:
    """Adjust a base score with simple higher-timeframe confluence logic.

    Rules:
    - all non-neutral higher timeframes aligned with the base direction -> 1.15
    - all non-neutral higher timeframes opposing the base direction -> 0.70
    - anything mixed or neutral -> 1.00
    """

    warnings: list[str] = []
    normalized_base = _normalize_score(base_score)
    base_direction = _direction(normalized_base)

    normalized_higher: dict[str, float] = {}
    for timeframe, score in (higher_tf_scores or {}).items():
        try:
            normalized_higher[timeframe] = _normalize_score(score)
        except (TypeError, ValueError):
            warnings.append(
                f"Higher timeframe '{timeframe}' had a non-numeric score and was ignored."
            )

    if base_direction == "neutral":
        status = "neutral"
        multiplier = 1.00
        warnings.append("Base score is neutral; confluence multiplier left unchanged.")
    elif not normalized_higher:
        status = "neutral"
        multiplier = 1.00
        warnings.append("No valid higher timeframe scores were provided.")
    else:
        aligned = 0
        opposing = 0
        neutral = 0

        for score in normalized_higher.values():
            tf_direction = _direction(score)
            if tf_direction == "neutral":
                neutral += 1
            elif tf_direction == base_direction:
                aligned += 1
            else:
                opposing += 1

        if aligned > 0 and opposing == 0 and neutral == 0:
            status = "aligned"
            multiplier = 1.15
        elif opposing > 0 and aligned == 0 and neutral == 0:
            status = "opposing"
            multiplier = 0.70
        else:
            status = "mixed"
            multiplier = 1.00

    multiplier = max(0.3, min(1.5, float(multiplier)))
    adjusted_score = round(max(0.0, min(100.0, normalized_base * multiplier)), 4)

    return {
        "original_score": round(normalized_base, 4),
        "adjusted_score": adjusted_score,
        "multiplier": round(multiplier, 4),
        "status": status,
        "warnings": warnings,
    }
