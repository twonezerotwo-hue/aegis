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

ASSET_METADATA: dict[str, dict] = {
    "gold": {
        "display_label": "ALTIN / GOLD",
        "subtitle": "XAU · Gold futures / physical gold proxy",
        "definition": "Kriz güvenli limanı, jeopolitik risk hedge'i, dolar zayıflığı ve reel faiz düşüşü senaryosunda koruma.",
        "portfolio_role": "Safe-haven ballast; hedge against USD weakness, geopolitical crisis, and falling real yields.",
        "increase_conditions": [
            "Risk-off or crisis regime",
            "DXY weak or declining",
            "Real yields falling",
            "Geopolitics / war risk elevated",
            "VIX high with gold trend confirmed",
        ],
        "reduce_conditions": [
            "Strong risk-on or liquidity expansion regime",
            "Real yields rising sharply",
            "Dollar strengthening (DXY > 104)",
            "Gold trend broken",
        ],
    },
    "btc": {
        "display_label": "BITCOIN / BTC",
        "subtitle": "Crypto core risk asset",
        "definition": "Likidite genişlemesi, risk-on beta, dijital varlık maruziyeti. Yüksek volatilite, yüksek büyüme potansiyeli.",
        "portfolio_role": "Liquidity expansion beta; risk-on exposure; digital scarcity and decentralization hedge.",
        "increase_conditions": [
            "Liquidity expansion regime confirmed",
            "BTC trend and momentum confirmed",
            "Stablecoin dominance declining (USDT.D down)",
            "DXY weak, VIX low or declining",
        ],
        "reduce_conditions": [
            "Risk-off or crisis regime",
            "Credit stress or systemic risk elevated",
            "BTC key support breakdown",
            "Funding rates overheated",
            "Data quality failure or kill switch",
        ],
    },
    "bond": {
        "display_label": "TAHVİL / BONDS",
        "subtitle": "Short-to-medium duration bonds · defensive ballast",
        "definition": "Sermaye koruma, gelir üretimi, defansif denge. Faiz indirim senaryolarında değer kazanır.",
        "portfolio_role": "Capital preservation, income, defensive ballast; benefits from rate cuts and flight-to-safety bids.",
        "increase_conditions": [
            "Risk-off regime",
            "Yields stabilizing or falling",
            "Credit stress with sovereign safety bid",
            "Recession risk rising",
        ],
        "reduce_conditions": [
            "Yields rising sharply",
            "Inflation acceleration",
            "Risk-on or liquidity expansion regime",
            "Duration drawdown risk elevated",
        ],
    },
    "commodity": {
        "display_label": "EMTİA / COMMODITIES",
        "subtitle": "Energy + industrial metals basket · Brent/WTI energy proxy · Copper/HG industrial proxy",
        "definition": "Enerji şoku koruması, enflasyon hedge'i, sanayi döngüsü maruziyeti. Brent/WTI (enerji) ve bakır/HG (sanayi metali) sepetini temsil eder.",
        "portfolio_role": "Inflation hedge; energy shock signal; industrial cycle and commodity risk diversification.",
        "increase_conditions": [
            "Brent / WTI uptrend confirmed",
            "Copper (HG) strength, industrial demand rising",
            "Inflation or supply shock regime",
            "War / energy risk confirmed",
        ],
        "reduce_conditions": [
            "Demand slowdown or recession risk",
            "DXY strong (commodity headwind)",
            "Energy shock fading",
            "Commodity trend weak or broken",
        ],
    },
    "cash": {
        "display_label": "NAKİT / CASH",
        "subtitle": "Liquidity reserve · opportunity capital · error margin",
        "definition": "Nakit aylak para değildir. Opsiyonellik, hata marjı, psikolojik istikrar ve gelecekteki fırsat sermayesidir.",
        "portfolio_role": "Liquidity reserve; optionality; error margin; psychological buffer; dry powder for future entries.",
        "increase_conditions": [
            "Neutral, risk-off, or crisis regime",
            "Data quality weak or unverified",
            "Event risk high",
            "Conflicting signals across modules",
            "Waiting for verified entry opportunity",
        ],
        "reduce_conditions": [
            "Verified risk-on with strong cross-validation",
            "Low event risk confirmed",
            "Attractive setup confirmed by multiple modules",
            "Liquidity expansion regime with live data",
        ],
    },
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

    # ML skoru dahil et (eğitilmişse ağırlıklı, değilse 0.5 nötr katkı)
    try:
        from routes.ml_model import get_ml_score as _gml, is_ml_trained as _iml
        ml_score   = _gml("BTC/USDT", "4h")
        ml_trained = _iml("BTC/USDT", "4h")
    except Exception:
        ml_score   = 0.5
        ml_trained = False

    # ── BTC signal: ML dahil edildi ───────────────────────────────────────────
    if ml_trained:
        # ML 30%, Touche 40%, Fundamental 20%, Sentinel 10%
        btc_signal = ml_score * 0.30 + touche * 0.40 + fundamental * 0.20 + sentinel * 0.10
    else:
        btc_signal = touche * 0.50 + fundamental * 0.30 + sentinel * 0.20
    btc_dev = btc_signal - 0.5
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

    ml_label = f",ML={ml_score:.2f}" if ml_trained else ""
    _apply_overlay(weights, overlay, basis,
                   f"ai_signal:T={touche:.2f},F={fundamental:.2f},N={news:.2f},S={sentinel:.2f}{ml_label}")

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


def build_real_estate_decision(
    horizon: str = "medium",
    regime: str = "NORMALIZATION",
    metrics: dict[str, Any] | None = None,
    data_status: str | None = None,
    verified: bool = True,
    cash_weight: float = 0.20,
) -> dict:
    """
    Real estate / property decision support signal.
    NOT financial advice — macro context for illiquid capital allocation.
    Signal: WAIT | RESEARCH | BUY_ZONE | BUILD_ZONE | AVOID
    """
    metrics = metrics if isinstance(metrics, dict) else {}
    horizon = _normalize_horizon(horizon)
    matched_regime = _match_regime(regime)
    normalized_status = _normalize_data_status(data_status, verified)
    unverified = normalized_status in _UNVERIFIED_STATUSES or not verified

    vix = _get_float(metrics.get("vix"), 22.0) or 22.0
    us10y = _get_float(metrics.get("us10y"), 4.25) or 4.25
    event_risk = _get_float(metrics.get("event_risk_score"), 0.25) or 0.25
    brent = _get_float(metrics.get("brent"), 92.0) or 92.0

    required_checks = [
        "Local property prices and market conditions (not in this system)",
        "Personal cash buffer: min 12 months living expenses + 20% purchase buffer",
        "Mortgage / financing rate: current vs historical trend",
        "Legal due diligence: title deed, permits, zoning",
        "Construction cost inflation: materials + labor trend",
        "Personal income stability over the investment horizon",
        "Local vacancy rates and rental demand / supply balance",
    ]

    rationale: list[str] = []
    buy_conditions: list[str] = []
    avoid_conditions: list[str] = []
    construction_conditions: list[str] = []
    score = 50

    if matched_regime == "RISK_OFF":
        avoid_conditions.append("Risk-off macro regime — capital preservation preferred over illiquid commitments")
        score -= 35
    elif matched_regime == "ACCUMULATION":
        rationale.append("Accumulation regime: base-building phase, limited liquidity flexibility")
        score -= 5
    elif matched_regime == "LIQUIDITY_EXPANSION":
        rationale.append("Liquidity expansion: illiquid allocation competes with liquid risk-on opportunities")
        score += 5
    else:
        rationale.append("Neutral macro regime: no strong buy or avoid signal from macro conditions")

    if event_risk >= 0.65:
        avoid_conditions.append(f"High event risk ({event_risk:.0%}) — wait for macro resolution")
        score -= 25
    elif event_risk >= 0.45:
        rationale.append(f"Elevated event risk ({event_risk:.0%}) — caution warranted")
        score -= 10

    if us10y >= 5.0:
        avoid_conditions.append(f"Very high rates (US10Y {us10y:.2f}%) — financing cost significantly elevated")
        score -= 20
    elif us10y >= 4.5:
        avoid_conditions.append(f"High rates (US10Y {us10y:.2f}%) — wait for rate stabilization or decline")
        score -= 10
    elif us10y <= 3.5:
        buy_conditions.append(f"Rates supportive (US10Y {us10y:.2f}%) — favorable financing environment")
        construction_conditions.append(f"Financing cost attractive for construction (US10Y {us10y:.2f}%)")
        score += 15
    else:
        rationale.append(f"Rates neutral (US10Y {us10y:.2f}%)")

    if vix >= 30:
        avoid_conditions.append(f"High market stress (VIX {vix:.1f}) — illiquid commitment not recommended")
        score -= 15
    elif vix >= 25:
        rationale.append(f"Elevated volatility (VIX {vix:.1f}) — cautious stance preferred")
        score -= 5
    elif vix <= 15:
        buy_conditions.append(f"Calm market environment (VIX {vix:.1f}) — lower systemic risk")
        score += 5

    if brent >= 100:
        construction_conditions.append(f"High energy costs (Brent ${brent:.0f}) elevate construction expenses")
        score -= 5
    elif brent <= 75:
        construction_conditions.append(f"Lower energy costs (Brent ${brent:.0f}) reduce construction inputs")
        score += 5

    if cash_weight >= 0.35:
        buy_conditions.append("Strong portfolio liquidity reserve — sufficient buffer for illiquid commitment")
        construction_conditions.append("Strong cash allocation supports construction financing")
        score += 10
    elif cash_weight >= 0.25:
        rationale.append("Adequate cash buffer — manageable, monitor liquidity needs")
        score += 3
    elif cash_weight <= 0.15:
        avoid_conditions.append("Insufficient portfolio cash reserve — improve liquidity first")
        score -= 20

    if horizon == "short":
        avoid_conditions.append("Short horizon selected — real estate requires long-term commitment (5+ years minimum)")
        score -= 25
    elif horizon == "long":
        buy_conditions.append("Long investment horizon aligns with real estate illiquidity profile")
        construction_conditions.append("Long horizon suitable for full construction and development cycles")
        score += 15
    else:
        rationale.append("Medium horizon: real estate possible but long-term local conditions must be verified")
        score -= 5

    if unverified:
        rationale.append("Macro data not fully verified — local due diligence is even more critical")
        score -= 15

    score = max(0, min(100, score))
    confidence = score

    if matched_regime == "RISK_OFF" or (event_risk >= 0.65 and vix >= 28):
        signal = "AVOID"
    elif score >= 65 and horizon == "long" and not unverified and cash_weight >= 0.25:
        signal = "BUY_ZONE"
    elif score >= 55 and horizon in ("medium", "long") and us10y <= 4.0 and not unverified:
        signal = "BUILD_ZONE"
    elif score >= 38:
        signal = "RESEARCH"
    elif score >= 20:
        signal = "WAIT"
    else:
        signal = "AVOID"

    if unverified and signal in ("BUY_ZONE", "BUILD_ZONE"):
        signal = "RESEARCH"
        rationale.append("Signal downgraded: macro data not fully verified — local data required")

    warning = (
        "Bu panel likit portföy yüzdesi değildir. Yatırım tavsiyesi değildir — "
        "makro koşul bazlı karar destek sinyalidir. Yerel piyasa koşulları, "
        "hukuki due diligence ve kişisel finansal durum değerlendirmesi zorunludur."
        if signal in ("BUY_ZONE", "BUILD_ZONE", "RESEARCH")
        else None
    )

    return {
        "signal": signal,
        "confidence": round(confidence),
        "data_status": normalized_status,
        "verified": bool(verified and not unverified),
        "rationale": rationale,
        "buy_conditions": buy_conditions,
        "avoid_conditions": avoid_conditions,
        "construction_conditions": construction_conditions,
        "required_checks": required_checks,
        "warning": warning,
        "disclaimer": "Decision support / due diligence signal only. Not financial advice.",
    }


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
        "asset_metadata": ASSET_METADATA,
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
