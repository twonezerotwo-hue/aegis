"""AEGIS Core: signal-only package for future BrainChain integration."""

from .adapters.brainchain_adapter import to_brainchain_signal
from .engine.backtest import format_backtest_evidence
from .engine.confluence import apply_multi_tf_confluence
from .engine.consensus import (
    build_aegis_signal,
    calculate_consensus_score,
    normalize_module_scores,
)
from .engine.regime_weights import (
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
    "to_brainchain_signal",
]

__version__ = "7.2_core"
