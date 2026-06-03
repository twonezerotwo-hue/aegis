"""
Touche AI Limited - Technical Analysis API
LIVE_INTEGRATION: Binance async data fetcher with fallback.
"""
from fastapi import FastAPI, Response, HTTPException
from contextlib import asynccontextmanager
import logging
import random
import numpy as np
import threading
import time
import os
from datetime import datetime, timezone
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
    from strategies.touche_ai.services.data_fetcher import BinanceDataFetcher, DataUnavailableError
except ModuleNotFoundError:
    # Inside Docker: code is at /app/touche_ai/
    from config import config as touche_config  # type: ignore[no-redef]
    from services.data_fetcher import BinanceDataFetcher, DataUnavailableError  # type: ignore[no-redef]

# LIVE_INTEGRATION: Module-level fetcher instance
_data_fetcher: Optional[BinanceDataFetcher] = None

# Legacy compat: USE_REAL_API mirrors DATA_MODE for existing code paths
USE_REAL_API = touche_config.data_mode.upper() != "CACHE_ONLY"
binance_client = None  # kept for backward compat, unused in LIVE mode

if USE_REAL_API:
    logger.info("[TOUCHE] LIVE-READY MODE - Binance async fetcher active")
else:
    logger.info("[TOUCHE] CACHE-ONLY MODE - Binance async fetcher cache path active")

# Store metric values in simple variables
_metric_values = {
    "touche_eqs_score": None,
    "touche_signal_quality": None,
    "timestamp": None,
    "source": "uninitialized",
    "verified": False,
    "data_status": "UNKNOWN",
    "warning": "No market data fetched yet.",
}

def _service_mode() -> str:
    if _metric_values.get("data_status") == "LIVE":
        return "REAL"
    if _metric_values.get("data_status") == "RECENT":
        return "CACHE_REAL"
    if touche_config.fallback_to_mock:
        return "MOCK_OPT_IN"
    return "UNAVAILABLE"


async def _refresh_metric_snapshot(symbol: str = "BTCUSDT", timeframe: str = "1h") -> None:
    if _data_fetcher is None:
        _metric_values.update(
            {
                "touche_eqs_score": None,
                "touche_signal_quality": None,
                "timestamp": None,
                "source": "service_not_initialized",
                "verified": False,
                "data_status": "UNKNOWN",
                "warning": "Binance data fetcher not initialized.",
            }
        )
        return

    try:
        df = await _data_fetcher.fetch_ohlcv(symbol, timeframe, limit=120)
        fetch_meta = _data_fetcher.get_last_fetch_meta()
        closes = [float(v) for v in df["close"].tolist()] if "close" in df.columns else []
        eqs = round(min(95.0, max(5.0, _compute_rsi(closes))), 2) if len(closes) >= 15 else None
        signal_quality = round(min(100.0, max(0.0, len(closes) / 1.2)), 2) if closes else None
        _metric_values.update(
            {
                "touche_eqs_score": eqs,
                "touche_signal_quality": signal_quality,
                "timestamp": fetch_meta.get("timestamp"),
                "source": fetch_meta.get("source", "binance_public"),
                "verified": bool(fetch_meta.get("verified")),
                "data_status": fetch_meta.get("data_status", "UNKNOWN"),
                "warning": fetch_meta.get("warning"),
            }
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[TOUCHE] metrics refresh failed: %s", exc)
        _metric_values.update(
            {
                "touche_eqs_score": None,
                "touche_signal_quality": None,
                "timestamp": None,
                "source": "binance_unavailable",
                "verified": False,
                "data_status": "MISSING",
                "warning": str(exc),
            }
        )


def update_metrics_background():
    """Background thread to refresh metric snapshot from real Binance data."""
    while True:
        try:
            asyncio.run(_refresh_metric_snapshot())
            time.sleep(30)
        except Exception as e:  # noqa: BLE001
            logger.error("Error updating Touche metrics: %s", e)
            time.sleep(30)


def _emit_metric_lines() -> str:
    mode = _service_mode()
    lines = [
        "# HELP touche_mode Operating mode (REAL, CACHE_REAL, UNAVAILABLE, MOCK_OPT_IN)",
        "# TYPE touche_mode gauge",
        f'touche_mode{{mode="{mode}"}} 1',
        "# HELP touche_data_available Whether a real or cached Touche snapshot is available",
        "# TYPE touche_data_available gauge",
        f"touche_data_available {1 if _metric_values.get('touche_eqs_score') is not None else 0}",
    ]
    if _metric_values.get("touche_eqs_score") is not None:
        lines.extend(
            [
                f"# HELP touche_eqs_score Touche EQS Score (0-100) - {mode} mode",
                "# TYPE touche_eqs_score gauge",
                f"touche_eqs_score {_metric_values['touche_eqs_score']}",
            ]
        )
    if _metric_values.get("touche_signal_quality") is not None:
        lines.extend(
            [
                f"# HELP touche_signal_quality Touche signal quality (0-100) - {mode} mode",
                "# TYPE touche_signal_quality gauge",
                f"touche_signal_quality {_metric_values['touche_signal_quality']}",
            ]
        )
    return "\n".join(lines) + "\n"

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
    binance_connected = False
    if _data_fetcher is not None:
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
        "data_mode": touche_config.data_mode,
        "binance_connected": binance_connected,
        "metric_source": _metric_values.get("source"),
        "metric_timestamp": _metric_values.get("timestamp"),
        "verified": bool(_metric_values.get("verified")),
        "data_status": _metric_values.get("data_status"),
    }

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    base_metrics = generate_latest(REGISTRY).decode()
    if _metric_values.get("timestamp") is None:
        await _refresh_metric_snapshot()
    return Response(content=base_metrics + _emit_metric_lines(), media_type=CONTENT_TYPE_LATEST)

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


def _binance_symbol(symbol: str) -> str:
    normalized = symbol.upper().strip()
    if normalized.endswith("USDT"):
        return normalized
    if "/" in normalized:
        normalized = normalized.replace("/", "")
    return f"{normalized}USDT"


def _compute_macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """MACD hesapla: histogram ve sinyal yönü."""
    if len(closes) < slow + signal:
        return {"histogram": 0.0, "direction": "NEUTRAL", "cross": None}
    def ema(vals: list[float], period: int) -> list[float]:
        k = 2.0 / (period + 1)
        result = [vals[0]]
        for v in vals[1:]:
            result.append(v * k + result[-1] * (1 - k))
        return result
    ema_fast   = ema(closes, fast)
    ema_slow   = ema(closes, slow)
    macd_line  = [f - s for f, s in zip(ema_fast[slow-1:], ema_slow)]
    signal_line = ema(macd_line, signal)
    hist        = [m - s for m, s in zip(macd_line[signal-1:], signal_line)]
    if not hist:
        return {"histogram": 0.0, "direction": "NEUTRAL", "cross": None}
    h_last = hist[-1]
    h_prev = hist[-2] if len(hist) >= 2 else h_last
    direction = "BULLISH" if h_last > 0 else "BEARISH" if h_last < 0 else "NEUTRAL"
    cross = None
    if h_prev < 0 and h_last > 0:
        cross = "GOLDEN"   # histogram sıfır çizgisini yukarı geçti
    elif h_prev > 0 and h_last < 0:
        cross = "DEATH"    # histogram sıfır çizgisini aşağı geçti
    return {"histogram": round(h_last, 6), "direction": direction, "cross": cross}


def _compute_ema_trend(closes: list[float], fast: int = 20, slow: int = 50) -> dict:
    """EMA20/EMA50 trendi ve fiyatın EMA'ya göre konumu."""
    if len(closes) < slow:
        return {"fast": None, "slow": None, "trend": "NEUTRAL", "price_vs_slow": None}
    k_f = 2.0 / (fast + 1); k_s = 2.0 / (slow + 1)
    ef = closes[0]; es = closes[0]
    for c in closes[1:]:
        ef = c * k_f + ef * (1 - k_f)
        es = c * k_s + es * (1 - k_s)
    price = closes[-1]
    trend = "BULLISH" if ef > es else "BEARISH" if ef < es else "NEUTRAL"
    return {
        "ema_fast": round(ef, 2),
        "ema_slow": round(es, 2),
        "trend": trend,
        "price_above_ema": price > es,
    }


async def _analyze_timeframe(symbol: str, timeframe: str) -> dict[str, Any]:
    """
    7 fazlı Touche EQS pipeline — RSI tek başına değil, tam teknik analiz.

    Faz 1: Likidite Süpürmesi (Smart Money sweep tespiti)
    Faz 2: Piyasa Yapısı + RSI/MACD Diverjans
    Faz 3: Arz/Talep Zonu + FVG + Confluence
    Faz 4: OBV + CMF Hacim Teyidi
    Faz 5: Hammer, Engulfing, Doji gibi mum formasyonları
    Faz 6: ATR bazlı SL/TP hesabı
    Faz 7: Fundamental/Makro köprüsü
    """
    if _data_fetcher is None:
        raise RuntimeError("service_not_initialized")

    binance_symbol = _binance_symbol(symbol)
    df_pd = await _data_fetcher.fetch_ohlcv(binance_symbol, timeframe, limit=200)
    fetch_meta = _data_fetcher.get_last_fetch_meta()
    closes = [float(v) for v in df_pd["close"].tolist()] if "close" in df_pd.columns else []
    if len(closes) < 15:
        raise RuntimeError(f"insufficient_ohlcv_rows:{timeframe}")

    # ── Fallback indikatörler (orchestrator başarısız olursa) ────────────────
    rsi   = _compute_rsi(closes)
    macd  = _compute_macd(closes)
    ema   = _compute_ema_trend(closes)

    # ── 7 fazlı orchestrator ─────────────────────────────────────────────────
    orchestrator_eqs   = None
    orchestrator_signal = None
    phase_summaries: list[dict] = []

    try:
        import polars as pl
        import os as _os
        import sys as _sys
        # Uvicorn /app/touche_ai/ içinden çalışır — üst dizini path'e ekle
        _app_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
        if _app_dir not in _sys.path:
            _sys.path.insert(0, _app_dir)
        from touche_ai.src.engine.orchestrator import ToucheOrchestrator

        # pandas → polars dönüşümü
        df_pl = pl.from_pandas(df_pd.reset_index())

        orc = ToucheOrchestrator(symbol=binance_symbol, timeframe=timeframe)
        result = await orc.analyze(df_pl)

        raw_eqs = float(result.eqs_score)
        orchestrator_signal = result.recommendation   # BUY / SELL / HOLD
        phase_summaries = [
            {
                "phase": r.get("phase_name", ""),
                "signal": r.get("signal", ""),
                "score": round(float(r.get("score", 0)), 1),
                "reason": r.get("reason", ""),
            }
            for r in (result.phase_results or [])
        ]
        # EQS=0.0 → pipeline bloke (NO_TRADE/NEUTRAL yön).
        # Bu durumda faz ortalama skorunu kullan — 0.0 "SAT" olarak yanlış okunuyor.
        if raw_eqs == 0.0 and phase_summaries:
            phase_avg = sum(p["score"] for p in phase_summaries) / len(phase_summaries)
            orchestrator_eqs = round(min(95.0, max(5.0, phase_avg)), 2)
        else:
            orchestrator_eqs = round(min(95.0, max(5.0, raw_eqs)), 2)
        logger.info("[TOUCHE-7F] %s %s → EQS=%.1f signal=%s (raw_eqs=%.1f)",
                    binance_symbol, timeframe, orchestrator_eqs, orchestrator_signal, raw_eqs)
    except Exception as exc:
        logger.warning("[TOUCHE-7F] orchestrator failed (%s %s): %s — RSI fallback",
                       binance_symbol, timeframe, exc)

    # Orchestrator başarılıysa onun EQS'ini kullan, yoksa RSI fallback
    if orchestrator_eqs is not None:
        eqs    = orchestrator_eqs
        signal = orchestrator_signal or _signal_from_eqs(eqs)
    else:
        eqs    = round(min(95.0, max(5.0, rsi)), 2)
        signal = _signal_from_eqs(eqs)

    timestamp = fetch_meta.get("timestamp")
    return {
        "eqs":      eqs,
        "signal":   signal,
        "rsi":      round(rsi, 2),
        "rsi_zone": "oversold" if rsi < 30 else "overbought" if rsi > 70 else "neutral",
        "macd":     macd,
        "ema_trend": ema,
        "phase_results": phase_summaries,
        "engine": "7-phase-orchestrator" if orchestrator_eqs is not None else "rsi-fallback",
        "timestamp":   timestamp,
        "source":      fetch_meta.get("source", "binance_public"),
        "verified":    bool(fetch_meta.get("verified")),
        "data_status": fetch_meta.get("data_status", "UNKNOWN"),
        "cached":      bool(fetch_meta.get("cached")),
        "row_count":   len(closes),
        "range": {
            "start": df_pd.index[0].isoformat() if len(df_pd.index) else None,
            "end":   df_pd.index[-1].isoformat() if len(df_pd.index) else None,
        },
    }


def _unverified_touche_payload(
    symbol: str,
    requested_tfs: list[str],
    tf_signals: dict[str, str],
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "eqs": 50.0,
        "eqs_score": 50.0,
        "timeframes_requested": requested_tfs,
        "tf_signals": tf_signals,
        "source": "touche-ai",
        "data_mode": touche_config.data_mode,
        "fallback_used": False,
        "verified": False,
        "data_status": "MISSING",
        "warnings": warnings,
        "data_range": {"start": None, "end": None},
    }


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
    for _tf in requested_tfs:
        if _tf not in standard_tfs:
            standard_tfs.append(_tf)
    tf_results: dict[str, dict[str, Any]] = {}
    unavailable_timeframes: list[str] = []
    warnings: list[str] = []
    tf_signals: dict[str, str] = {}
    tf_eqs: dict[str, float] = {}
    ranges: list[dict[str, str | None]] = []

    for tf in standard_tfs:
        try:
            result = await _analyze_timeframe(sym, tf)
            tf_results[tf] = result
            tf_eqs[tf] = float(result["eqs"])
            tf_signals[tf] = str(result["signal"])
            if isinstance(result.get("range"), dict):
                ranges.append(result["range"])
        except DataUnavailableError as exc:
            unavailable_timeframes.append(tf)
            tf_signals[tf] = "UNAVAILABLE"
            warnings.append(str(exc))
        except Exception as exc:  # noqa: BLE001
            unavailable_timeframes.append(tf)
            tf_signals[tf] = "UNAVAILABLE"
            warnings.append(f"{tf}: {exc}")

    requested_scores = [tf_eqs[tf] for tf in requested_tfs if tf in tf_eqs]
    if not requested_scores:
        return _unverified_touche_payload(
            sym,
            requested_tfs,
            tf_signals,
            warnings or [f"No verified OHLCV data available for {sym}."],
        )

    eqs = round(sum(requested_scores) / len(requested_scores), 2)
    timestamps = [tf_results[tf].get("timestamp") for tf in requested_tfs if tf in tf_results]
    valid_timestamps = [ts for ts in timestamps if isinstance(ts, str) and ts.strip()]
    statuses = [str(tf_results[tf].get("data_status", "UNKNOWN")) for tf in requested_tfs if tf in tf_results]
    data_status = "LIVE" if all(status == "LIVE" for status in statuses) else "RECENT" if statuses and all(
        status in {"LIVE", "RECENT"} for status in statuses
    ) else "PARTIAL_FALLBACK" if unavailable_timeframes else "UNKNOWN"
    verified = data_status in {"LIVE", "RECENT"} and not unavailable_timeframes
    data_range = {
        "start": min(
            (item.get("start") for item in ranges if isinstance(item.get("start"), str)),
            default=None,
        ),
        "end": max(
            (item.get("end") for item in ranges if isinstance(item.get("end"), str)),
            default=None,
        ),
    }

    return {
        "symbol": sym,
        "eqs": eqs,
        "eqs_score": eqs,
        "timeframes_requested": requested_tfs,
        "tf_signals": tf_signals,
        "timeframe_details": tf_results,
        "source": "touche-ai",
        "timestamp": max(valid_timestamps) if valid_timestamps else None,
        "data_mode": touche_config.data_mode,
        "fallback_used": False,
        "verified": verified,
        "data_status": data_status,
        "warnings": warnings,
        "unavailable_timeframes": unavailable_timeframes,
        "horizon_applied": horizon,
        "data_range": data_range,
    }


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

    fetch_meta: dict[str, Any] = {
        "source": "binance_unavailable",
        "timestamp": None,
        "verified": False,
        "data_status": "MISSING",
        "warning": "No verified 15m OHLCV data available.",
    }
    if _data_fetcher is not None:
        try:
            df = await _data_fetcher.fetch_ohlcv(sym, interval="15m", limit=120)
            fetch_meta = _data_fetcher.get_last_fetch_meta()
            closes = [float(v) for v in df["close"].tolist()] if "close" in df.columns else []
            volumes = [float(v) for v in df["volume"].tolist()] if "volume" in df.columns else []
            ohlcv = {"close": closes, "volume": volumes}
        except Exception as exc:  # noqa: BLE001
            logger.warning("[DATA] exit_signal fetch failed for %s: %s", sym, exc)
            closes = []
            volumes = []
            ohlcv = {"close": closes, "volume": volumes}
            fetch_meta["warning"] = str(exc)
    else:
        closes = []
        volumes = []
        ohlcv = {"close": closes, "volume": volumes}

    current_price = float(closes[-1]) if closes else float(entry_price)
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
            "timestamp": fetch_meta.get("timestamp"),
            "verified": bool(fetch_meta.get("verified")),
            "data_status": fetch_meta.get("data_status", "UNKNOWN"),
            "warning": fetch_meta.get("warning"),
            "data_mode": _service_mode(),
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
            "timestamp": fetch_meta.get("timestamp"),
            "verified": bool(fetch_meta.get("verified")),
            "data_status": fetch_meta.get("data_status", "UNKNOWN"),
            "warning": fetch_meta.get("warning"),
            "data_mode": _service_mode(),
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
            "timestamp": fetch_meta.get("timestamp"),
            "verified": bool(fetch_meta.get("verified")),
            "data_status": fetch_meta.get("data_status", "UNKNOWN"),
            "warning": fetch_meta.get("warning"),
            "data_mode": _service_mode(),
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
        "timestamp": fetch_meta.get("timestamp"),
        "verified": bool(fetch_meta.get("verified")),
        "data_status": fetch_meta.get("data_status", "UNKNOWN"),
        "warning": fetch_meta.get("warning"),
        "data_mode": _service_mode(),
    }


# ── Phase Hit-Rate İzleme ────────────────────────────────────────────────────
# Son N sinyal analizinin faz özeti → hangi faz ne sıklıkla hangi yönde oy kullandı

_phase_snapshot_log: list[dict] = []  # son 100 snapshot
_MAX_SNAPSHOTS = 100


@app.post("/touche/phase_snapshot")
async def record_phase_snapshot(body: dict):
    """
    Orchestrator'dan gelen faz özetini kaydeder.
    dashboard_backend → her /touche/analyze çağrısı sonrası POST eder.
    """
    _phase_snapshot_log.append({**body, "recorded_at": __import__("time").time()})
    if len(_phase_snapshot_log) > _MAX_SNAPSHOTS:
        _phase_snapshot_log.pop(0)
    return {"stored": True, "total": len(_phase_snapshot_log)}


@app.get("/touche/phase_hit_rate")
async def get_phase_hit_rate():
    """
    Son N sinyal analizinden faz bazlı BULLISH/BEARISH/NEUTRAL oy dağılımı.
    Hangi faz daha tutarlı sinyal veriyor?
    """
    if not _phase_snapshot_log:
        return {"total_snapshots": 0, "phases": {}, "message": "Henüz snapshot yok"}

    agg: dict[str, dict[str, int]] = {}
    for snap in _phase_snapshot_log:
        for phase_key, info in (snap.get("phases") or {}).items():
            if phase_key not in agg:
                agg[phase_key] = {"BULLISH": 0, "BEARISH": 0, "NEUTRAL": 0, "total": 0}
            sig = str(info.get("signal", "NEUTRAL")).upper()
            agg[phase_key][sig] = agg[phase_key].get(sig, 0) + 1
            agg[phase_key]["total"] += 1

    result = {}
    for phase_key, counts in agg.items():
        total = counts["total"]
        bull = counts.get("BULLISH", 0)
        bear = counts.get("BEARISH", 0)
        neut = counts.get("NEUTRAL", 0)
        result[phase_key] = {
            "BULLISH_pct": round(bull / total * 100, 1) if total else 0,
            "BEARISH_pct": round(bear / total * 100, 1) if total else 0,
            "NEUTRAL_pct": round(neut / total * 100, 1) if total else 0,
            "total_signals": total,
            "dominant": max({"B": bull, "E": bear, "N": neut}, key={"B": bull, "E": bear, "N": neut}.get),
        }

    return {
        "total_snapshots": len(_phase_snapshot_log),
        "window": f"son {_MAX_SNAPSHOTS} analiz",
        "phases": result,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
