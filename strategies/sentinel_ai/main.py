"""
AEGIS v7.4 - Sentinel API live macro data with explicit fallback metadata.

Sentinel AI Limited - Macro-Economic Risk Analysis API
"""
from fastapi import FastAPI, Response
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import asyncio
import logging
import math
import random
import numpy as np
import pandas as pd
import threading
import time
import os
import httpx
from dotenv import load_dotenv

from correlation_engine import CorrelationEngine

try:
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from determinism_control import DeterministicSeedManager, GLOBAL_SEED

    DeterministicSeedManager.initialize(GLOBAL_SEED, verbose=False)
except Exception:
    random.seed(42)
    if "np" in dir():
        np.random.seed(42)

load_dotenv()

from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Counter, Gauge, Histogram

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()
TWELVE_DATA_BASE_URL = os.getenv("TWELVE_DATA_BASE_URL", "https://api.twelvedata.com").rstrip("/")

corr_engine = CorrelationEngine(window=30, min_periods=20)

SENTINEL_DXY_THRESHOLD = float(os.getenv("SENTINEL_DXY_THRESHOLD", "104"))
SENTINEL_VIX_THRESHOLD = float(os.getenv("SENTINEL_VIX_THRESHOLD", "20"))
SENTINEL_US10Y_THRESHOLD = float(os.getenv("SENTINEL_US10Y_THRESHOLD", "4.5"))
SENTINEL_BRENT_THRESHOLD = float(os.getenv("SENTINEL_BRENT_THRESHOLD", "95"))
SENTINEL_XAU_THRESHOLD = float(os.getenv("SENTINEL_XAU_THRESHOLD", "4800"))

if TWELVE_DATA_API_KEY:
    logger.info("[SENTINEL] LIVE MODE - Twelve Data macro feed active")
else:
    logger.info("[SENTINEL] FALLBACK MODE - explicit fallback snapshot active")

REQUEST_COUNT = Counter("sentinel_requests_total", "Total requests", ["method", "endpoint"])
REQUEST_LATENCY = Histogram("sentinel_request_duration_seconds", "Request latency (seconds)", ["endpoint"])
ACTIVE_REQUESTS = Gauge("sentinel_active_requests", "Active requests")
RISK_ASSESSMENT = Gauge("sentinel_risk_assessment", "Overall risk assessment")
MULTIPLIER = Gauge("sentinel_multiplier", "Risk multiplier")
MARKET_REGIME = Gauge("sentinel_market_regime", "Current market regime")

_metric_values = {
    "sentinel_multiplier": None,
    "sentinel_risk_assessment": None,
    "timestamp": None,
    "source": "uninitialized",
    "verified": False,
    "data_status": "UNKNOWN",
    "warning": "No macro snapshot fetched yet.",
}

_FALLBACK_MACRO = {
    "dxy": 98.5,
    "vix": 22.0,
    "us10y": 4.25,
    "brent": 92.0,
    "xau": 4800.0,
}


def _service_mode() -> str:
    if _metric_values.get("data_status") == "LIVE":
        return "REAL"
    if _metric_values.get("data_status") == "RECENT":
        return "CACHE_REAL"
    if _metric_values.get("data_status") in {"PARTIAL_FALLBACK", "FALLBACK"}:
        return "FALLBACK"
    return "UNAVAILABLE"


def _latest_timestamp(values: list[str | None]) -> str | None:
    valid = [value for value in values if isinstance(value, str) and value.strip()]
    if not valid:
        return None
    return max(valid, key=lambda item: datetime.fromisoformat(item.replace("Z", "+00:00")))


def _fallback_snapshot(reason: str, *, cached: bool = False) -> dict:
    field_sources = {
        field: {
            "source": "hardcoded_fallback",
            "timestamp": None,
            "verified": False,
            "fallback_used": True,
        }
        for field in _FALLBACK_MACRO
    }
    return {
        **_FALLBACK_MACRO,
        "source": "fallback_cache" if cached else "fallback",
        "timestamp": None,
        "field_sources": field_sources,
        "fallback_fields": sorted(_FALLBACK_MACRO.keys()),
        "verified": False,
        "fallback_used": True,
        "data_status": "FALLBACK",
        "warnings": [reason],
        "cached": cached,
    }


async def _refresh_metric_snapshot() -> None:
    macro = await _get_macro_snapshot()
    risk_score = _compute_event_risk(macro)
    multiplier_value = round(max(0.1, min(1.0, 1.0 - risk_score)), 3)
    regime_probs = _compute_regime_probabilities(macro)
    max_regime = max(regime_probs, key=lambda key: regime_probs[key]) if regime_probs else "normalization"
    regime_value = 2 if max_regime == "risk_off" else 0 if max_regime == "risk_on" else 1

    _metric_values.update(
        {
            "sentinel_multiplier": multiplier_value,
            "sentinel_risk_assessment": round(risk_score * 100.0, 2),
            "timestamp": macro.get("timestamp"),
            "source": macro.get("source", "fallback"),
            "verified": bool(macro.get("verified")),
            "data_status": macro.get("data_status", "UNKNOWN"),
            "warning": " ".join(macro.get("warnings", [])) or None,
        }
    )

    MULTIPLIER.set(multiplier_value)
    RISK_ASSESSMENT.set(float(_metric_values["sentinel_risk_assessment"]))
    MARKET_REGIME.set(regime_value)


def update_metrics_background():
    while True:
        try:
            asyncio.run(_refresh_metric_snapshot())
            time.sleep(30)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error updating Sentinel metrics: %s", exc)
            time.sleep(30)


def _emit_metric_lines() -> str:
    mode = _service_mode()
    return "\n".join(
        [
            "# HELP sentinel_mode Operating mode (REAL, CACHE_REAL, FALLBACK, UNAVAILABLE)",
            "# TYPE sentinel_mode gauge",
            f'sentinel_mode{{mode="{mode}"}} 1',
            "# HELP sentinel_data_available Whether a macro snapshot is available",
            "# TYPE sentinel_data_available gauge",
            f"sentinel_data_available {1 if _metric_values.get('sentinel_multiplier') is not None else 0}",
        ]
    ) + "\n"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Sentinel AI Module starting up...")
    thread = threading.Thread(target=update_metrics_background, daemon=True)
    thread.start()
    yield
    logger.info("Sentinel AI Module shutting down...")


app = FastAPI(
    title="Sentinel AI Limited",
    description="Macro-Economic Risk Analysis Engine",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "sentinel-ai",
        "version": "1.0.0",
        "data_mode": _service_mode(),
        "metric_source": _metric_values.get("source"),
        "metric_timestamp": _metric_values.get("timestamp"),
        "verified": bool(_metric_values.get("verified")),
        "data_status": _metric_values.get("data_status"),
    }


@app.get("/metrics")
async def metrics():
    base_metrics = generate_latest().decode()
    if _metric_values.get("timestamp") is None and _metric_values.get("data_status") == "UNKNOWN":
        await _refresh_metric_snapshot()
    return Response(content=base_metrics + _emit_metric_lines(), media_type=CONTENT_TYPE_LATEST)


@app.get("/")
async def root():
    return {
        "service": "Sentinel AI Limited",
        "description": "Macro-Economic Risk Analysis",
        "endpoints": {
            "health": "/health",
            "metrics": "/metrics",
            "docs": "/docs",
        },
    }


@app.get("/sentinel/event_risk")
async def get_event_risk(symbol: str = "BTC", horizon: str = "medium"):
    horizon_hours = {"short": 24, "medium": 48, "long": 72}
    hours_to_event = horizon_hours.get(horizon, 48)

    macro = await _get_macro_snapshot()
    risk_score = _compute_event_risk(macro)
    regime_probs = _compute_regime_probabilities(macro)
    liquidity = _compute_liquidity_score(macro)
    volatility = _compute_volatility_composite(macro)

    return {
        "symbol": symbol,
        "event_risk_score": risk_score,
        "hours_to_event": hours_to_event,
        "horizon_applied": horizon,
        "macro_snapshot": macro,
        "is_low_risk": bool(risk_score <= 0.4 or hours_to_event >= 48),
        "regime_probability_distribution": regime_probs,
        "liquidity_composite": liquidity,
        "volatility_composite": volatility,
        "timestamp": macro.get("timestamp"),
        "source": macro.get("source", "fallback"),
        "verified": bool(macro.get("verified")),
        "fallback_used": bool(macro.get("fallback_used")),
        "data_status": macro.get("data_status", "UNKNOWN"),
        "warnings": macro.get("warnings", []),
    }


@app.get("/sentinel/sentiment")
async def get_sentiment(symbol: str = "BTC"):
    macro = await _get_macro_snapshot()
    score = round(max(0.0, min(1.0, 1.0 - _compute_event_risk(macro))), 3)
    label = "bullish" if score > 0.6 else "bearish" if score < 0.4 else "neutral"
    return {
        "symbol": symbol,
        "sentiment": label,
        "score": score,
        "source": macro.get("source", "fallback"),
        "timestamp": macro.get("timestamp"),
        "verified": bool(macro.get("verified")),
        "data_status": macro.get("data_status", "UNKNOWN"),
    }


@app.get("/sentinel/analyze")
async def analyze(symbol: str = "BTC", horizon: str = "medium"):
    event = await get_event_risk(symbol=symbol, horizon=horizon)
    confidence = round(max(0.5, min(0.95, 1.0 - event["event_risk_score"] / 2)), 3)
    return {
        "symbol": symbol,
        "horizon": horizon,
        "analysis": "macro_risk_derived",
        "confidence": confidence,
        "event_risk_score": event["event_risk_score"],
        "timestamp": event.get("timestamp"),
        "source": event.get("source"),
        "verified": event.get("verified", False),
        "data_status": event.get("data_status", "UNKNOWN"),
    }


@app.get("/sentinel/correlation")
async def get_correlation():
    macro = await _get_macro_snapshot()
    price_df = _build_macro_price_df(macro)
    return corr_engine.analyze(price_df)


@app.get("/sentinel/macro")
async def get_macro(horizon: str = "medium"):
    macro = await _get_macro_snapshot()
    risk = _compute_event_risk(macro)
    regime = "RISK_OFF" if risk > 0.65 else "NORMALIZATION" if risk > 0.35 else "LIQUIDITY_EXPANSION"
    corr_data = corr_engine.analyze(_build_macro_price_df(macro))

    return {
        "horizon": horizon,
        "regime": regime,
        "fallback": bool(macro.get("fallback_used")),
        "metrics": macro,
        "correlation": corr_data,
        "regime_probability_distribution": _compute_regime_probabilities(macro),
        "liquidity_composite": _compute_liquidity_score(macro),
        "volatility_composite": _compute_volatility_composite(macro),
        "timestamp": macro.get("timestamp"),
        "source": macro.get("source", "fallback"),
        "verified": bool(macro.get("verified")),
        "data_status": macro.get("data_status", "UNKNOWN"),
        "warnings": macro.get("warnings", []),
    }


async def _get_macro_snapshot() -> dict:
    """Fetch current macro snapshot from Twelve Data with explicit fallback metadata."""
    if not TWELVE_DATA_API_KEY:
        return _fallback_snapshot("twelve_data_api_key_missing")

    now = time.time()
    if hasattr(_get_macro_snapshot, "_cache") and _get_macro_snapshot._cache:
        cached_at, cached_data = _get_macro_snapshot._cache
        if now - cached_at < 900:
            cached_copy = dict(cached_data)
            cached_copy["cached"] = True
            if cached_copy.get("verified"):
                cached_copy["data_status"] = "RECENT"
            return cached_copy

    symbol_map = {
        "dxy": "DXY",
        "vix": "VIX",
        "us10y": "US10Y",
        "brent": "BRENT",
        "xau": "XAU/USD",
    }

    values: dict[str, object] = {}
    field_sources: dict[str, dict[str, object]] = {}
    fallback_fields: list[str] = []
    warnings: list[str] = []
    timestamps: list[str | None] = []

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            for field, symbol in symbol_map.items():
                try:
                    response = await client.get(
                        f"{TWELVE_DATA_BASE_URL}/price",
                        params={"symbol": symbol, "apikey": TWELVE_DATA_API_KEY},
                    )
                    response.raise_for_status()
                    payload = response.json() if isinstance(response.json(), dict) else {}
                    if payload.get("status") == "error" or payload.get("code") in (400, 401, 403, 429):
                        raise RuntimeError(str(payload.get("message", "provider_error")))

                    values[field] = float(payload.get("price", _FALLBACK_MACRO[field]))
                    field_timestamp = payload.get("datetime")
                    timestamps.append(field_timestamp)
                    field_sources[field] = {
                        "source": "twelve_data",
                        "timestamp": field_timestamp,
                        "verified": True,
                        "fallback_used": False,
                    }
                except Exception as exc:  # noqa: BLE001
                    values[field] = _FALLBACK_MACRO[field]
                    fallback_fields.append(field)
                    warnings.append(f"{field}: {exc}")
                    field_sources[field] = {
                        "source": "hardcoded_fallback",
                        "timestamp": None,
                        "verified": False,
                        "fallback_used": True,
                    }
    except Exception as exc:  # noqa: BLE001
        logger.warning("[SENTINEL] Twelve Data fetch failed: %s", exc)
        fallback = _fallback_snapshot(f"twelve_data_exception:{exc}")
        _get_macro_snapshot._cache = (now, fallback)
        return fallback

    timestamp = _latest_timestamp(timestamps)
    data_status = "LIVE" if not fallback_fields else "PARTIAL_FALLBACK"
    snapshot = {
        **values,
        "source": "twelve_data" if data_status == "LIVE" else "twelve_data_partial_fallback",
        "timestamp": timestamp,
        "field_sources": field_sources,
        "fallback_fields": sorted(fallback_fields),
        "verified": data_status == "LIVE",
        "fallback_used": bool(fallback_fields),
        "data_status": data_status,
        "warnings": warnings,
        "cached": False,
    }
    _get_macro_snapshot._cache = (now, snapshot)
    return snapshot


def _build_macro_price_df(macro: dict) -> pd.DataFrame:
    """Build a deterministic rolling window from the current macro snapshot."""
    row = {
        "BTCUSD": 85000.0,
        "BTC.D": 59.5,
        "TOTAL": 2800.0,
        "TOTAL2": 1200.0,
        "DXY": float(macro.get("dxy", 98.5)),
        "XAUUSD": float(macro.get("xau", 4800.0)),
        "XAGUSD": 32.0,
        "XAUXAG": 150.0,
        "BRENT": float(macro.get("brent", 92.0)),
        "US02Y": 4.95,
        "US10Y": float(macro.get("us10y", 4.35)),
        "US20Y": 4.70,
        "USCPI": 3.2,
        "USPPI": 2.1,
        "M2SL": 21000.0,
        "SP500": 5200.0,
        "NASDAQ": 16400.0,
        "QQQ": 440.0,
        "FXI": 28.0,
        "HYG": 78.0,
        "JNK": 95.0,
        "000001": 3100.0,
        "BTCXAU": 37.0,
    }
    rows = []
    for step in range(35):
        factor = 1 - ((35 - step) * 0.0008)
        rows.append({key: value * factor for key, value in row.items()})
    rows.append(row)
    return pd.DataFrame(rows)


def _compute_event_risk(macro: dict) -> float:
    components = [
        float(macro.get("dxy", SENTINEL_DXY_THRESHOLD)) / SENTINEL_DXY_THRESHOLD,
        float(macro.get("vix", SENTINEL_VIX_THRESHOLD)) / SENTINEL_VIX_THRESHOLD,
        float(macro.get("us10y", SENTINEL_US10Y_THRESHOLD)) / SENTINEL_US10Y_THRESHOLD,
        float(macro.get("brent", SENTINEL_BRENT_THRESHOLD)) / SENTINEL_BRENT_THRESHOLD,
        float(macro.get("xau", SENTINEL_XAU_THRESHOLD)) / SENTINEL_XAU_THRESHOLD,
    ]
    score = sum(components) / len(components)
    return round(max(0.0, min(1.0, score - 0.6)), 3)


def _compute_regime_probabilities(macro: dict) -> dict:
    dxy = float(macro.get("dxy", 99))
    us10y = float(macro.get("us10y", 4.25))
    vix = float(macro.get("vix", 22))
    xau = float(macro.get("xau", 4800))

    scores = {"risk_on": 0.0, "normalization": 0.0, "risk_off": 0.0, "accumulation": 0.0}
    scores["risk_on"] += max(0, (102 - dxy) * 0.03)
    scores["risk_on"] += max(0, (4.5 - us10y) * 0.12)
    scores["risk_on"] += max(0, (22 - vix) * 0.02)
    scores["risk_off"] += max(0, (dxy - 100) * 0.025)
    scores["risk_off"] += max(0, (us10y - 4.0) * 0.10)
    scores["risk_off"] += max(0, (vix - 20) * 0.025)
    scores["risk_off"] += max(0, (xau - 4500) * 0.00005)

    if 96 <= dxy <= 103 and 3.5 <= us10y <= 5.0 and vix < 25:
        scores["normalization"] = 0.35
    if vix < 20 and us10y < 4.5 and dxy < 101:
        scores["accumulation"] = 0.30

    exp_scores = {k: math.exp(min(v, 10)) for k, v in scores.items()}
    total = sum(exp_scores.values())
    if total == 0:
        return {"risk_on": 0.25, "normalization": 0.25, "risk_off": 0.25, "accumulation": 0.25}
    return {k: round(v / total, 3) for k, v in exp_scores.items()}


def _compute_liquidity_score(macro: dict) -> dict:
    m2sl_score = min(100, max(0, (float(macro.get("m2sl", 21)) - 10) * 5))
    rrp_score = min(100, max(0, 100 - (float(macro.get("rrp", 500)) / 30)))
    cb_score = min(100, max(0, float(macro.get("cb_balance", 8000)) / 100))
    funding = float(macro.get("funding_rate", 0))
    funding_score = min(100, max(0, 50 - funding * 1000))
    composite = m2sl_score * 0.35 + rrp_score * 0.25 + cb_score * 0.25 + funding_score * 0.15

    return {
        "liquidity_composite_score": round(composite, 1),
        "components": {
            "m2sl": round(m2sl_score, 1),
            "rrp": round(rrp_score, 1),
            "cb_balance_sheet": round(cb_score, 1),
            "funding_rate_impact": round(funding_score, 1),
        },
        "interpretation": "High" if composite > 70 else "Medium" if composite > 40 else "Low",
    }


def simulate_macro_scenario(dxy=100, vix=20, us10y=4.0, m2sl=20, brent=90, xau=4800):
    macro = {"dxy": dxy, "vix": vix, "us10y": us10y, "m2sl": m2sl, "brent": brent, "xau": xau}
    return {
        "regime_probability_distribution": _compute_regime_probabilities(macro),
        "liquidity_composite": _compute_liquidity_score(macro),
        "volatility_composite": _compute_volatility_composite(macro),
    }


def _compute_volatility_composite(macro: dict) -> dict:
    vix = float(macro.get("vix", 22))
    move = float(macro.get("move", 100))
    cvix = float(macro.get("cvix", 60))
    vix_norm = min(100, max(0, (vix - 10) * 2.5))
    move_norm = min(100, max(0, (move - 50) * 1.5))
    cvix_norm = min(100, max(0, (cvix - 30) * 1.25))
    composite = vix_norm * 0.30 + move_norm * 0.25 + cvix_norm * 0.45

    return {
        "volatility_composite": round(composite, 1),
        "components": {
            "vix": round(vix_norm, 1),
            "move_bond_vol": round(move_norm, 1),
            "cvix_crypto_vol": round(cvix_norm, 1),
        },
        "regime_signal": "HIGH_VOL" if composite > 60 else "LOW_VOL" if composite < 30 else "NORMAL_VOL",
    }


@app.post("/sentinel/simulate")
async def run_simulation(scenario: dict):
    return simulate_macro_scenario(
        dxy=scenario.get("dxy", 100),
        vix=scenario.get("vix", 20),
        us10y=scenario.get("us10y", 4.0),
        m2sl=scenario.get("m2sl", 20),
        brent=scenario.get("brent", 90),
        xau=scenario.get("xau", 4800),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8004)
