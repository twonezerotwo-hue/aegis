# AEGIS v7.2 - Quantum API live-data hardening and futures integration.
"""
Quantum AI Limited - Market-Making Engine API
"""
from fastapi import FastAPI, Response
from contextlib import asynccontextmanager
import asyncio
import logging
import random
import numpy as np
import threading
import time
import os
import httpx
from dotenv import load_dotenv

try:
    from services.futures_fetcher import FuturesFetcher
except ModuleNotFoundError:
    from strategies.quantum_ai.services.futures_fetcher import FuturesFetcher

try:
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
    from determinism_control import DeterministicSeedManager, GLOBAL_SEED

    DeterministicSeedManager.initialize(GLOBAL_SEED, verbose=False)
except Exception:
    random.seed(42)
    np.random.seed(42)

load_dotenv()

from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Counter, Gauge, Histogram

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "").strip()
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", os.getenv("BINANCE_SECRET_KEY", "")).strip()
USE_REAL_API = bool(BINANCE_API_KEY and BINANCE_API_SECRET and not BINANCE_API_KEY.startswith("your_"))

if USE_REAL_API:
    logger.info("[QUANTUM] REAL API MODE - credentials configured")
else:
    logger.info("[QUANTUM] PUBLIC DATA MODE - market data uses public Binance endpoints")

REQUEST_COUNT = Counter("quantum_requests_total", "Total requests", ["method", "endpoint"])
REQUEST_LATENCY = Histogram("quantum_request_duration_seconds", "Request latency (seconds)", ["endpoint"])
ACTIVE_REQUESTS = Gauge("quantum_active_requests", "Active requests")
MM_SPREAD = Gauge("quantum_spread_bps", "Market-making spread (bps)")
MM_INVENTORY = Gauge("quantum_inventory", "Current inventory")
QUANTUM_PNL = Gauge("quantum_pnl", "Market-making PnL")
FUNDING_RATE_GAUGE = Gauge("quantum_funding_rate_pct", "Binance Futures Funding Rate %")
OI_GAUGE = Gauge("quantum_open_interest_usdt", "Open Interest in USDT")
LS_RATIO_GAUGE = Gauge("quantum_long_short_ratio", "Global Long/Short Account Ratio")

_metric_values = {
    "quantum_pnl": None,
    "quantum_spread_bps": None,
    "timestamp": None,
    "source": "uninitialized",
    "verified": False,
    "data_status": "UNKNOWN",
    "warning": "No futures snapshot fetched yet.",
}

futures_fetcher = FuturesFetcher()


def _service_mode() -> str:
    if _metric_values.get("data_status") == "LIVE":
        return "REAL"
    if _metric_values.get("data_status") == "RECENT":
        return "CACHE_REAL"
    return "UNAVAILABLE"


async def _fetch_depth_snapshot(symbol: str) -> tuple[float | None, float | None]:
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            response = await client.get(
                "https://fapi.binance.com/fapi/v1/depth",
                params={"symbol": symbol.upper().strip(), "limit": 20},
            )
            response.raise_for_status()
            payload = response.json() if isinstance(response.json(), dict) else {}
        bids = payload.get("bids") or []
        asks = payload.get("asks") or []
        if not bids or not asks:
            return None, None
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        spread_pct = ((best_ask - best_bid) / max(best_ask, 1e-9)) * 100.0
        depth_usd = 0.0
        for side in (bids[:10], asks[:10]):
            for level in side:
                price = float(level[0])
                quantity = float(level[1])
                depth_usd += price * quantity
        return round(depth_usd, 2), round(spread_pct, 4)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[QUANTUM] depth fetch failed for %s: %s", symbol, exc)
        return None, None


async def _refresh_metric_snapshot(symbol: str = "BTCUSDT") -> None:
    result = await futures_fetcher.get_futures_data(symbol=symbol)
    _metric_values.update(
        {
            "quantum_pnl": round((result.modifier - 0.5) * 100000.0, 2),
            "quantum_spread_bps": round(max(0.1, abs(result.funding_rate_pct) * 100.0), 2),
            "timestamp": result.timestamp,
            "source": result.source,
            "verified": result.verified,
            "data_status": result.data_status,
            "warning": " ".join(result.warnings) or None,
        }
    )
    QUANTUM_PNL.set(float(_metric_values["quantum_pnl"]))
    MM_SPREAD.set(float(_metric_values["quantum_spread_bps"]))
    MM_INVENTORY.set(float(result.open_interest_usdt) / 100000.0 if result.open_interest_usdt else 0.0)
    FUNDING_RATE_GAUGE.set(float(result.funding_rate_pct))
    OI_GAUGE.set(float(result.open_interest_usdt))
    LS_RATIO_GAUGE.set(float(result.long_short_ratio))


def update_metrics_thread():
    while True:
        try:
            asyncio.run(_refresh_metric_snapshot())
            time.sleep(30)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error updating Quantum metrics: %s", exc, exc_info=True)
            time.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Quantum AI Module starting up...")
    thread = threading.Thread(target=update_metrics_thread, daemon=True)
    thread.start()
    yield
    logger.info("Quantum AI Module shutting down...")


app = FastAPI(
    title="Quantum AI Limited",
    description="Market-Making Engine with Avellaneda-Stoikov Algorithm",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "quantum-ai",
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
    if _metric_values.get("timestamp") is None:
        await _refresh_metric_snapshot()
    custom_metrics = (
        "# HELP quantum_mode Operating mode (REAL, CACHE_REAL, UNAVAILABLE)\n"
        "# TYPE quantum_mode gauge\n"
        f'quantum_mode{{mode="{_service_mode()}"}} 1\n'
    )
    return Response(content=base_metrics + custom_metrics, media_type=CONTENT_TYPE_LATEST)


@app.get("/")
async def root():
    return {
        "service": "Quantum AI Limited",
        "description": "Market-Making Engine",
        "endpoints": {
            "health": "/health",
            "metrics": "/metrics",
            "docs": "/docs",
        },
    }


@app.post("/executor/liquidity_check")
async def liquidity_check(payload: dict):
    symbol = str(payload.get("symbol", "BTCUSDT")).upper().strip()
    depth_usd = payload.get("depth_usd")
    spread_pct = payload.get("spread_pct")
    warnings: list[str] = []

    if depth_usd is None or spread_pct is None:
        live_depth_usd, live_spread_pct = await _fetch_depth_snapshot(symbol)
        if depth_usd is None:
            depth_usd = live_depth_usd
        if spread_pct is None:
            spread_pct = live_spread_pct

    if depth_usd is None or spread_pct is None:
        warnings.append("Live order book depth unavailable.")

    result = await futures_fetcher.get_futures_data(symbol=symbol)
    funding_rate = float(result.funding_rate)
    requested_signal = str(payload.get("signal", "HOLD")).upper().strip()
    filtered_signal = "HOLD" if requested_signal == "BUY" and funding_rate > 0.01 else requested_signal

    numeric_depth = float(depth_usd or 0.0)
    numeric_spread = float(spread_pct or 999.0)

    return {
        "depth_usd": numeric_depth,
        "spread_pct": numeric_spread,
        "is_sufficient": numeric_depth >= 500000 and numeric_spread <= 0.1,
        "min_depth_required": 500000.0,
        "max_spread_allowed": 0.1,
        "funding_rate": funding_rate,
        "open_interest_change_24h": None,
        "liquidation_heatmap": result.futures_signal,
        "requested_signal": requested_signal,
        "filtered_signal": filtered_signal,
        "buy_filtered": requested_signal == "BUY" and filtered_signal != requested_signal,
        "source": result.source,
        "timestamp": result.timestamp,
        "verified": result.verified and not warnings,
        "data_status": result.data_status if not warnings else "MISSING",
        "warnings": result.warnings + warnings,
    }


@app.get("/quantum/futures_metrics")
async def get_futures_metrics(symbol: str = "BTCUSDT"):
    result = await futures_fetcher.get_futures_data(symbol)
    return {
        "funding_rate": result.funding_rate,
        "open_interest_change_24h": None,
        "liquidation_heatmap": result.futures_signal,
        "source": result.source,
        "timestamp": result.timestamp,
        "verified": result.verified,
        "data_status": result.data_status,
        "warnings": result.warnings,
    }


@app.get("/quantum/futures_data")
async def get_futures_data(symbol: str = "BTCUSDT"):
    result = await futures_fetcher.get_futures_data(symbol=symbol)
    payload = result.model_dump()
    payload["signal"] = payload.get("futures_signal", "CACHE_FALLBACK")
    return payload


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8003)
