"""Regime context model for AEGIS 5-layer architecture."""

from dataclasses import dataclass
from enum import Enum
from typing import Dict


class RegimeType(str, Enum):
    LIQUIDITY_EXPANSION = "LIQUIDITY_EXPANSION"
    RISK_OFF = "RISK_OFF"
    STAGFLATION = "STAGFLATION"
    NORMALIZATION = "NORMALIZATION"


@dataclass(frozen=True)
class RegimeContext:
    regime: RegimeType
    module_weights: Dict[str, float]


REGIME_MODULE_WEIGHTS: Dict[RegimeType, Dict[str, float]] = {
    RegimeType.LIQUIDITY_EXPANSION: {
        "touche": 0.40,
        "fundamental": 0.30,
        "news": 0.15,
        "sentinel": 0.10,
        "quantum": 0.05,
    },
    RegimeType.RISK_OFF: {
        "touche": 0.20,
        "fundamental": 0.25,
        "news": 0.15,
        "sentinel": 0.30,
        "quantum": 0.10,
    },
    RegimeType.STAGFLATION: {
        "touche": 0.25,
        "fundamental": 0.35,
        "news": 0.10,
        "sentinel": 0.25,
        "quantum": 0.05,
    },
    RegimeType.NORMALIZATION: {
        "touche": 0.35,
        "fundamental": 0.30,
        "news": 0.20,
        "sentinel": 0.10,
        "quantum": 0.05,
    },
}


def get_regime_context(regime: str) -> RegimeContext:
    """Build typed regime context from free-form regime string."""
    normalized = (regime or "NORMALIZATION").strip().upper()
    regime_type = RegimeType.__members__.get(normalized, RegimeType.NORMALIZATION)
    return RegimeContext(regime=regime_type, module_weights=REGIME_MODULE_WEIGHTS[regime_type].copy())
