from __future__ import annotations

import importlib.util
from statistics import mean
from typing import Any

from .models import MetricSummary


def optional_dependency_status() -> dict[str, str]:
    return {
        "quantstats": "available" if importlib.util.find_spec("quantstats") else "missing_optional_dependency",
        "empyrical": "available" if importlib.util.find_spec("empyrical") else "missing_optional_dependency",
    }


def _as_return(record: dict[str, Any]) -> float | None:
    for key in ("forward_return", "forward_return_pct", "outcome_return", "return_pct"):
        value = record.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _expected_probability(record: dict[str, Any]) -> float:
    confidence = record.get("confidence", 0.5)
    try:
        return max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        return 0.5


def calculate_metric_summary(records: list[dict[str, Any]]) -> MetricSummary:
    observed = [(record, _as_return(record)) for record in records]
    observed = [(record, ret) for record, ret in observed if ret is not None]
    if not observed:
        return MetricSummary(
            sample_size=0,
            hit_rate=None,
            average_return=None,
            brier_score=None,
            calibration_error=None,
            max_adverse_return=None,
            max_favorable_return=None,
            dependency_status=optional_dependency_status(),
        )

    signed_hits: list[float] = []
    brier_terms: list[float] = []
    calibration_terms: list[float] = []
    returns: list[float] = []

    for record, ret in observed:
        assert ret is not None
        returns.append(float(ret))
        direction = str(record.get("direction", "HOLD")).upper()
        if direction == "BUY":
            hit = 1.0 if ret > 0 else 0.0
        elif direction == "SELL":
            hit = 1.0 if ret < 0 else 0.0
        else:
            hit = 1.0 if abs(ret) < 0.001 else 0.0
        signed_hits.append(hit)
        expected = _expected_probability(record)
        brier_terms.append((expected - hit) ** 2)
        calibration_terms.append(abs(expected - hit))

    return MetricSummary(
        sample_size=len(observed),
        hit_rate=round(mean(signed_hits), 6),
        average_return=round(mean(returns), 6),
        brier_score=round(mean(brier_terms), 6),
        calibration_error=round(mean(calibration_terms), 6),
        max_adverse_return=round(min(returns), 6),
        max_favorable_return=round(max(returns), 6),
        dependency_status=optional_dependency_status(),
    )
