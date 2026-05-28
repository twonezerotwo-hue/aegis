"""Core signal-only engine helpers for AEGIS."""

from .backtest import format_backtest_evidence
from .confluence import apply_multi_tf_confluence
from .consensus import (
    build_aegis_signal,
    calculate_consensus_score,
    normalize_module_scores,
)
from .regime_weights import (
    get_weights_for_regime,
    load_consensus_weights,
    map_regime_to_weight_key,
)

__all__ = [
    "apply_multi_tf_confluence",
    "build_aegis_signal",
    "calculate_consensus_score",
    "format_backtest_evidence",
    "get_weights_for_regime",
    "load_consensus_weights",
    "map_regime_to_weight_key",
    "normalize_module_scores",
]
