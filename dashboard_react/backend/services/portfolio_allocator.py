"""
AEGIS dynamic portfolio allocator.

The allocator is horizon-aware first, then applies macro regime, hedge, event-risk,
volatility, and data-quality overlays to produce illustrative multi-asset weights.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_ASSETS = ("gold", "btc", "bond", "commodity", "cash")
_UNVERIFIED_STATUSES = {"FALLBACK", "PARTIAL_FALLBACK", "MOCK", "MISSING", "UNKNOWN"}

_HORIZON_BASE = {
    "short": {"gold": 0.18, "btc": 0.12, "bond": 0.25, "commodity": 0.10, "cash": 0.35},
    "medium": {"gold": 0.22, "btc": 0.20, "bond": 0.25, "commodity": 0.13, "cash": 0.20},
    "long": {"gold": 0.25, "btc": 0.28, "bond": 0.18, "commodity": 0.17, "cash": 0.12},
}

_PROFILE_BY_HORIZON = {
    "short": "defensive",
    "medium": "balanced",
    "long": "structural",
}

_REGIME_OVERLAYS = {
    "RISK_OFF": {"gold": 0.05, "btc": -0.09, "bond": 0.08, "commodity": -0.05, "cash": 0.01},
    "NORMALIZATION": {"gold": 0.00, "btc": 0.00, "bond": 0.00, "commodity": 0.00, "cash": 0.00},
    "LIQUIDITY_EXPANSION": {"gold": -0.01, "btc": 0.08, "bond": -0.06, "commodity": 0.05, "cash": -0.06},
    "ACCUMULATION": {"gold": 0.02, "btc": 0.04, "bond": 0.03, "commodity": 0.01, "cash": -0.04},
}

_RISK_LIMITS = {
    "short": {
        "mins": {"gold": 0.12, "btc": 0.05, "bond": 0.18, "commodity": 0.03, "cash": 0.22},
        "maxs": {"gold": 0.30, "btc": 0.18, "bond": 0.40, "commodity": 0.14, "cash": 0.58},
        "trim_priority": ("btc", "commodity", "gold", "bond", "cash"),
        "add_priority": ("cash", "bond", "gold", "btc", "commodity"),
    },
    "medium": {
        "mins": {"gold": 0.14, "btc": 0.06, "bond": 0.15, "commodity": 0.05, "cash": 0.14},
        "maxs": {"gold": 0.32, "btc": 0.28, "bond": 0.36, "commodity": 0.20, "cash": 0.42},
        "trim_priority": ("btc", "commodity", "gold", "bond", "cash"),
        "add_priority": ("gold", "btc", "bond", "commodity", "cash"),
    },
    "long": {
        "mins": {"gold": 0.16, "btc": 0.08, "bond": 0.10, "commodity": 0.07, "cash": 0.08},
        "maxs": {"gold": 0.36, "btc": 0.40, "bond": 0.30, "commodity": 0.24, "cash": 0.28},
        "trim_priority": ("commodity", "btc", "bond", "gold", "cash"),
        "add_priority": ("btc", "gold", "commodity", "bond", "cash"),
    },
}

_ILLUSTRATIVE_CASH_FLOOR = {
    "short": 0.30,
    "medium": 0.24,
    "long": 0.18,
}

_RATIONALE = {
    "RISK_OFF": {
        "cash": "Higher liquidity buffer for shorter-dated uncertainty",
        "btc": "Reduced crypto concentration under risk-off conditions",
        "gold": "Safe-haven ballast during stressed macro conditions",
        "bond": "Capital preservation and duration support",
        "commodity": "Commodity sleeve reduced under defensive regime",
    },
    "NORMALIZATION": {
        "cash": "Liquidity reserve for balanced portfolio maintenance",
        "btc": "Core risk allocation sized to the selected horizon",
        "gold": "Strategic diversifier against macro variance",
        "bond": "Income and stability ballast",
        "commodity": "Moderate real-asset diversification",
    },
    "LIQUIDITY_EXPANSION": {
        "cash": "Lower idle cash while liquidity supports risk assets",
        "btc": "Higher structural crypto exposure in supportive liquidity backdrop",
        "gold": "Maintained hard-asset hedge alongside growth risk",
        "bond": "Reduced fixed-income weight in pro-risk regime",
        "commodity": "Expanded real-asset sleeve in supportive macro backdrop",
    },
    "ACCUMULATION": {
        "cash": "Reserve capital for gradual accumulation",
        "btc": "Measured accumulation posture with risk controls",
        "gold": "Preservation anchor during base-building regime",
        "bond": "Carry sleeve while waiting for trend confirmation",
        "commodity": "Selective commodity exposure during accumulation",
    },
}


def _normalize_horizon(horizon: str) -> str:
    return horizon if horizon in _HORIZON_BASE else "medium"


def _clip(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, float(weights.get(asset, 0.0))) for asset in _ASSETS)
    if total <= 0:
        return dict(_HORIZON_BASE["medium"])
    return {asset: max(0.0, float(weights.get(asset, 0.0))) / total for asset in _ASSETS}


def _match_regime(regime: str) -> str:
    normalized = str(regime or "NORMALIZATION").upper().replace("-", "_").replace(" ", "_")
    if "RISK_OFF" in normalized:
        return "RISK_OFF"
    if "LIQ" in normalized or "RISK_ON" in normalized:
        return "LIQUIDITY_EXPANSION"
    if "ACCUMULATION" in normalized:
        return "ACCUMULATION"
    return "NORMALIZATION"


def _get_float(value: Any, default: float | None = None) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _normalize_data_status(data_status: str | None, verified: bool) -> str:
    if isinstance(data_status, str) and data_status.strip():
        return data_status.strip().upper()
    return "UNKNOWN" if not verified else "LIVE"


def _derive_hedge_signal(metrics: dict[str, Any]) -> bool:
    vix = _get_float(metrics.get("vix"), 0.0) or 0.0
    dxy = _get_float(metrics.get("dxy"), 0.0) or 0.0
    us10y = _get_float(metrics.get("us10y"), 0.0) or 0.0
    event_risk = _get_float(metrics.get("event_risk_score"), 0.0) or 0.0
    return vix >= 25 or dxy >= 103 or us10y >= 4.6 or event_risk >= 0.55


def _apply_overlay(
    weights: dict[str, float],
    overlay: dict[str, float],
    basis: list[str],
    label: str,
) -> None:
    if not overlay:
        return
    for asset, delta in overlay.items():
        if asset in weights:
            weights[asset] = max(0.01, weights[asset] + delta)
    basis.append(label)


def _build_constraints(horizon: str, illustrative: bool) -> tuple[dict[str, float], dict[str, float]]:
    base_limits = _RISK_LIMITS[horizon]
    mins = dict(base_limits["mins"])
    maxs = dict(base_limits["maxs"])
    if illustrative:
        mins["cash"] = max(mins["cash"], _ILLUSTRATIVE_CASH_FLOOR[horizon])
        maxs["btc"] = min(maxs["btc"], {"short": 0.15, "medium": 0.22, "long": 0.30}[horizon])
        maxs["commodity"] = min(maxs["commodity"], {"short": 0.12, "medium": 0.16, "long": 0.20}[horizon])
    return mins, maxs


def _rebalance_to_total(
    weights: dict[str, float],
    mins: dict[str, float],
    maxs: dict[str, float],
    horizon: str,
) -> dict[str, float]:
    rebalanced = {asset: _clip(weights[asset], mins[asset], maxs[asset]) for asset in _ASSETS}
    total = sum(rebalanced.values())
    if abs(total - 1.0) < 1e-9:
        return rebalanced

    if total > 1.0:
        excess = total - 1.0
        for asset in _RISK_LIMITS[horizon]["trim_priority"]:
            room = rebalanced[asset] - mins[asset]
            if room <= 0:
                continue
            move = min(room, excess)
            rebalanced[asset] -= move
            excess -= move
            if excess <= 1e-9:
                break
    else:
        shortfall = 1.0 - total
        for asset in _RISK_LIMITS[horizon]["add_priority"]:
            room = maxs[asset] - rebalanced[asset]
            if room <= 0:
                continue
            move = min(room, shortfall)
            rebalanced[asset] += move
            shortfall -= move
            if shortfall <= 1e-9:
                break

    diff = 1.0 - sum(rebalanced.values())
    if abs(diff) > 1e-9:
        cash_room = maxs["cash"] - rebalanced["cash"] if diff > 0 else rebalanced["cash"] - mins["cash"]
        if cash_room > 0:
            rebalanced["cash"] += max(-cash_room, min(cash_room, diff))

    final_diff = 1.0 - sum(rebalanced.values())
    if abs(final_diff) > 1e-9:
        for asset in _ASSETS:
            if final_diff > 0 and rebalanced[asset] < maxs[asset]:
                move = min(maxs[asset] - rebalanced[asset], final_diff)
                rebalanced[asset] += move
                final_diff -= move
            elif final_diff < 0 and rebalanced[asset] > mins[asset]:
                move = min(rebalanced[asset] - mins[asset], abs(final_diff))
                rebalanced[asset] -= move
                final_diff += move
            if abs(final_diff) <= 1e-9:
                break

    return {asset: round(rebalanced[asset], 6) for asset in _ASSETS}


def _apply_ai_signal_overlay(
    weights: dict[str, float],
    module_scores: dict[str, float],
    horizon: str,
    basis: list[str],
    warnings: list[str],
) -> None:
    """
    Adjust allocation weights based on live AI module scores.
    All scores are 0-1. Neutral = 0.5. Scale = ±deviation from 0.5.
    Max single move: BTC ±6pp, gold ±3pp, commodity ±2pp, cash ±5pp.
    """
    touche    = float(module_scores.get("touche", 0.5))
    fundamental = float(module_scores.get("fundamental", 0.5))
    news      = float(module_scores.get("news", 0.5))
    sentinel  = float(module_scores.get("sentinel", 0.5))  # high = low risk

    # ── BTC signal: Touche 50%, Fundamental 30%, Sentinel risk 20% ────────────
    btc_signal = touche * 0.50 + fundamental * 0.30 + sentinel * 0.20
    btc_dev = btc_signal - 0.5          # −0.5 to +0.5
    # Scale: ±0.5 deviation → ±6pp for long, ±4pp for short
    btc_scale = {"short": 0.08, "medium": 0.10, "long": 0.12}.get(horizon, 0.10)
    btc_delta = round(btc_dev * btc_scale, 4)

    # ── Risk/defensive signal: Sentinel 50%, News 30%, Fundamental 20% ───────
    risk_signal = sentinel * 0.50 + news * 0.30 + fundamental * 0.20
    risk_dev = risk_signal - 0.5        # positive = safer environment
    gold_delta = round(-risk_dev * 0.06, 4)   # safer → less gold buffer needed
    cash_delta = round(-btc_delta * 0.60 + -risk_dev * 0.05, 4)
    commodity_delta = round(btc_dev * 0.04, 4)  # follows BTC risk-on/off

    overlay = {
        "btc":       btc_delta,
        "gold":      gold_delta,
        "cash":      cash_delta,
        "commodity": commodity_delta,
        "bond":      round(-(btc_delta + gold_delta + cash_delta + commodity_delta), 4),
    }

    _apply_overlay(weights, overlay, basis,
                   f"ai_signal:T={touche:.2f},F={fundamental:.2f},N={news:.2f},S={sentinel:.2f}")

    if abs(btc_delta) >= 0.02:
        direction = "artırıldı" if btc_delta > 0 else "azaltıldı"
        warnings.append(
            f"AI sinyali BTC ağırlığını {direction} "
            f"(Touche {touche*100:.0f}%, Fundamental {fundamental*100:.0f}%)."
        )
    if abs(gold_delta) >= 0.015:
        direction = "artırıldı" if gold_delta > 0 else "azaltıldı"
        warnings.append(
            f"Risk ortamına göre altın ağırlığı {direction} "
            f"(Sentinel {sentinel*100:.0f}%, Haberler {news*100:.0f}%)."
        )


def build_allocation_plan(
    horizon: str = "medium",
    regime: str = "NORMALIZATION",
    metrics: dict[str, Any] | None = None,
    data_status: str | None = None,
    verified: bool = True,
    hedge_on: bool | None = None,
    module_scores: dict[str, float] | None = None,
) -> dict[str, Any]:
    horizon = _normalize_horizon(horizon)
    metrics = metrics if isinstance(metrics, dict) else {}
    matched_regime = _match_regime(regime)
    normalized_status = _normalize_data_status(data_status, verified)
    illustrative = normalized_status in _UNVERIFIED_STATUSES or verified is False
    derived_hedge = _derive_hedge_signal(metrics) if hedge_on is None else bool(hedge_on)
    event_risk_score = _get_float(metrics.get("event_risk_score"), 0.0) or 0.0
    vix = _get_float(metrics.get("vix"), 0.0) or 0.0

    weights = dict(_HORIZON_BASE[horizon])
    basis = [f"horizon_base:{horizon}", f"regime_overlay:{matched_regime.lower()}"]
    warnings: list[str] = []

    _apply_overlay(weights, _REGIME_OVERLAYS[matched_regime], basis, f"profile:{_PROFILE_BY_HORIZON[horizon]}")

    if derived_hedge:
        hedge_overlay = (
            {"gold": 0.03, "bond": 0.04, "cash": 0.02, "btc": -0.05, "commodity": -0.04}
            if horizon == "short"
            else {"gold": 0.03, "bond": 0.03, "cash": 0.01, "btc": -0.04, "commodity": -0.03}
        )
        _apply_overlay(weights, hedge_overlay, basis, "hedge_overlay:on")
        warnings.append("Hedge overlay reduced higher-volatility sleeves.")

    if event_risk_score >= 0.45:
        intensity = min(1.0, (event_risk_score - 0.45) / 0.40)
        overlay = {
            "gold": 0.02 + (0.03 * intensity),
            "btc": -(0.04 + (0.05 * intensity)),
            "bond": 0.01 * intensity,
            "commodity": -(0.02 + (0.03 * intensity)),
            "cash": 0.04 + (0.05 * intensity),
        }
        _apply_overlay(weights, overlay, basis, f"event_risk_overlay:{event_risk_score:.2f}")
        warnings.append("Elevated event risk increased cash and gold buffers.")

    if vix >= 28:
        overlay = {
            "gold": 0.03,
            "btc": -0.05,
            "bond": 0.02,
            "commodity": -0.03,
            "cash": 0.03,
        }
        _apply_overlay(weights, overlay, basis, "volatility_overlay:high_vix")
        warnings.append("High VIX shifted the mix toward defense.")
    elif vix > 0 and vix <= 15 and horizon == "long" and not illustrative:
        overlay = {
            "gold": 0.01,
            "btc": 0.03,
            "bond": -0.02,
            "commodity": 0.02,
            "cash": -0.02,
        }
        _apply_overlay(weights, overlay, basis, "volatility_overlay:low_vix")

    # ── AI signal overlay (live module scores) ────────────────────────────────
    if module_scores and not illustrative:
        _apply_ai_signal_overlay(weights, module_scores, horizon, basis, warnings)

    if illustrative:
        overlay = {
            "gold": 0.02,
            "btc": -0.06,
            "bond": 0.03,
            "commodity": -0.05,
            "cash": 0.06,
        }
        _apply_overlay(weights, overlay, basis, f"data_quality_overlay:{normalized_status.lower()}")
        warnings.append("Illustrative allocation based on incomplete/fallback macro data.")

    mins, maxs = _build_constraints(horizon, illustrative)
    normalized = _normalize(weights)
    constrained = _rebalance_to_total(normalized, mins, maxs, horizon)
    adjustments = {
        asset: round(constrained[asset] - _HORIZON_BASE[horizon][asset], 4)
        for asset in _ASSETS
    }

    profile = "fallback_illustrative" if illustrative else _PROFILE_BY_HORIZON[horizon]
    if matched_regime == "RISK_OFF" and not illustrative:
        warnings.append("Risk-off regime is tilting the base profile toward defense.")

    return {
        "weights": constrained,
        "allocation_horizon": horizon,
        "allocation_profile": profile,
        "allocation_basis": basis,
        "data_status": normalized_status,
        "verified": False if illustrative else bool(verified),
        "warnings": warnings,
        "horizon_adjustments": adjustments,
        "matched_regime": matched_regime,
        "hedge_on": derived_hedge,
    }


def calculate_dynamic_allocation(
    horizon: str = "medium",
    regime: str = "NORMALIZATION",
    module_scores: dict | None = None,
    metrics: dict[str, Any] | None = None,
    data_status: str | None = None,
    verified: bool = True,
    hedge_on: bool | None = None,
) -> dict:
    """
    Calculate allocation percentages plus rationale text for UI or reporting surfaces.
    """
    plan = build_allocation_plan(
        horizon=horizon,
        regime=regime,
        metrics=metrics,
        data_status=data_status,
        verified=verified,
        hedge_on=hedge_on,
        module_scores=module_scores,
    )
    rationale_map = _RATIONALE.get(plan["matched_regime"], _RATIONALE["NORMALIZATION"])

    result = {}
    for asset, weight in plan["weights"].items():
        rationale = rationale_map.get(asset, "")
        if plan["allocation_profile"] == "fallback_illustrative":
            rationale = f"{rationale} Illustrative only until verified macro data is available.".strip()
        result[asset] = {
            "allocation_pct": round(weight * 100, 1),
            "rationale": rationale,
        }

    logger.info(
        "Portfolio allocation: horizon=%s regime=%s profile=%s weights=%s",
        plan["allocation_horizon"],
        plan["matched_regime"],
        plan["allocation_profile"],
        {asset: round(weight * 100, 1) for asset, weight in plan["weights"].items()},
    )
    return result


def get_allocation_weights(
    horizon: str = "medium",
    regime: str = "NORMALIZATION",
    metrics: dict[str, Any] | None = None,
    data_status: str | None = None,
    verified: bool = True,
    hedge_on: bool | None = None,
) -> dict:
    """Return normalized allocation weights only (0-1 scale)."""
    return build_allocation_plan(
        horizon=horizon,
        regime=regime,
        metrics=metrics,
        data_status=data_status,
        verified=verified,
        hedge_on=hedge_on,
    )["weights"]
