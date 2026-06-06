"""Multi-timeframe confluence helpers for signal-only AEGIS Core.

Inspired by:
- consensus_engine/src/multi_tf_validator.py
- strategies/touche_ai/src/engine/multi_timeframe_analyzer.py
"""

from __future__ import annotations


def _extract_score_payload(score) -> tuple[object, str | None]:
    if not isinstance(score, dict):
        return score, None

    value = None
    for value_key in ("value", "score", "raw_score"):
        if value_key in score:
            value = score[value_key]
            break

    score_range = score.get("range") or score.get("scale") or score.get("score_range")
    return value, str(score_range).strip().lower() if score_range else None


def _normalize_signed_range(value: float, lower: float, upper: float) -> float:
    if lower >= upper:
        raise ValueError("Invalid signed score range.")
    if value < lower or value > upper:
        raise ValueError(f"Score {value} outside declared range {lower}..{upper}.")
    return ((value - lower) / (upper - lower)) * 100.0


def _normalize_score(score: float) -> float:
    raw_value, declared_range = _extract_score_payload(score)
    value = float(raw_value)
    range_name = declared_range

    if range_name in {"0..1", "0-1", "fraction", "probability"}:
        if value < 0.0 or value > 1.0:
            raise ValueError(f"Score {value} outside declared range 0..1.")
        value *= 100.0
        return max(0.0, min(100.0, value))

    if range_name in {"0..100", "0-100", "percent", "percentage"}:
        if value < 0.0 or value > 100.0:
            raise ValueError(f"Score {value} outside declared range 0..100.")
        return max(0.0, min(100.0, value))

    if range_name in {"-1..1", "-1-1", "signed_1", "signed"}:
        return _normalize_signed_range(value, -1.0, 1.0)

    if range_name in {"-1.5..1.5", "-1.5-1.5", "signed_1_5", "conviction"}:
        return _normalize_signed_range(value, -1.5, 1.5)

    if range_name:
        raise ValueError(f"Unsupported score range '{range_name}'.")

    if 0.0 <= value <= 1.0:
        return value * 100.0

    if 0.0 <= value <= 100.0:
        return value

    raise ValueError(
        f"Score {value} is outside supported ranges. Provide an explicit range."
    )


def _direction(score: float) -> str:
    if score > 55.0:
        return "bullish"
    if score < 45.0:
        return "bearish"
    return "neutral"


def apply_multi_tf_confluence(
    base_score: float,
    higher_tf_scores: dict[str, float],
    aligned_multiplier: float = 1.20,
    opposing_multiplier: float = 0.80,
) -> dict:
    """Adjust a base score with simple higher-timeframe confluence logic.

    Rules:
    - neutral band is 45-55 and does not vote
    - all voting higher timeframes aligned with the base direction -> aligned_multiplier
    - all voting higher timeframes opposing the base direction -> opposing_multiplier
    - mixed voting directions or no voting higher timeframes -> 1.00
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
        status = "skipped"
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

        if aligned > 0 and opposing == 0:
            status = "aligned"
            multiplier = aligned_multiplier
        elif opposing > 0 and aligned == 0:
            status = "opposing"
            multiplier = opposing_multiplier
        elif aligned == 0 and opposing == 0 and neutral > 0:
            status = "neutral"
            multiplier = 1.00
            warnings.append("Higher timeframe scores were neutral; no confluence vote applied.")
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
