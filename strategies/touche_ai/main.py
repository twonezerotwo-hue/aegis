"""
Touche AI Limited - Technical Analysis API
LIVE_INTEGRATION: Binance async data fetcher with fallback.
"""
from fastapi import FastAPI, Response
from contextlib import asynccontextmanager
import logging
import random
import numpy as np
import threading
import time
import os
from datetime import timezone
from typing import Any, Optional
from dotenv import load_dotenv
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

from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, REGISTRY

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# LIVE_INTEGRATION: Import config and data fetcher
try:
    from strategies.touche_ai.config import config as touche_config
    from strategies.touche_ai.services.data_fetcher import BinanceDataFetcher
except ModuleNotFoundError:
    # Inside Docker: code is at /app/touche_ai/
    from config import config as touche_config  # type: ignore[no-redef]
    from services.data_fetcher import BinanceDataFetcher  # type: ignore[no-redef]

# LIVE_INTEGRATION: Module-level fetcher instance
_data_fetcher: Optional[BinanceDataFetcher] = None

# Legacy compat: USE_REAL_API mirrors DATA_MODE for existing code paths
USE_REAL_API = touche_config.data_mode.upper() == "LIVE"
binance_client = None  # kept for backward compat, unused in LIVE mode

if USE_REAL_API:
    logger.info("[TOUCHE] LIVE MODE - Binance async fetcher active")
else:
    logger.info("[TOUCHE] MOCK DATA MODE - Using random test values")

# Store metric values in simple variables
_metric_values = {
    'touche_eqs_score': random.uniform(50, 85),
    'touche_signal_quality': random.uniform(70, 95),
}

def update_metrics_background():
    """Background thread to update metrics every 10 seconds"""
    while True:
        try:
            _metric_values['touche_eqs_score'] = random.uniform(50, 85)
            _metric_values['touche_signal_quality'] = random.uniform(70, 95)
            time.sleep(10)
        except Exception as e:
            logger.error(f"Error updating metrics: {e}")
            time.sleep(10)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown"""
    global _data_fetcher
    # LIVE_INTEGRATION: Initialise async fetcher on startup
    _data_fetcher = BinanceDataFetcher(
        base_url=touche_config.binance_base_url,
        timeout=touche_config.binance_timeout,
        max_retries=touche_config.binance_retries,
        redis_url=touche_config.redis_url,
        cache_ttl=touche_config.cache_ttl_seconds,
    )
    logger.info(
        "[DATA] Mode=%s, Source=Binance, BaseURL=%s",
        touche_config.data_mode,
        touche_config.binance_base_url,
    )
    # Startup
    metrics_thread = threading.Thread(target=update_metrics_background, daemon=True)
    metrics_thread.start()
    logger.info("✅ Touche AI metrics background thread started")
    yield
    # Shutdown
    logger.info("🛑 Touche AI shutting down")

app = FastAPI(
    title="Touche AI Limited",
    description="Technical Analysis Engine",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    # LIVE_INTEGRATION: report data_mode and binance connectivity
    mode = touche_config.data_mode
    binance_connected = False
    if mode == "LIVE" and _data_fetcher is not None:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.get(
                    f"{touche_config.binance_base_url}/api/v3/ping"
                )
                binance_connected = r.status_code == 200
        except Exception:
            binance_connected = False
    return {
        "status": "ok",
        "service": "touche-ai",
        "version": "1.0.0",
        "data_mode": mode,
        "binance_connected": binance_connected,
    }

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    # Update metric values
    _metric_values['touche_eqs_score'] = random.uniform(50, 85)
    _metric_values['touche_signal_quality'] = random.uniform(70, 95)

    # Get standard metrics
    base_metrics = generate_latest(REGISTRY).decode()

    # Add custom metrics + MODE info
    mode = "REAL" if USE_REAL_API else "MOCK"
    custom_metrics = (
        f"# HELP touche_mode Operating mode (REAL API or MOCK data)\n"
        f"# TYPE touche_mode gauge\n"
        f"touche_mode{{mode=\"{mode}\"}} 1\n"
        f"# HELP touche_eqs_score Touche EQS Score (0-100) - {mode} MODE\n"
        f"# TYPE touche_eqs_score gauge\n"
        f"touche_eqs_score {_metric_values['touche_eqs_score']}\n"
        f"# HELP touche_signal_quality Touche Signal Quality - {mode} MODE\n"
        f"# TYPE touche_signal_quality gauge\n"
        f"touche_signal_quality {_metric_values['touche_signal_quality']}\n"
    )

    return Response(content=base_metrics + custom_metrics, media_type=CONTENT_TYPE_LATEST)

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Touche AI Limited",
        "description": "Technical Analysis",
        "endpoints": {
            "health": "/health",
            "metrics": "/metrics",
            "docs": "/docs"
        }
    }


@app.get("/touche/key_levels")
async def get_touche_key_levels(symbol: str = "BTCUSDT"):
    """Protocol endpoint: Fundamental AI -> Touche AI key technical levels."""
    base = 45000.0 if symbol.upper().startswith("BTC") else 3000.0
    return {
        "symbol": symbol,
        "support_levels": [round(base * 0.98, 2), round(base * 0.95, 2)],
        "resistance_levels": [round(base * 1.02, 2), round(base * 1.05, 2)],
        "pivot": round(base, 2),
        "source": "touche-ai",
    }


# AEGIS v7.1: Horizon-to-timeframe mapping (mirrors horizon_configs.yaml)
HORIZON_TF_MAP: dict[str, list[str]] = {
    "short":  ["4h", "1d"],
    "medium": ["1d", "4h"],
    "long":   ["1w", "1d"],
}
_VALID_HORIZONS = {"short", "medium", "long"}


def _eqs_for_timeframe(symbol: str, tf: str, seed_offset: int = 0) -> float:
    """Reproduce a deterministic mock EQS for a given symbol+timeframe pair."""
    rng = random.Random(abs(hash(symbol.upper() + tf)) + seed_offset)
    return round(rng.uniform(30, 95), 2)


def _signal_from_eqs(eqs: float) -> str:
    if eqs >= 60:
        return "BUY"
    if eqs <= 40:
        return "SELL"
    return "NEUTRAL"


def _base_price_for_symbol(symbol: str) -> float:
    """Deterministic mock base price used across Touche endpoints."""
    return 45000.0 if symbol.upper().startswith("BTC") else 3000.0


def _price_proxy_for_symbol(symbol: str) -> float:
    """Simple current-price proxy for structure checks in MOCK mode."""
    return round(_base_price_for_symbol(symbol), 2)


def _mock_ohlcv_series(symbol: str, limit: int = 120) -> dict[str, list[float]]:
    """Build deterministic OHLCV-like series for MOCK mode."""
    base = _base_price_for_symbol(symbol)
    rng = random.Random(abs(hash(symbol.upper())) + 1337)
    closes: list[float] = []
    volumes: list[float] = []
    price = base
    for i in range(limit):
        drift = 0.0005 if i % 18 < 9 else -0.0003
        noise = rng.uniform(-0.003, 0.003)
        price = max(1.0, price * (1.0 + drift + noise))
        closes.append(round(price, 2))
        volumes.append(round(rng.uniform(800.0, 2200.0), 2))
    return {"close": closes, "volume": volumes}


def _get_recent_ohlcv(symbol: str, limit: int = 120) -> dict[str, list[float]]:
    """Fetch OHLCV from Binance when available; otherwise deterministic mock."""
    if USE_REAL_API and binance_client is not None:
        try:
            klines = binance_client.get_klines(symbol=symbol.upper(), interval="15m", limit=limit)
            closes = [float(k[4]) for k in klines]
            volumes = [float(k[5]) for k in klines]
            if len(closes) >= 30 and len(volumes) >= 30:
                return {"close": closes, "volume": volumes}
        except Exception as exc:
            logger.warning("[TOUCHE] real ohlcv fetch failed, using mock: %s", exc)
    return _mock_ohlcv_series(symbol, limit=limit)


def _extract_series(df: Any, key: str) -> list[float]:
    """Extract a numeric series from dict-like or list-like payloads."""
    if isinstance(df, dict):
        vals = df.get(key, [])
        return [float(v) for v in vals]
    if isinstance(df, list):
        out: list[float] = []
        for row in df:
            if isinstance(row, dict) and key in row:
                out.append(float(row[key]))
        return out
    return []


def _compute_rsi(closes: list[float], period: int = 14) -> float:
    """Classic RSI(14) calculation with simple average gains/losses."""
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(0.0, d) for d in deltas[-period:]]
    losses = [abs(min(0.0, d)) for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def get_last_higher_low(df: Any) -> float:
    """Return last local low that is higher than the previous local low."""
    closes = _extract_series(df, "close")
    if len(closes) < 5:
        return closes[-1] if closes else 0.0

    lows: list[tuple[int, float]] = []
    for i in range(1, len(closes) - 1):
        if closes[i] < closes[i - 1] and closes[i] < closes[i + 1]:
            lows.append((i, closes[i]))

    for j in range(len(lows) - 1, 0, -1):
        prev_low = lows[j - 1][1]
        curr_low = lows[j][1]
        if curr_low > prev_low:
            return round(curr_low, 2)

    return round(min(closes[-5:]), 2)


def get_last_lower_high(df: Any) -> float:
    """Return last local high that is lower than the previous local high."""
    closes = _extract_series(df, "close")
    if len(closes) < 5:
        return closes[-1] if closes else 0.0

    highs: list[tuple[int, float]] = []
    for i in range(1, len(closes) - 1):
        if closes[i] > closes[i - 1] and closes[i] > closes[i + 1]:
            highs.append((i, closes[i]))

    for j in range(len(highs) - 1, 0, -1):
        prev_high = highs[j - 1][1]
        curr_high = highs[j][1]
        if curr_high < prev_high:
            return round(curr_high, 2)

    return round(max(closes[-5:]), 2)


def is_broken(current_price: float, level: float, side: str) -> bool:
    """Check whether structure level is broken for LONG/SHORT semantics."""
    normalized = (side or "LONG").upper()
    if normalized == "LONG":
        return float(current_price) < float(level)
    if normalized == "SHORT":
        return float(current_price) > float(level)
    return False


@app.get("/touche/analyze")
async def touche_analyze(symbol: str = "BTC", timeframe: str = "1h,4h", horizon: str = "medium"):
    """
    Multi-timeframe technical analysis for a symbol.

    Query params:
        symbol    – ticker (e.g. BTC, ETH)
        timeframe – comma-separated TF list (e.g. "1h,4h" or "15m,1h,4h,1d")
        horizon   – investment horizon: short | medium | long
                    When provided, overrides the timeframe param with the
                    horizon-specific TF set from HORIZON_TF_MAP.

    Returns:
        {
            "symbol": "BTC",
            "eqs": 78,
            "timeframes_requested": ["1h", "4h"],
            "tf_signals": {"15m": "BUY", "1h": "BUY", "4h": "NEUTRAL", "1d": "BUY"}
        }

    Notes:
        - eqs is the average EQS across requested timeframes.
        - tf_signals always contains all four standard timeframes (15m, 1h, 4h, 1d)
          regardless of the timeframe param, so callers always get a complete picture.
        - In MOCK mode values are deterministic per symbol+timeframe.
    """
    sym = symbol.upper().strip()

    # Horizon takes precedence over the raw timeframe param
    if horizon not in _VALID_HORIZONS:
        horizon = "medium"
    horizon_tfs = HORIZON_TF_MAP[horizon]
    requested_tfs = horizon_tfs

    standard_tfs = ["15m", "1h", "4h", "1d"]
    # Extend with any horizon-specific TFs not already covered (e.g. "1w" for long)
    for _tf in requested_tfs:
        if _tf not in standard_tfs:
            standard_tfs.append(_tf)
    mode = touche_config.data_mode
    fallback_used = False
    data_range: dict = {}

    # LIVE_INTEGRATION: attempt to derive EQS from live closes
    if mode == "LIVE" and _data_fetcher is not None:
        try:
            import pandas as pd
            primary_tf = requested_tfs[0] if requested_tfs else "1h"
            df = await _data_fetcher.fetch_ohlcv(sym, primary_tf, limit=100)
            # Detect whether fetcher fell back internally
            fallback_used = not (hasattr(df.index, "tzinfo") and len(df) > 10)
            if isinstance(df.index, pd.DatetimeIndex) and len(df) > 0:
                data_range = {
                    "start": df.index[0].isoformat(),
                    "end": df.index[-1].isoformat(),
                }
            closes = df["close"].tolist() if "close" in df.columns else []
            rsi_live = _compute_rsi([float(c) for c in closes]) if len(closes) > 14 else 50.0
            # Map RSI to an EQS proxy for the primary timeframe
            live_eqs_primary = round(min(95.0, max(5.0, rsi_live)), 2)
            tf_eqs: dict = {tf: _eqs_for_timeframe(sym, tf) for tf in standard_tfs}
            tf_eqs[primary_tf] = live_eqs_primary
        except Exception as exc:
            logger.warning("[DATA] Fallback activated for %s: %s", sym, exc)
            fallback_used = True
            tf_eqs = {tf: _eqs_for_timeframe(sym, tf) for tf in standard_tfs}
    else:
        tf_eqs = {tf: _eqs_for_timeframe(sym, tf) for tf in standard_tfs}

    tf_signals: dict = {tf: _signal_from_eqs(eqs) for tf, eqs in tf_eqs.items()}
    agg_tfs = [tf for tf in requested_tfs if tf in tf_eqs] or standard_tfs
    eqs = round(sum(tf_eqs[tf] for tf in agg_tfs) / len(agg_tfs), 2)

    logger.info(
        "[DATA] Mode=%s, Source=Binance, Symbol=%s, EQS=%s, Fallback=%s",
        mode, sym, eqs, fallback_used,
    )

    response: dict = {
        "symbol": sym,
        "eqs": eqs,
        "eqs_score": eqs,  # LIVE_INTEGRATION: alias expected by tests
        "timeframes_requested": requested_tfs,
        "tf_signals": tf_signals,
        "source": "touche-ai",
        "data_mode": mode,
        "fallback_used": fallback_used,
        "horizon_applied": horizon,
    }
    # FIX: Always include data_range for schema consistency.
    response["data_range"] = data_range if data_range else {"start": None, "end": None}
    return response


@app.get("/touche/exit_signal")
async def touche_exit_signal(
    symbol: str = "BTCUSDT",
    entry_price: float = 45000.0,
    position_side: str = "LONG",
):
    """
    Dynamic position exit helper for paper trading.

    Rules:
    - LONG: last Higher Low broke -> FULL_CLOSE
    - SHORT: last Lower High broke -> FULL_CLOSE
    - RSI > 70 and current volume < avg(volume, 20) -> PARTIAL_CLOSE 50%
    - otherwise NONE
    """
    sym = symbol.upper().strip()
    side = (position_side or "LONG").strip().upper()

    # LIVE_INTEGRATION: Prefer async Binance fetcher in LIVE mode.
    if touche_config.data_mode == "LIVE" and _data_fetcher is not None:
        try:
            df = await _data_fetcher.fetch_ohlcv(sym, interval="15m", limit=120)
            closes = [float(v) for v in df["close"].tolist()] if "close" in df.columns else []
            volumes = [float(v) for v in df["volume"].tolist()] if "volume" in df.columns else []
            ohlcv = {"close": closes, "volume": volumes}
        except Exception as exc:
            logger.warning("[DATA] exit_signal live fetch failed for %s: %s", sym, exc)
            ohlcv = _get_recent_ohlcv(sym, limit=120)
            closes = _extract_series(ohlcv, "close")
            volumes = _extract_series(ohlcv, "volume")
    else:
        ohlcv = _get_recent_ohlcv(sym, limit=120)
        closes = _extract_series(ohlcv, "close")
        volumes = _extract_series(ohlcv, "volume")

    current_price = float(closes[-1]) if closes else _price_proxy_for_symbol(sym)
    rsi_val = _compute_rsi(closes)
    volume_avg_20 = (sum(volumes[-20:]) / 20.0) if len(volumes) >= 20 else (sum(volumes) / len(volumes) if volumes else 0.0)
    current_volume = float(volumes[-1]) if volumes else 0.0

    hl_level = get_last_higher_low(ohlcv)
    lh_level = get_last_lower_high(ohlcv)

    if side == "LONG" and is_broken(current_price, hl_level, "LONG"):
        return {
            "symbol": sym,
            "entry_price": float(entry_price),
            "position_side": side,
            "current_price": current_price,
            "exit": "FULL_CLOSE",
            "percentage": 1.0,
            "reason": "Higher Low broke",
            "level": hl_level,
            "rsi": rsi_val,
            "current_volume": current_volume,
            "avg_volume_20": round(volume_avg_20, 2),
            "source": "touche-ai",
            "data_mode": "REAL" if USE_REAL_API else "MOCK",
        }

    if side == "SHORT" and is_broken(current_price, lh_level, "SHORT"):
        return {
            "symbol": sym,
            "entry_price": float(entry_price),
            "position_side": side,
            "current_price": current_price,
            "exit": "FULL_CLOSE",
            "percentage": 1.0,
            "reason": "Lower High broke",
            "level": lh_level,
            "rsi": rsi_val,
            "current_volume": current_volume,
            "avg_volume_20": round(volume_avg_20, 2),
            "source": "touche-ai",
            "data_mode": "REAL" if USE_REAL_API else "MOCK",
        }

    if rsi_val > 70.0 and current_volume < volume_avg_20:
        return {
            "symbol": sym,
            "entry_price": float(entry_price),
            "position_side": side,
            "current_price": current_price,
            "exit": "PARTIAL_CLOSE",
            "percentage": 0.50,
            "reason": "Overbought + low volume",
            "rsi": rsi_val,
            "current_volume": current_volume,
            "avg_volume_20": round(volume_avg_20, 2),
            "source": "touche-ai",
            "data_mode": "REAL" if USE_REAL_API else "MOCK",
        }

    return {
        "symbol": sym,
        "entry_price": float(entry_price),
        "position_side": side,
        "current_price": current_price,
        "exit": "NONE",
        "percentage": 0.0,
        "rsi": rsi_val,
        "current_volume": current_volume,
        "avg_volume_20": round(volume_avg_20, 2),
        "source": "touche-ai",
        "data_mode": "REAL" if USE_REAL_API else "MOCK",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
