from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


FORBIDDEN_SAFE_FIELDS = {
    "action",
    "buy",
    "sell",
    "hold",
    "rebalance",
    "position_size",
    "order",
    "broker",
    "execution",
}


def _drop_forbidden(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in FORBIDDEN_SAFE_FIELDS}


@dataclass(frozen=True)
class SignalCandidate:
    signal_id: str
    symbol: str
    timeframe: str
    direction: str
    score: float
    confidence: float
    edge: float
    decision: str
    reason: str
    mode: str
    created_at: str
    source: str = "agent"
    data_status: str = "UNKNOWN"
    module_scores: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _drop_forbidden(asdict(self))


@dataclass(frozen=True)
class DataSnapshot:
    source: str
    source_timestamp: str | None
    ingested_at: str
    data_status: str
    verified: bool
    fallback_used: bool
    values: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _drop_forbidden(asdict(self))


@dataclass(frozen=True)
class MetricSummary:
    sample_size: int
    hit_rate: float | None
    average_return: float | None
    brier_score: float | None
    calibration_error: float | None
    max_adverse_return: float | None
    max_favorable_return: float | None
    dependency_status: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _drop_forbidden(asdict(self))


@dataclass(frozen=True)
class WeightSuggestion:
    status: str
    proposed_weights: dict[str, float]
    sample_size: int
    expected_improvement: float | None
    reason: str
    risk_warning: str
    shadow_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return _drop_forbidden(asdict(self))


@dataclass(frozen=True)
class ThresholdSuggestion:
    status: str
    proposed_thresholds: dict[str, float]
    sample_size: int
    reason: str
    risk_warning: str
    shadow_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return _drop_forbidden(asdict(self))
