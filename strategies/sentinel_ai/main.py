"""
AEGIS v7.4 — Sentinel API canli makro veri/fallback ve endpoint tamamlama.

Sentinel AI Limited - Macro-Economic Risk Analysis API
"""
from fastapi import FastAPI, Response
from contextlib import asynccontextmanager
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
except:
    random.seed(42)
    if "np" in dir(): np.random.seed(42)

# Load environment variables from .env
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

# ============ MACRO INDICATORS DATA SOURCES ============
if TWELVE_DATA_API_KEY:
    logger.info("✅ [SENTINEL] LIVE MODE - Twelve Data macro feed aktif")
else:
    logger.info("ℹ️  [SENTINEL] FALLBACK MODE - deterministic test verisi aktif")

# Prometheus metrics
REQUEST_COUNT = Counter('sentinel_requests_total', 'Total requests', ['method', 'endpoint'])
REQUEST_LATENCY = Histogram('sentinel_request_duration_seconds', 'Request latency (seconds)', ['endpoint'])
ACTIVE_REQUESTS = Gauge('sentinel_active_requests', 'Active requests')
RISK_ASSESSMENT = Gauge('sentinel_risk_assessment', 'Overall risk assessment')
MULTIPLIER = Gauge('sentinel_multiplier', 'Risk multiplier')
MARKET_REGIME = Gauge('sentinel_market_regime', 'Current market regime')

# Store metric values
_metric_values = {
    'sentinel_multiplier': random.uniform(0.1, 1.0),
    'sentinel_risk_assessment': random.uniform(0, 100),
}

def update_metrics_background():
    """Background thread to update metrics every 10 seconds"""
    while True:
        try:
            multiplier_value = random.uniform(0.1, 1.0)
            risk_value = random.uniform(0, 100)
            regime_value = random.randint(0, 2)  # 0=Bull, 1=Neutral, 2=Bear

            # Update gauge objects (this is what Prometheus scrapes!)
            MULTIPLIER.set(multiplier_value)
            RISK_ASSESSMENT.set(risk_value)
            MARKET_REGIME.set(regime_value)

            # Also update cache
            _metric_values['sentinel_multiplier'] = multiplier_value
            _metric_values['sentinel_risk_assessment'] = risk_value

            logger.info(f"Updated metrics: Multiplier={multiplier_value:.2f}, Risk={risk_value:.1f}, Regime={regime_value}")
            time.sleep(10)
        except Exception as e:
            logger.error(f"Error updating metrics: {e}")
            time.sleep(10)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown"""
    logger.info("Sentinel AI Module starting up...")

    # Start background thread
    thread = threading.Thread(target=update_metrics_background, daemon=True)
    thread.start()

    yield

    logger.info("Sentinel AI Module shutting down...")

app = FastAPI(
    title="Sentinel AI Limited",
    description="Macro-Economic Risk Analysis Engine",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "sentinel-ai",
        "version": "1.0.0"
    }

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    # Get standard metrics (registered Gauge/Counter/Histogram values)
    base_metrics = generate_latest().decode()

    # Add only mode marker; avoid duplicating already-registered metric names.
    custom_metrics = (
        f"# HELP sentinel_mode Operating mode (FALLBACK public endpoints)\n"
        f"# TYPE sentinel_mode gauge\n"
        f"sentinel_mode{{mode=\"FALLBACK\"}} 1\n"
    )

    return Response(content=base_metrics + custom_metrics, media_type=CONTENT_TYPE_LATEST)

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Sentinel AI Limited",
        "description": "Macro-Economic Risk Analysis",
        "endpoints": {
            "health": "/health",
            "metrics": "/metrics",
            "docs": "/docs"
        }
    }


@app.get("/sentinel/event_risk")
async def get_event_risk(symbol: str = "BTC", horizon: str = "medium"):
    """Protocol endpoint: News AI -> Sentinel event shock risk."""
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
    }


@app.get("/sentinel/sentiment")
async def get_sentiment(symbol: str = "BTC"):
    """AEGIS v7.2 — Dashboard uyumlulugu icin sentiment endpoint'i."""
    macro = await _get_macro_snapshot()
    score = round(max(0.0, min(1.0, 1.0 - _compute_event_risk(macro))), 3)
    label = "bullish" if score > 0.6 else "bearish" if score < 0.4 else "neutral"
    return {"symbol": symbol, "sentiment": label, "score": score, "source": macro.get("source", "fallback")}


@app.get("/sentinel/analyze")
async def analyze(symbol: str = "BTC", horizon: str = "medium"):
    """AEGIS v7.2 — Dashboard uyumlulugu icin analiz endpoint'i."""
    event = await get_event_risk(symbol=symbol, horizon=horizon)
    confidence = round(max(0.5, min(0.95, 1.0 - event["event_risk_score"] / 2)), 3)
    return {
        "symbol": symbol,
        "horizon": horizon,
        "analysis": "macro_risk_derived",
        "confidence": confidence,
        "event_risk_score": event["event_risk_score"],
    }


@app.get("/sentinel/correlation")
async def get_correlation():
    """AEGIS v7.2 — Macro correlation analysis endpoint."""
    macro = await _get_macro_snapshot()
    price_df = _build_macro_price_df(macro)
    result = corr_engine.analyze(price_df)
    return result


@app.get("/sentinel/macro")
async def get_macro(horizon: str = "medium"):
    """AEGIS v7.4 — Dashboard uyumlulugu icin macro endpoint'i."""
    macro = await _get_macro_snapshot()
    risk = _compute_event_risk(macro)
    regime = "RISK_OFF" if risk > 0.65 else "NORMALIZATION" if risk > 0.35 else "LIQUIDITY_EXPANSION"

    # Correlation analysis
    price_df = _build_macro_price_df(macro)
    corr_data = corr_engine.analyze(price_df)

    return {
        "horizon": horizon,
        "regime": regime,
        "fallback": macro.get("source") != "twelve_data",
        "metrics": macro,
        "correlation": corr_data,
        "regime_probability_distribution": _compute_regime_probabilities(macro),
        "liquidity_composite": _compute_liquidity_score(macro),
        "volatility_composite": _compute_volatility_composite(macro),
    }


async def _get_macro_snapshot() -> dict:
    """AEGIS v7.2 — Twelve Data'dan makro snapshot ceker, hata durumunda fallback doner.
    Caches results for 5 minutes to avoid exhausting TwelveData free-tier API credits."""
    fallback = {
        "source": "fallback",
        "dxy": 98.5,
        "vix": 22.0,
        "us10y": 4.25,
        "brent": 92.0,
        "xau": 4800.0,
    }
    if not TWELVE_DATA_API_KEY:
        return fallback

    # ---- In-memory cache (5-minute TTL) ----
    now = time.time()
    if hasattr(_get_macro_snapshot, "_cache") and _get_macro_snapshot._cache:
        cached_at, cached_data = _get_macro_snapshot._cache
        if now - cached_at < 900:  # 15 minutes — 480 credits/day stays within free tier (800)
            return cached_data

    symbols = {
        "dxy": "DXY",
        "vix": "VIX",
        "us10y": "US10Y",
        "brent": "BRENT",
        "xau": "XAU/USD",
    }
    values = {"source": "twelve_data"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            for key, symbol in symbols.items():
                resp = await client.get(
                    f"{TWELVE_DATA_BASE_URL}/price",
                    params={"symbol": symbol, "apikey": TWELVE_DATA_API_KEY},
                )
                resp.raise_for_status()
                data = resp.json() if isinstance(resp.json(), dict) else {}
                # TwelveData returns {"code": 429, "status": "error"} on rate limit
                if data.get("status") == "error" or data.get("code") in (400, 401, 403, 429):
                    logger.warning("[SENTINEL] TwelveData error for %s: %s", symbol, data.get("message", "unknown"))
                    values[key] = fallback[key]
                    values["source"] = "partial_fallback"
                else:
                    values[key] = float(data.get("price", fallback[key]))
        _get_macro_snapshot._cache = (now, values)
        return values
    except Exception as exc:  # noqa: BLE001
        logger.warning("[SENTINEL] Twelve Data fetch failed: %s", exc)
        return fallback


def _build_macro_price_df(macro: dict) -> pd.DataFrame:
    """Build a synthetic price DataFrame from macro snapshot for correlation engine.
    Covers all 23 MACRO_SYMBOLS from correlation_engine.
    For a real deployment, this would query historical macro data.
    Here we generate a minimal rolling window from the current snapshot."""
    try:
        row = {
            "BTCUSD": 85000.0,
            "BTC.D": 59.5,       # BTC dominance %
            "TOTAL": 2800.0,     # Total crypto market cap (B)
            "TOTAL2": 1200.0,    # Total crypto ex-BTC (B)
            "DXY": float(macro.get("dxy", 98.5)),
            "XAUUSD": float(macro.get("xau", 4800.0)),
            "XAGUSD": 32.0,
            "XAUXAG": 150.0,    # Gold/Silver ratio
            "BRENT": float(macro.get("brent", 92.0)),
            "US02Y": 4.95,
            "US10Y": float(macro.get("us10y", 4.35)),
            "US20Y": 4.70,
            "USCPI": 3.2,
            "USPPI": 2.1,
            "M2SL": 21000.0,    # M2 money supply (B)
            "SP500": 5200.0,
            "NASDAQ": 16400.0,
            "QQQ": 440.0,
            "FXI": 28.0,        # China large-cap ETF
            "HYG": 78.0,
            "JNK": 95.0,        # High-yield bond ETF
            "000001": 3100.0,   # Shanghai Composite
            "BTCXAU": 37.0,     # BTC/Gold ratio
        }
        np.random.seed(int(time.time()) % 10000)
        rows = []
        for i in range(35):
            noise = {k: v * (1 + np.random.normal(0, 0.005)) for k, v in row.items()}
            rows.append(noise)
        rows.append(row)
        return pd.DataFrame(rows)
    except Exception as e:
        logger.warning(f"Failed to build macro price df: {e}")
        return pd.DataFrame()


def _compute_event_risk(macro: dict) -> float:
    """AEGIS v7.2 — Makro esiklere gore normalize event risk hesabi."""
    components = [
        float(macro.get("dxy", SENTINEL_DXY_THRESHOLD)) / SENTINEL_DXY_THRESHOLD,
        float(macro.get("vix", SENTINEL_VIX_THRESHOLD)) / SENTINEL_VIX_THRESHOLD,
        float(macro.get("us10y", SENTINEL_US10Y_THRESHOLD)) / SENTINEL_US10Y_THRESHOLD,
        float(macro.get("brent", SENTINEL_BRENT_THRESHOLD)) / SENTINEL_BRENT_THRESHOLD,
        float(macro.get("xau", SENTINEL_XAU_THRESHOLD)) / SENTINEL_XAU_THRESHOLD,
    ]
    score = sum(components) / len(components)
    return round(max(0.0, min(1.0, score - 0.6)), 3)


# ============ REGIME PROBABILITY DISTRIBUTION (v7.4) ============

def _compute_regime_probabilities(macro: dict) -> dict:
    """Bayesian-style probability across 4 regimes based on macro indicators."""
    dxy = float(macro.get("dxy", 99))
    us10y = float(macro.get("us10y", 4.25))
    vix = float(macro.get("vix", 22))
    brent = float(macro.get("brent", 92))
    xau = float(macro.get("xau", 4800))

    scores = {"risk_on": 0.0, "normalization": 0.0, "risk_off": 0.0, "accumulation": 0.0}

    # Risk-on: weak DXY, falling yields, low VIX
    scores["risk_on"] += max(0, (102 - dxy) * 0.03)
    scores["risk_on"] += max(0, (4.5 - us10y) * 0.12)
    scores["risk_on"] += max(0, (22 - vix) * 0.02)

    # Risk-off: strong DXY, rising yields, high VIX, gold rally
    scores["risk_off"] += max(0, (dxy - 100) * 0.025)
    scores["risk_off"] += max(0, (us10y - 4.0) * 0.10)
    scores["risk_off"] += max(0, (vix - 20) * 0.025)
    scores["risk_off"] += max(0, (xau - 4500) * 0.00005)

    # Normalization: balanced macro
    if 96 <= dxy <= 103 and 3.5 <= us10y <= 5.0 and vix < 25:
        scores["normalization"] = 0.35

    # Accumulation: low vol, stable yields, moderate DXY
    if vix < 20 and us10y < 4.5 and dxy < 101:
        scores["accumulation"] = 0.30

    # Softmax normalization
    exp_scores = {k: math.exp(min(v, 10)) for k, v in scores.items()}
    total = sum(exp_scores.values())
    if total == 0:
        return {"risk_on": 0.25, "normalization": 0.25, "risk_off": 0.25, "accumulation": 0.25}
    return {k: round(v / total, 3) for k, v in exp_scores.items()}


# ============ LIQUIDITY COMPOSITE SCORE (v7.4) ============

def _compute_liquidity_score(macro: dict) -> dict:
    """M2SL + RRP + CB Balance + Funding Rate → 0-100 composite."""
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


# ============ WHAT-IF SIMULATOR (v7.5) ============

def simulate_macro_scenario(dxy=100, vix=20, us10y=4.0, m2sl=20, brent=90, xau=4800):
    """Fast-path simulator for UI sliders — no external API calls."""
    macro = {"dxy": dxy, "vix": vix, "us10y": us10y, "m2sl": m2sl, "brent": brent, "xau": xau}
    regime_probs = _compute_regime_probabilities(macro)
    liquidity = _compute_liquidity_score(macro)
    volatility = _compute_volatility_composite(macro)
    return {
        "regime_probability_distribution": regime_probs,
        "liquidity_composite": liquidity,
        "volatility_composite": volatility,
    }


# ============ VOLATILITY COMPOSITE (v7.4) ============

def _compute_volatility_composite(macro: dict) -> dict:
    """VIX + MOVE (bond vol) + CVIX (crypto vol) → weighted composite."""
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
    """What-If simulator: compute regime/liquidity/volatility from user-supplied macro values."""
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
