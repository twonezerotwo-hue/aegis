"""Signal-only consensus scoring for AEGIS Core.

Source behavior references:
- consensus_engine/src/signal_aggregator.py
- consensus_engine/src/meta_scorer.py
- modules/news-ai-limited/src/signal_models.py
"""

from __future__ import annotations

from typing import Optional

from .regime_weights import get_weights_for_regime

CANONICAL_MODULES = ("touche", "fundamental", "news", "sentinel", "quantum")

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


def _normalize_score_value(raw_score: float) -> float:
    value = float(raw_score)
    if 0.0 <= value <= 1.0:
        value *= 100.0
    return max(0.0, min(100.0, value))


def _normalize_module_scores_with_warnings(module_scores: dict) -> tuple[dict[str, float], list[str]]:
    normalized: dict[str, float] = {}
    warnings: list[str] = []

    if not isinstance(module_scores, dict):
        return {}, ["Module scores payload was not a dictionary."]

    for raw_key, raw_value in module_scores.items():
        canonical_key = _canonical_module_name(raw_key)
        if canonical_key not in CANONICAL_MODULES:
            warnings.append(f"Unknown module '{raw_key}' was ignored.")
            continue

        try:
            normalized[canonical_key] = round(_normalize_score_value(raw_value), 4)
        except (TypeError, ValueError):
            warnings.append(f"Module '{raw_key}' had a non-numeric score and was ignored.")

    return normalized, warnings


def normalize_module_scores(module_scores: dict) -> dict:
    """Normalize module scores to a 0-100 scale using canonical module names."""
    normalized, _ = _normalize_module_scores_with_warnings(module_scores)
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
    normalized_scores, score_warnings = _normalize_module_scores_with_warnings(module_scores)
    normalized_weights, weight_warnings = _coerce_weight_map(weights)
    warnings = score_warnings + weight_warnings

    contributions: dict[str, dict] = {}
    missing_modules: list[str] = []
    consensus_score = 0.0

    for module_name in CANONICAL_MODULES:
        weight = normalized_weights.get(module_name, 0.0)
        if module_name in normalized_scores:
            score_value = normalized_scores[module_name]
            source = "provided"
        else:
            score_value = 50.0
            source = "neutral_fallback"
            missing_modules.append(module_name)
            warnings.append(
                f"Missing module score for '{module_name}'; using neutral fallback score 50.0."
            )

        weighted_score = score_value * weight
        consensus_score += weighted_score
        contributions[module_name] = {
            "score": round(score_value, 4),
            "weight": round(weight, 6),
            "weighted_score": round(weighted_score, 4),
            "source": source,
        }

    return {
        "normalized_scores": normalized_scores,
        "weights_used": normalized_weights,
        "consensus_score": round(consensus_score, 4),
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
        "raw_regime": raw_regime,
        "weight_key": regime_result["weight_key"],
        "weights_used": consensus_result["weights_used"],
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
