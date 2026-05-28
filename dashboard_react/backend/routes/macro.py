"""Macro routes — real market data (yfinance / CoinGecko) + Sentinel event risk.
AEGIS v7.2: field-level data provenance, canonical fallback/verified metadata.

Every response includes:
  data_status     : LIVE | PARTIAL_FALLBACK | FALLBACK | UNKNOWN
  verified        : true only when ALL fields come from live sources
  live            : same as verified
  fallback_used   : true when any field is hardcoded
  fallback_fields : list of fields using hardcoded values
  verified_fields : list of fields from live sources
  field_sources   : per-field {source, verified, fallback_used, timestamp}
  warning         : human-readable summary when degraded
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import os

import httpx
from fastapi import APIRouter, Query

from services.market_data import fetch_market_data
from services.portfolio_allocator import build_allocation_plan

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["macro"])

_SENTINEL_BASE = os.getenv("SENTINEL_URL", "http://localhost:8004").rstrip("/")
_VALID_HORIZONS = {"short", "medium", "long"}
_HORIZON_WINDOWS = {"short": 7, "medium": 30, "long": 90}

# Hardcoded fallback snapshot — used only when live sources fail
_FALLBACK_METRICS: dict[str, float | str] = {
    "dxy": 98.5,
    "vix": 22.0,
    "us10y": 4.25,
    "brent": 92.0,
    "xau": 4800.0,
    "btc_d": 59.8,
    "usdt_d": 7.5,
    "hg": 4.5,
    "event_risk_score": 0.25,
    "hours_to_event": 48,
    "regime": "NORMALIZATION",
}

# Market fields come from yfinance/CoinGecko; event/regime fields from Sentinel
_MARKET_FIELDS: tuple[str, ...] = ("dxy", "vix", "us10y", "brent", "xau", "hg", "btc_d", "usdt_d")
_SENTINEL_FIELDS: tuple[str, ...] = ("event_risk_score", "hours_to_event", "regime")
_ALL_FIELDS: tuple[str, ...] = _MARKET_FIELDS + _SENTINEL_FIELDS


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_timestamp(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _build_data_status(fallback_fields: list[str]) -> str:
    if not fallback_fields:
        return "LIVE"
    if len(fallback_fields) == len(_ALL_FIELDS):
        return "FALLBACK"
    return "PARTIAL_FALLBACK"


@router.get("/macro")
async def get_macro_metrics(
    horizon: str = Query("medium", description="Investment horizon: short | medium | long"),
) -> dict:
    """Canonical macro endpoint with per-field data provenance."""
    if horizon not in _VALID_HORIZONS:
        horizon = "medium"
    commentary_window_days = _HORIZON_WINDOWS[horizon]

    # ── 1. Real market data (yfinance + CoinGecko, cached 60s) ───────────────
    market_results = await fetch_market_data()

    # ── 2. Sentinel for event risk + regime ──────────────────────────────────
    sentinel_data: dict = {}
    sentinel_timestamp: str | None = None
    sentinel_ok = False
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(
                f"{_SENTINEL_BASE}/sentinel/event_risk",
                params={"symbol": "BTC", "horizon": horizon},
            )
            resp.raise_for_status()
            raw = resp.json()
            sentinel_data = raw if isinstance(raw, dict) else {}
            sentinel_timestamp = _clean_timestamp(sentinel_data.get("timestamp"))
            sentinel_ok = True
    except Exception as exc:
        logger.warning("sentinel_unavailable: %s", exc)

    # ── 3. Build per-field metrics and metadata ───────────────────────────────
    metrics: dict[str, object] = {}
    field_sources: dict[str, dict] = {}
    fallback_fields: list[str] = []
    warnings: list[str] = []

    for field in _MARKET_FIELDS:
        result = market_results.get(field, {})
        if result and not result.get("fallback_used", True):
            metrics[field] = result["value"]
            field_sources[field] = {
                "source": result["source"],
                "verified": True,
                "fallback_used": False,
                "timestamp": result.get("timestamp"),
            }
        else:
            metrics[field] = _FALLBACK_METRICS[field]
            fallback_fields.append(field)
            reason = result.get("fallback_reason", "unavailable") if result else "no_result"
            field_sources[field] = {
                "source": "hardcoded_fallback",
                "verified": False,
                "fallback_used": True,
                "timestamp": None,
                "fallback_reason": reason,
            }
            warnings.append(f"{field}: hardcoded fallback ({reason})")

    sentinel_snap = sentinel_data.get("macro_snapshot", {})
    if not isinstance(sentinel_snap, dict):
        sentinel_snap = {}

    # Derive regime from regime_probability_distribution if not explicit
    def _derive_regime(sd: dict) -> str | None:
        rpd = sd.get("regime_probability_distribution", {})
        if not isinstance(rpd, dict) or not rpd:
            return None
        label_map = {
            "risk_on": "RISK_ON",
            "normalization": "NORMALIZATION",
            "risk_off": "RISK_OFF",
            "accumulation": "ACCUMULATION",
        }
        best = max(rpd.items(), key=lambda kv: float(kv[1]) if isinstance(kv[1], (int, float)) else 0.0)
        return label_map.get(best[0], str(best[0]).upper())

    for field in _SENTINEL_FIELDS:
        raw_val = sentinel_data.get(field, sentinel_snap.get(field))

        # Special case: derive regime from probability distribution when not explicit
        if field == "regime" and raw_val is None and sentinel_ok:
            raw_val = _derive_regime(sentinel_data)

        if sentinel_ok and raw_val is not None:
            metrics[field] = raw_val
            source_tag = (
                "sentinel-ai:regime_probability_distribution"
                if field == "regime" and sentinel_data.get("regime") is None
                else "sentinel-ai"
            )
            field_sources[field] = {
                "source": source_tag,
                "verified": bool(sentinel_timestamp),
                "fallback_used": False,
                "timestamp": sentinel_timestamp,
            }
        else:
            metrics[field] = _FALLBACK_METRICS[field]
            fallback_fields.append(field)
            field_sources[field] = {
                "source": "hardcoded_fallback",
                "verified": False,
                "fallback_used": True,
                "timestamp": None,
                "fallback_reason": "sentinel_unavailable",
            }
            warnings.append(f"{field}: hardcoded fallback (sentinel_unavailable)")

    # ── 4. Aggregate status ───────────────────────────────────────────────────
    data_status = _build_data_status(fallback_fields)
    verified = data_status == "LIVE"
    live = verified
    verified_fields = [f for f in _ALL_FIELDS if not field_sources[f]["fallback_used"]]

    regime = str(metrics.get("regime", "NORMALIZATION")).upper()

    # ── 5. Allocation plan ────────────────────────────────────────────────────
    allocation_plan = build_allocation_plan(
        horizon=horizon,
        regime=regime,
        metrics={k: v for k, v in metrics.items()},
        data_status=data_status,
        verified=verified,
    )

    # ── 6. Aggregate warning ──────────────────────────────────────────────────
    if data_status == "FALLBACK":
        aggregate_warning: str | None = (
            "All macro data is hardcoded fallback — no live market sources available."
        )
    elif data_status == "PARTIAL_FALLBACK":
        aggregate_warning = (
            f"Partial fallback: {len(fallback_fields)} of {len(_ALL_FIELDS)} fields are "
            f"hardcoded. Verified fields: {', '.join(sorted(verified_fields)) or 'none'}."
        )
    else:
        aggregate_warning = None

    return {
        # Status block
        "status": "ok" if data_status == "LIVE" else "degraded",
        "data_status": data_status,
        "verified": verified,
        "live": live,
        "fallback": len(fallback_fields) > 0,
        "fallback_used": len(fallback_fields) > 0,
        "fallback_fields": sorted(fallback_fields),
        "verified_fields": sorted(verified_fields),
        "sentinel_available": sentinel_ok,
        # Timestamps
        "timestamp": _now_iso(),
        "last_updated": _now_iso(),
        # Source
        "source": (
            "market_data_live" if data_status == "LIVE"
            else "market_data_partial_plus_fallback" if data_status == "PARTIAL_FALLBACK"
            else "all_hardcoded_fallback"
        ),
        # Core data
        "metrics": {k: v for k, v in metrics.items() if k in _FALLBACK_METRICS},
        "regime": regime,
        # field_sources as simple {field: source_string} for frontend compatibility (apiV2.ts)
        "field_sources": {f: v["source"] for f, v in field_sources.items()},
        # field_provenance carries full per-field metadata (canonical contract)
        "field_provenance": field_sources,
        # Allocation
        "allocation_target": allocation_plan["weights"],
        "allocation_horizon": allocation_plan["allocation_horizon"],
        "allocation_profile": allocation_plan["allocation_profile"],
        "allocation_basis": allocation_plan["allocation_basis"],
        "hedge": allocation_plan["hedge_on"],
        "horizon_adjustments": allocation_plan["horizon_adjustments"],
        # Warnings
        "warning": aggregate_warning,
        "warnings": allocation_plan["warnings"] + warnings,
        # Horizon
        "horizon_applied": horizon,
        "commentary_window_days": commentary_window_days,
        # Sentinel passthrough
        "regime_probability_distribution": sentinel_data.get("regime_probability_distribution", {}),
        "liquidity_composite": sentinel_data.get("liquidity_composite"),
        "volatility_composite": sentinel_data.get("volatility_composite"),
    }


@router.get("/metrics/sentinel/macro")
async def get_macro_metrics_legacy_alias(
    horizon: str = Query("medium", description="Investment horizon: short | medium | long"),
) -> dict:
    """Legacy alias — delegates to canonical /api/macro."""
    return await get_macro_metrics(horizon=horizon)


@router.get("/risk/profiles")
async def get_risk_profiles() -> dict:
    """Return available risk presets for the UI."""
    return {
        "presets": {
            "conservative": {
                "kelly_cap": 0.15, "sl_pct": 1.5, "tp_pct": 3.0,
                "max_dd": 3.0, "description": "Sermaye koruma odaklı",
            },
            "moderate": {
                "kelly_cap": 0.25, "sl_pct": 2.0, "tp_pct": 4.0,
                "max_dd": 5.0, "description": "Dengeli risk/getiri",
            },
            "aggressive": {
                "kelly_cap": 0.35, "sl_pct": 3.0, "tp_pct": 6.0,
                "max_dd": 8.0, "description": "Yüksek volatilite toleransı",
            },
        },
        "current_profile": "moderate",
    }


@router.post("/simulator")
async def run_macro_simulator(scenario: dict) -> dict:
    """Forward to Sentinel simulate; local fallback if unavailable."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{_SENTINEL_BASE}/sentinel/simulate", json=scenario)
            resp.raise_for_status()
            return resp.json()
    except Exception:
        logger.warning("Sentinel simulate unavailable — local fallback")
        dxy = float(scenario.get("dxy", 100))
        vix = float(scenario.get("vix", 20))
        us10y = float(scenario.get("us10y", 4.0))
        m2sl = float(scenario.get("m2sl", 20))
        risk_on = max(0.0, 0.25 + (m2sl - 20) * 0.02 - (dxy - 100) * 0.01)
        risk_off = max(0.0, 0.25 + (vix - 20) * 0.015 + (us10y - 4) * 0.03)
        norm = max(0.0, 1.0 - risk_on - risk_off - 0.2)
        accum = 0.2
        total = risk_on + risk_off + norm + accum or 1.0
        return {
            "regime_probability_distribution": {
                "risk_on": round(risk_on / total, 3),
                "normalization": round(norm / total, 3),
                "risk_off": round(risk_off / total, 3),
                "accumulation": round(accum / total, 3),
            },
            "liquidity_composite": {
                "liquidity_composite_score": round(min(100.0, max(0.0, m2sl * 3 + 30)), 1),
                "interpretation": "High" if m2sl > 23 else "Medium" if m2sl > 18 else "Low",
            },
            "volatility_composite": {
                "volatility_composite": round(min(100.0, vix * 2.5), 1),
                "regime_signal": (
                    "HIGH_VOL" if vix > 25 else "LOW_VOL" if vix < 15 else "NORMAL_VOL"
                ),
            },
        }
