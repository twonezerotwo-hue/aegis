# AEGIS v7.2 - Quantum API canli veri etkinlestirme ve futures entegrasyonu.
"""
Quantum AI Limited - Market-Making Engine API
"""
from fastapi import FastAPI, Response
from contextlib import asynccontextmanager
import logging
import random
import numpy as np
import threading
import time
import os
from dotenv import load_dotenv

try:
    from services.futures_fetcher import FuturesFetcher
except ModuleNotFoundError:
    from strategies.quantum_ai.services.futures_fetcher import FuturesFetcher

# Determinism support
try:
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
    from determinism_control import DeterministicSeedManager, GLOBAL_SEED
    DeterministicSeedManager.initialize(GLOBAL_SEED, verbose=False)
except:
    random.seed(42)
    np.random.seed(42)

# Load environment variables from .env
load_dotenv()

from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Counter, Gauge, Histogram

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============ BINANCE CLIENT INITIALIZATION ============
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', '').strip()
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET', os.getenv('BINANCE_SECRET_KEY', '')).strip()

# Determine if using real API or mock data
USE_REAL_API = (
    BINANCE_API_KEY
    and BINANCE_API_SECRET
    and not BINANCE_API_KEY.startswith('your_')
    and not BINANCE_API_SECRET.startswith('your_')
)

binance_client = None
if USE_REAL_API:
    try:
        from binance.client import Client as BinanceClient
        binance_client = BinanceClient(BINANCE_API_KEY, BINANCE_API_SECRET)
        logger.info("✅ [QUANTUM] REAL API MODE - Binance Market-Making enabled")
    except Exception as e:
        logger.error(f"❌ [QUANTUM] Failed to initialize Binance: {e}")
        USE_REAL_API = False
else:
    logger.info("ℹ️  [QUANTUM] FALLBACK MODE - API key yok, deterministic test values kullaniliyor")

# Prometheus metrics
REQUEST_COUNT = Counter('quantum_requests_total', 'Total requests', ['method', 'endpoint'])
REQUEST_LATENCY = Histogram('quantum_request_duration_seconds', 'Request latency (seconds)', ['endpoint'])
ACTIVE_REQUESTS = Gauge('quantum_active_requests', 'Active requests')
MM_SPREAD = Gauge('quantum_spread_bps', 'Market-making spread (bps)')
MM_INVENTORY = Gauge('quantum_inventory', 'Current inventory')
QUANTUM_PNL = Gauge('quantum_pnl', 'Market-making PnL')
FUNDING_RATE_GAUGE = Gauge('quantum_funding_rate_pct', 'Binance Futures Funding Rate %')
OI_GAUGE = Gauge('quantum_open_interest_usdt', 'Open Interest in USDT')
LS_RATIO_GAUGE = Gauge('quantum_long_short_ratio', 'Global Long/Short Account Ratio')

# Store metric values
_metric_values = {
    'quantum_pnl': random.uniform(-10000, 50000),
    'quantum_spread_bps': random.uniform(0.5, 5),
}

futures_fetcher = FuturesFetcher()


def _get_futures_metrics(symbol: str) -> dict:
    """
    Return deterministic futures risk metrics for the requested symbol.

    Rule support:
    - funding_rate > 0.01 => BUY signal should be filtered.
    """
    sym = (symbol or "BTCUSDT").upper().strip()
    rng = random.Random(abs(hash(sym)) + 1703)

    funding_rate = round(rng.uniform(-0.005, 0.02), 6)
    open_interest_change_24h = round(rng.uniform(-0.25, 0.35), 4)

    if funding_rate > 0.01 or open_interest_change_24h > 0.2:
        liquidation_heatmap = "high"
    elif funding_rate > 0.004 or open_interest_change_24h > 0.08:
        liquidation_heatmap = "medium"
    else:
        liquidation_heatmap = "low"

    return {
        "funding_rate": funding_rate,
        "open_interest_change_24h": open_interest_change_24h,
        "liquidation_heatmap": liquidation_heatmap,
    }

# Initialize FastAPI app
def update_metrics_thread():
    """Background thread to update metrics every 10 seconds"""
    logger.info("Background metrics thread started (threading)")
    while True:
        try:
            pnl_val = random.uniform(-10000, 50000)
            spread_val = random.uniform(0.5, 5)
            inv_val = random.uniform(-1000, 1000)
            QUANTUM_PNL.set(pnl_val)
            MM_SPREAD.set(spread_val)
            MM_INVENTORY.set(inv_val)
            logger.info(f"Updated metrics: PnL={pnl_val:.0f}, Spread={spread_val:.2f}, Inv={inv_val:.0f}")
            time.sleep(10)
        except Exception as e:
            logger.error(f"Error updating metrics: {e}", exc_info=True)
            time.sleep(10)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown"""
    logger.info("Quantum AI Module starting up...")

    # Start background thread for metrics (daemon thread dies with app)
    thread = threading.Thread(target=update_metrics_thread, daemon=True)
    thread.start()
    logger.info("Background metrics thread started")

    yield

    logger.info("Quantum AI Module shutting down...")

app = FastAPI(
    title="Quantum AI Limited",
    description="Market-Making Engine with Avellaneda-Stoikov Algorithm",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "quantum-ai",
        "version": "1.0.0"
    }

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    # Get standard metrics (registered Gauge/Counter/Histogram values)
    base_metrics = generate_latest().decode()

    # Add only mode marker; avoid duplicating already-registered metric names.
    mode = "REAL" if USE_REAL_API else "MOCK"
    custom_metrics = (
        f"# HELP quantum_mode Operating mode (REAL API or MOCK data)\n"
        f"# TYPE quantum_mode gauge\n"
        f"quantum_mode{{mode=\"{mode}\"}} 1\n"
    )

    return Response(content=base_metrics + custom_metrics, media_type=CONTENT_TYPE_LATEST)

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Quantum AI Limited",
        "description": "Market-Making Engine",
        "endpoints": {
            "health": "/health",
            "metrics": "/metrics",
            "docs": "/docs"
        }
    }


@app.post("/executor/liquidity_check")
async def liquidity_check(payload: dict):
    """Protocol endpoint: Quantum AI -> Executor liquidity sufficiency check."""
    depth_usd = float(payload.get("depth_usd", random.uniform(200000, 1500000)))
    spread_pct = float(payload.get("spread_pct", random.uniform(0.02, 0.25)))
    is_sufficient = depth_usd >= 500000 and spread_pct <= 0.1

    symbol = str(payload.get("symbol", "BTCUSDT"))
    metrics = _get_futures_metrics(symbol)
    funding_rate = float(metrics["funding_rate"])

    requested_signal = str(payload.get("signal", "HOLD")).upper().strip()
    filtered_signal = "HOLD" if requested_signal == "BUY" and funding_rate > 0.01 else requested_signal

    return {
        "depth_usd": depth_usd,
        "spread_pct": spread_pct,
        "is_sufficient": is_sufficient,
        "min_depth_required": 500000.0,
        "max_spread_allowed": 0.1,
        "funding_rate": funding_rate,
        "open_interest_change_24h": metrics["open_interest_change_24h"],
        "liquidation_heatmap": metrics["liquidation_heatmap"],
        "requested_signal": requested_signal,
        "filtered_signal": filtered_signal,
        "buy_filtered": requested_signal == "BUY" and filtered_signal != requested_signal,
    }


@app.get("/quantum/futures_metrics")
async def get_futures_metrics(symbol: str = "BTCUSDT"):
    """Return futures metrics for risk-aware signal filtering."""
    metrics = _get_futures_metrics(symbol)
    return {
        "funding_rate": metrics["funding_rate"],
        "open_interest_change_24h": metrics["open_interest_change_24h"],
        "liquidation_heatmap": metrics["liquidation_heatmap"],
    }


@app.get("/quantum/futures_data")
async def get_futures_data(symbol: str = "BTCUSDT"):
    """Fetch Binance futures metrics with cache and return consensus-ready modifier."""
    result = await futures_fetcher.get_futures_data(symbol=symbol)

    FUNDING_RATE_GAUGE.set(float(result.funding_rate_pct))
    OI_GAUGE.set(float(result.open_interest_usdt))
    LS_RATIO_GAUGE.set(float(result.long_short_ratio))

    payload = result.model_dump()
    # FIX: keep compatibility with consumers expecting generic "signal" field.
    payload["signal"] = payload.get("futures_signal", "CACHE_FALLBACK")
    return payload

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
