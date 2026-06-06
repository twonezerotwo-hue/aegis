"""Signal-only consensus scoring for AEGIS Core.

Source behavior references:
- consensus_engine/src/signal_aggregator.py
- consensus_engine/src/meta_scorer.py
- modules/news-ai-limited/src/signal_models.py
"""

from __future__ import annotations

from typing import Any, Optional

from .regime_weights import get_weights_for_regime

CANONICAL_MODULES = ("touche", "fundamental", "news", "sentinel", "quantum")
MIN_MODULES_REQUIRED = 3

MODULE_ALIASES = {
    "touche": "touche",
    "technical": "touche",
    "fundamental": "fundamental",
    "news": "news",
    "sentiment": "news",
    "sentinel": "sentinel",
    "macro": "sentinel",
    "quantum": "quantum",
    "quant": "quantum",
}


def _canonical_module_name(raw_key: str) -> str:
    return MODULE_ALIASES.get(str(raw_key).strip().lower(), str(raw_key).strip().lower())


def _extract_score_payload(raw_score: Any) -> tuple[Any, str | None]:
    if not isinstance(raw_score, dict):
        return raw_score, None

    value = None
    for value_key in ("value", "score", "raw_score"):
        if value_key in raw_score:
            value = raw_score[value_key]
            break

    score_range = (
        raw_score.get("range")
        or raw_score.get("scale")
        or raw_score.get("score_range")
    )
    return value, str(score_range).strip().lower() if score_range else None


def _normalize_signed_range(value: float, lower: float, upper: float) -> float:
    if lower >= upper:
        raise ValueError("Invalid signed score range.")
    if value < lower or value > upper:
        raise ValueError(f"Score {value} outside declared range {lower}..{upper}.")
    return ((value - lower) / (upper - lower)) * 100.0


def _normalize_score_value(raw_score: Any, module_name: str) -> tuple[float, str]:
    raw_value, declared_range = _extract_score_payload(raw_score)
    value = float(raw_value)
    range_name = declared_range

    if range_name in {"0..1", "0-1", "fraction", "probability"}:
        if value < 0.0 or value > 1.0:
            raise ValueError(f"Score {value} outside declared range 0..1.")
        value *= 100.0
        return max(0.0, min(100.0, value)), "0..1"

    if range_name in {"0..100", "0-100", "percent", "percentage"}:
        if value < 0.0 or value > 100.0:
            raise ValueError(f"Score {value} outside declared range 0..100.")
        return max(0.0, min(100.0, value)), "0..100"

    if range_name in {"-1..1", "-1-1", "signed_1", "signed"}:
        return _normalize_signed_range(value, -1.0, 1.0), "-1..1"

    if range_name in {"-1.5..1.5", "-1.5-1.5", "signed_1_5", "conviction"}:
        return _normalize_signed_range(value, -1.5, 1.5), "-1.5..1.5"

    if range_name:
        raise ValueError(f"Unsupported score range '{range_name}'.")

    if module_name == "quantum" and -1.5 <= value <= 1.5:
        return _normalize_signed_range(value, -1.5, 1.5), "-1.5..1.5"

    if 0.0 <= value <= 1.0:
        return value * 100.0, "0..1"

    if 0.0 <= value <= 100.0:
        return value, "0..100"

    raise ValueError(
        f"Score {value} is outside supported ranges. Provide an explicit range."
    )


def _normalize_module_scores_with_warnings(
    module_scores: dict,
) -> tuple[dict[str, float], dict[str, str], list[str]]:
    normalized: dict[str, float] = {}
    ranges_used: dict[str, str] = {}
    warnings: list[str] = []

    if not isinstance(module_scores, dict):
        return {}, {}, ["Module scores payload was not a dictionary."]

    for raw_key, raw_value in module_scores.items():
        canonical_key = _canonical_module_name(raw_key)
        if canonical_key not in CANONICAL_MODULES:
            warnings.append(f"Unknown module '{raw_key}' was ignored.")
            continue

        try:
            score_value, score_range = _normalize_score_value(raw_value, canonical_key)
            normalized[canonical_key] = round(score_value, 4)
            ranges_used[canonical_key] = score_range
        except (TypeError, ValueError) as exc:
            warnings.append(f"Module '{raw_key}' had an invalid score and was ignored: {exc}")

    return normalized, ranges_used, warnings


def normalize_module_scores(module_scores: dict) -> dict:
    """Normalize module scores to a 0-100 scale using canonical module names."""
    normalized, _, _ = _normalize_module_scores_with_warnings(module_scores)
    return normalized


def _coerce_weight_map(weights: dict) -> tuple[dict[str, float], list[str]]:
    warnings: list[str] = []
    if isinstance(weights, dict) and "weights" in weights and isinstance(weights["weights"], dict):
        raw_weights = weights["weights"]
    else:
        raw_weights = weights or {}

    normalized_weights: dict[str, float] = {}
    for key, value in raw_weights.items():
        canonical_key = _canonical_module_name(key)
        if canonical_key not in CANONICAL_MODULES:
            warnings.append(f"Unknown weight key '{key}' was ignored.")
            continue
        normalized_weights[canonical_key] = float(value)

    total = sum(normalized_weights.values())
    if total <= 0:
        raise ValueError("A positive set of module weights is required.")

    if abs(total - 1.0) > 1e-9:
        warnings.append(f"Module weights summed to {total:.6f}; normalized to 1.0.")

    normalized_weights = {
        key: round(value / total, 6) for key, value in normalized_weights.items()
    }
    return normalized_weights, warnings


def calculate_consensus_score(module_scores: dict, weights: dict) -> dict:
    """Calculate a weighted, signal-only consensus score."""
    normalized_scores, score_ranges, score_warnings = _normalize_module_scores_with_warnings(module_scores)
    normalized_weights, weight_warnings = _coerce_weight_map(weights)
    warnings = score_warnings + weight_warnings

    contributions: dict[str, dict] = {}
    missing_modules = [
        module_name
        for module_name in CANONICAL_MODULES
        if normalized_weights.get(module_name, 0.0) > 0 and module_name not in normalized_scores
    ]
    provided_modules = [
        module_name
        for module_name in CANONICAL_MODULES
        if normalized_weights.get(module_name, 0.0) > 0 and module_name in normalized_scores
    ]

    for module_name in missing_modules:
        warnings.append(
            f"Missing module score for '{module_name}'; excluded from consensus and weight redistribution."
        )

    provided_weight_total = sum(normalized_weights[module_name] for module_name in provided_modules)
    consensus_available = (
        len(provided_modules) >= MIN_MODULES_REQUIRED and provided_weight_total > 0.0
    )
    consensus_score: float | None = 0.0 if consensus_available else None
    effective_weights: dict[str, float] = {}

    if not consensus_available:
        warnings.append(
            f"Only {len(provided_modules)} valid positive-weight module scores were provided; "
            f"at least {MIN_MODULES_REQUIRED} are required."
        )
    else:
        effective_weights = {
            module_name: round(normalized_weights[module_name] / provided_weight_total, 6)
            for module_name in provided_modules
        }

    for module_name in CANONICAL_MODULES:
        original_weight = normalized_weights.get(module_name, 0.0)
        if module_name in normalized_scores:
            score_value = normalized_scores[module_name]
            source = "provided"
            effective_weight = effective_weights.get(module_name, 0.0)
        else:
            score_value = None
            source = "missing_excluded"
            effective_weight = 0.0

        weighted_score = (
            round(float(score_value) * effective_weight, 4)
            if consensus_available and score_value is not None
            else None
        )
        if consensus_available and weighted_score is not None and consensus_score is not None:
            consensus_score += weighted_score
        contributions[module_name] = {
            "score": round(float(score_value), 4) if score_value is not None else None,
            "score_range": score_ranges.get(module_name),
            "original_weight": round(original_weight, 6),
            "weight": round(effective_weight, 6),
            "weighted_score": weighted_score,
            "source": source,
        }

    return {
        "normalized_scores": normalized_scores,
        "score_ranges_used": score_ranges,
        "weights_used": effective_weights if consensus_available else {},
        "configured_weights": normalized_weights,
        "consensus_score": round(consensus_score, 4) if consensus_score is not None else None,
        "consensus_status": "AVAILABLE" if consensus_available else "INSUFFICIENT_DATA",
        "consensus_available": consensus_available,
        "min_modules_required": MIN_MODULES_REQUIRED,
        "provided_modules": provided_modules,
        "missing_modules": missing_modules,
        "contributions": contributions,
        "warnings": warnings,
    }


def build_aegis_signal(
    symbol: str,
    timeframe: str,
    module_scores: dict,
    raw_regime: str,
    confluence: Optional[dict] = None,
) -> dict:
    """Build the signal-only AEGIS Core output contract."""
    warnings: list[str] = []

    regime_result = get_weights_for_regime(raw_regime)
    warnings.extend(regime_result["warnings"])

    consensus_result = calculate_consensus_score(module_scores, regime_result["weights"])
    warnings.extend(consensus_result["warnings"])

    signal: dict = {
        "source_engine": "AEGIS",
        "source_version": "7.2_core",
        "symbol": symbol,
        "timeframe": timeframe,
        "module_scores": consensus_result["normalized_scores"],
        "consensus_score": consensus_result["consensus_score"],
        "consensus_status": consensus_result["consensus_status"],
        "consensus_available": consensus_result["consensus_available"],
        "min_modules_required": consensus_result["min_modules_required"],
        "provided_modules": consensus_result["provided_modules"],
        "missing_modules": consensus_result["missing_modules"],
        "raw_regime": raw_regime,
        "weight_key": regime_result["weight_key"],
        "weights_used": consensus_result["weights_used"],
        "configured_weights": consensus_result["configured_weights"],
        "contributions": consensus_result["contributions"],
        "source_config": regime_result["source_config"],
        "decision_permission": "SIGNAL_ONLY_NOT_FINAL",
        "final_decision": False,
        "warnings": warnings,
    }

    if isinstance(confluence, dict):
        signal["confluence"] = confluence
    elif confluence is not None:
        signal["warnings"].append("Confluence payload was not a dictionary and was ignored.")

    return signal
