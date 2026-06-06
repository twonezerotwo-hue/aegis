"""AEGIS research-only helpers.

This package is intentionally outside ``aegis_core``. It may analyze signal
candidates, outcomes, calibration and data adapters, but it must not emit final
investment decisions or execution instructions.
"""

from .models import (
    DataSnapshot,
    MetricSummary,
    SignalCandidate,
    ThresholdSuggestion,
    WeightSuggestion,
)

__all__ = [
    "DataSnapshot",
    "MetricSummary",
    "SignalCandidate",
    "ThresholdSuggestion",
    "WeightSuggestion",
]
