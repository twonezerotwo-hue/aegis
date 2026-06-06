from __future__ import annotations

from typing import Any

from .metrics import calculate_metric_summary
from .models import ThresholdSuggestion, WeightSuggestion


MIN_SAMPLE_FOR_SUGGESTION = 30


def suggest_thresholds(records: list[dict[str, Any]]) -> ThresholdSuggestion:
    metrics = calculate_metric_summary(records)
    if metrics.sample_size < MIN_SAMPLE_FOR_SUGGESTION:
        return ThresholdSuggestion(
            status="INSUFFICIENT_SAMPLE",
            proposed_thresholds={},
            sample_size=metrics.sample_size,
            reason=f"Need at least {MIN_SAMPLE_FOR_SUGGESTION} labeled candidates before threshold suggestions.",
            risk_warning="Shadow-only. No production config is changed.",
        )

    hit_rate = metrics.hit_rate or 0.0
    calibration_error = metrics.calibration_error or 1.0
    min_confidence = 0.62
    min_score_edge = 0.08

    if hit_rate >= 0.58 and calibration_error <= 0.35:
        min_confidence = 0.58
        min_score_edge = 0.06
    elif hit_rate < 0.50 or calibration_error > 0.45:
        min_confidence = 0.68
        min_score_edge = 0.10

    return ThresholdSuggestion(
        status="SHADOW_SUGGESTION",
        proposed_thresholds={
            "min_confidence": min_confidence,
            "min_score_edge": min_score_edge,
        },
        sample_size=metrics.sample_size,
        reason=(
            f"hit_rate={hit_rate:.3f}, calibration_error={calibration_error:.3f}; "
            "suggestion must be shadow-tested before promotion."
        ),
        risk_warning="Owner approval required before production config change.",
    )


def suggest_module_weights(module_metrics: dict[str, dict[str, float]], *, sample_size: int) -> WeightSuggestion:
    if sample_size < MIN_SAMPLE_FOR_SUGGESTION:
        return WeightSuggestion(
            status="INSUFFICIENT_SAMPLE",
            proposed_weights={},
            sample_size=sample_size,
            expected_improvement=None,
            reason=f"Need at least {MIN_SAMPLE_FOR_SUGGESTION} labeled candidates before weight suggestions.",
            risk_warning="Shadow-only. No production config is changed.",
        )

    raw_scores: dict[str, float] = {}
    for module, values in module_metrics.items():
        hit_rate = float(values.get("hit_rate", 0.5))
        calibration_error = float(values.get("calibration_error", 0.5))
        raw_scores[module] = max(0.01, hit_rate * (1.0 - min(1.0, calibration_error)))

    total = sum(raw_scores.values())
    weights = {module: round(score / total, 6) for module, score in raw_scores.items()} if total else {}
    return WeightSuggestion(
        status="SHADOW_SUGGESTION",
        proposed_weights=weights,
        sample_size=sample_size,
        expected_improvement=None,
        reason="Weights are derived from labeled candidate reliability and require shadow validation.",
        risk_warning="Owner approval required before production config change.",
    )
