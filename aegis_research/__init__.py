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
from .external_repo_matrix import repo_feature_table_rows, top10_external_repo_matrix

__all__ = [
    "DataSnapshot",
    "MetricSummary",
    "SignalCandidate",
    "ThresholdSuggestion",
    "WeightSuggestion",
    "repo_feature_table_rows",
    "top10_external_repo_matrix",
]
