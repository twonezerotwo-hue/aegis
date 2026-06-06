"""Regime-aware weight loading for signal-only AEGIS Core.

Source references:
- consensus_engine/config/consensus_weights.yaml
- dashboard_react/backend/routes/backtest_routes.py
- strategies/sentinel_ai/src/regime_context.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "consensus_weights.yaml"

KNOWN_REGIME_MAP = {
    "LIQUIDITY_EXPANSION": "mega_bull",
    "NORMALIZATION": "bull",
    "RISK_OFF": "bear_2022",
    "ACCUMULATION": "accumulation",
}

DIRECT_WEIGHT_KEYS = {
    "BULL": "bull",
    "MEGA_BULL": "mega_bull",
    "MEGA_BULL_AGGRESSIVE": "mega_bull_aggressive",
    "BEAR_2022": "bear_2022",
    "ACCUMULATION": "accumulation",
    "DEFAULT": "default",
}

WEIGHT_FIELDS = {
    "touche_weight": "touche",
    "fundamental_weight": "fundamental",
    "news_weight": "news",
    "sentinel_weight": "sentinel",
    "quantum_weight": "quantum",
}


def _resolve_config_path(path: Optional[str] = None) -> Path:
    return Path(path).resolve() if path else DEFAULT_CONFIG_PATH


def load_consensus_weights(path: Optional[str] = None) -> dict:
    """Load consensus weights from YAML without silent fallback."""
    config_path = _resolve_config_path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Consensus weights config not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}

    if not isinstance(loaded, dict):
        raise ValueError(f"Consensus weights config must be a mapping: {config_path}")

    return loaded


def map_regime_to_weight_key(raw_regime: str) -> tuple[str, list[str]]:
    """Map external regime names to YAML regime keys and report warnings explicitly."""
    warnings: list[str] = []
    normalized = (raw_regime or "").strip().upper()

    if normalized in KNOWN_REGIME_MAP:
        return KNOWN_REGIME_MAP[normalized], warnings

    if normalized in DIRECT_WEIGHT_KEYS:
        return DIRECT_WEIGHT_KEYS[normalized], warnings

    warnings.append(
        f"Unknown regime '{raw_regime or 'None'}'; falling back to default regime weights."
    )
    return "default", warnings


def _extract_weights(regime_config: dict) -> dict[str, float]:
    weights: dict[str, float] = {}
    for source_key, target_key in WEIGHT_FIELDS.items():
        if source_key not in regime_config:
            raise ValueError(f"Missing required regime weight field: {source_key}")
        try:
            value = float(regime_config[source_key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Regime weight field '{source_key}' must be numeric.") from exc
        if value < 0:
            raise ValueError(f"Regime weight field '{source_key}' cannot be negative.")
        weights[target_key] = value
    return weights


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("Regime weight block must contain a positive total weight.")
    return {key: round(value / total, 6) for key, value in weights.items()}


def get_weights_for_regime(raw_regime: str, path: Optional[str] = None) -> dict:
    """Return regime weights plus explicit warnings and source metadata."""
    config_path = _resolve_config_path(path)
    config = load_consensus_weights(str(config_path))
    warnings: list[str] = []

    weight_key, map_warnings = map_regime_to_weight_key(raw_regime)
    warnings.extend(map_warnings)

    regime_weights = config.get("regime_weights")
    if not isinstance(regime_weights, dict) or not regime_weights:
        raise ValueError(f"Missing 'regime_weights' block in config: {config_path}")

    regime_config = regime_weights.get(weight_key)
    resolved_key = weight_key

    if not isinstance(regime_config, dict):
        warnings.append(
            f"Regime key '{weight_key}' was not found in config; falling back to default regime weights."
        )
        resolved_key = "default"
        regime_config = regime_weights.get("default")

    if not isinstance(regime_config, dict):
        raise ValueError(f"Default regime weights are missing from config: {config_path}")

    raw_weights = _extract_weights(regime_config)
    total = sum(raw_weights.values())
    if abs(total - 1.0) > 1e-9:
        warnings.append(
            f"Regime weights for '{resolved_key}' summed to {total:.6f}; normalized to 1.0."
        )
    weights = _normalize_weights(raw_weights)

    return {
        "weight_key": resolved_key,
        "weights": weights,
        "warnings": warnings,
        "source_config": {
            "path": str(config_path),
            "raw_regime": raw_regime,
            "resolved_weight_key": resolved_key,
            "regime_config": regime_config,
        },
    }
