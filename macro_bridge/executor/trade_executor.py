from macro_bridge.config.settings import HEDGE_TRIGGERS, POSITION_SIZE, STOP_LOSS
from macro_bridge.utils.helpers import clamp


def _normalize_regime(regime: str) -> str:
    if regime == "liquidity_expansion":
        return "risk_on"
    if regime == "risk_off":
        return "risk_off"
    return "normal"


def calculate_position_size(regime: str, macro_score: float, confidence: float) -> float:
    regime_key = _normalize_regime(regime)
    base = POSITION_SIZE[regime_key]
    macro_adj = 1.0 + (macro_score * 0.5)
    conf_adj = 0.6 + clamp(confidence, 0.0, 1.0) * 0.8
    size = base * macro_adj * conf_adj
    return round(clamp(size, 0.01, 1.0), 4)


def calculate_stop_loss(regime: str, entry_price: float, atr: float) -> float:
    regime_key = _normalize_regime(regime)
    pct = STOP_LOSS[regime_key]
    pct_stop = entry_price * (1.0 - pct)

    atr_multiplier = 1.0 if regime_key == "risk_off" else 1.5
    atr_stop = entry_price - (atr * atr_multiplier)

    # Use the tighter stop between percentage and ATR models.
    stop = max(pct_stop, atr_stop)
    return round(stop, 2)


def check_hedge(vix: float, dxy: float, us10y: float) -> bool:
    return bool(
        vix >= HEDGE_TRIGGERS["vix"]
        or dxy >= HEDGE_TRIGGERS["dxy"]
        or us10y >= HEDGE_TRIGGERS["us10y"]
    )


def calculate_asset_allocation(regime: str, macro_score: float, hedge: bool = False) -> dict:
    regime_key = _normalize_regime(regime)

    # Strategic base mix by macro regime.
    base_weights = {
        "risk_on": {"gold": 0.12, "btc": 0.45, "bond": 0.10, "commodity": 0.18, "cash": 0.15},
        "risk_off": {"gold": 0.28, "btc": 0.06, "bond": 0.34, "commodity": 0.10, "cash": 0.22},
        "normal": {"gold": 0.20, "btc": 0.20, "bond": 0.25, "commodity": 0.15, "cash": 0.20},
    }

    weights = dict(base_weights[regime_key])

    # Tactical tilt from macro score in [-1, 1].
    weights["btc"] += 0.18 * macro_score
    weights["bond"] -= 0.10 * macro_score
    weights["cash"] -= 0.06 * macro_score
    weights["gold"] -= 0.03 * macro_score
    weights["commodity"] += 0.01 * macro_score

    if hedge:
        # Defensive overlay when hedge warning is active.
        weights["gold"] += 0.04
        weights["bond"] += 0.04
        weights["cash"] += 0.04
        weights["btc"] -= 0.08
        weights["commodity"] -= 0.04

    for key in weights:
        weights[key] = max(0.01, weights[key])

    total = sum(weights.values())
    normalized = {k: v / total for k, v in weights.items()}

    rounded = {k: round(v, 4) for k, v in normalized.items()}
    delta = round(1.0 - sum(rounded.values()), 4)
    rounded["cash"] = round(rounded["cash"] + delta, 4)

    return rounded


def generate_rebalance_signal(target_allocation: dict, current_allocation: dict | None = None, threshold: float = 0.05) -> dict:
    current = current_allocation or target_allocation
    asset_keys = sorted(set(target_allocation.keys()) | set(current.keys()))

    deltas = {}
    actions = []
    max_deviation = 0.0

    for asset in asset_keys:
        target_weight = float(target_allocation.get(asset, 0.0))
        current_weight = float(current.get(asset, 0.0))
        deviation = round(target_weight - current_weight, 4)
        deltas[asset] = deviation
        max_deviation = max(max_deviation, abs(deviation))

        if abs(deviation) > threshold:
            action = "BUY" if deviation > 0 else "SELL"
            actions.append(
                {
                    "asset": asset,
                    "action": action,
                    "current_weight": round(current_weight, 4),
                    "target_weight": round(target_weight, 4),
                    "deviation": deviation,
                }
            )

    return {
        "rebalance_required": bool(actions),
        "threshold": threshold,
        "max_deviation": round(max_deviation, 4),
        "actions": actions,
        "drift": deltas,
    }
