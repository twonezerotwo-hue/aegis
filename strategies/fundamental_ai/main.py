"""
AEGIS v7.2 — Fundamental API canli/fallback veri modu.

Fundamental AI Limited - On-Chain Metrics Analysis API
LIVE_INTEGRATION: Glassnode async client with Redis cache and mock fallback.
"""
from fastapi import FastAPI, Query, Response
from contextlib import asynccontextmanager
import logging
import random
import numpy as np
import threading
import time
import os
from typing import List, Optional
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

from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Counter, Gauge, Histogram

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# LIVE_INTEGRATION: Glassnode service client
try:
    from strategies.fundamental_ai.services.glassnode_client import GlassnodeServiceClient
except ModuleNotFoundError:
    # Inside Docker: code is at /app/fundamental_ai/
    from services.glassnode_client import GlassnodeServiceClient  # type: ignore[no-redef]

_glassnode_client: Optional[GlassnodeServiceClient] = None

# ============ ON-CHAIN DATA API INITIALIZATION ============
GLASSNODE_API_KEY = os.getenv('GLASSNODE_API_KEY', '').strip()
CRYPTOQUANT_API_KEY = os.getenv('CRYPTOQUANT_API_KEY', '').strip()
TWELVE_DATA_API_KEY = os.getenv('TWELVE_DATA_API_KEY', '').strip()

# Determine if using real APIs or mock data
USE_REAL_API = (
    (GLASSNODE_API_KEY and not GLASSNODE_API_KEY.startswith('your_'))
    or (CRYPTOQUANT_API_KEY and not CRYPTOQUANT_API_KEY.startswith('your_'))
    or (TWELVE_DATA_API_KEY and not TWELVE_DATA_API_KEY.startswith('your_'))
)

if USE_REAL_API:
    logger.info("✅ [FUNDAMENTAL] REAL API MODE - On-chain data enabled")
    GLASSNODE_BASE_URL = "https://api.glassnode.com/v1"
    CRYPTOQUANT_BASE_URL = "https://api.cryptoquant.com/v1"
else:
    logger.info("ℹ️  [FUNDAMENTAL] FALLBACK MODE - API key yok, deterministic test values")
    GLASSNODE_BASE_URL = None
    CRYPTOQUANT_BASE_URL = None

# Prometheus metrics
REQUEST_COUNT = Counter('fundamental_requests_total', 'Total requests', ['method', 'endpoint'])
REQUEST_LATENCY = Histogram('fundamental_request_duration_seconds', 'Request latency (seconds)', ['endpoint'])
ACTIVE_REQUESTS = Gauge('fundamental_active_requests', 'Active requests')
METRIC_QUALITY = Gauge('fundamental_metric_quality', 'Metric quality score')
FUNDAMENTAL_SCORE = Gauge('fundamental_score', 'Fundamental analysis score')

# Store metric values
_metric_values = {
    'fundamental_score': random.uniform(20, 95),
    'fundamental_metric_quality': random.uniform(0, 100),
}

async def _fetch_coingecko_score(symbol: str = "BTC") -> tuple:
    """Fetch real fundamental score from CoinGecko free API."""
    coin_map = {"BTC": "bitcoin", "ETH": "ethereum", "BNB": "binancecoin", "SOL": "solana"}
    coin_id = coin_map.get(symbol.upper(), "bitcoin")
    try:
        import httpx as _httpx
        async with _httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={
                    "ids": coin_id,
                    "vs_currencies": "usd",
                    "include_market_cap": "true",
                    "include_24hr_vol": "true",
                    "include_24hr_change": "true",
                    "include_7d_change": "true",
                },
            )
            resp.raise_for_status()
            data = resp.json().get(coin_id, {})
        change_24h = float(data.get("usd_24h_change") or 0.0)
        change_7d = float(data.get("usd_7d_change") or 0.0)
        vol = float(data.get("usd_24h_vol") or 0.0)
        mcap = float(data.get("usd_market_cap") or 1.0)
        vol_mcap = min(vol / max(mcap, 1.0), 0.1) / 0.1
        price_score = min(max((change_24h + 10) / 20 * 100, 0), 100)
        trend_score = min(max((change_7d + 20) / 40 * 100, 0), 100)
        volume_score = vol_mcap * 100
        score = round(price_score * 0.4 + volume_score * 0.3 + trend_score * 0.3, 1)
        return score, 95.0
    except Exception as e:
        logger.warning(f"CoinGecko fetch failed: {e}")
        return None, None


def update_metrics_background():
    """Background thread to update Prometheus metrics every 60 seconds using CoinGecko."""
    while True:
        try:
            result = asyncio.run(_fetch_coingecko_score())
            fundamental_value, quality_value = result if result[0] is not None else (
                _metric_values.get('fundamental_score', 50.0), 60.0
            )

            FUNDAMENTAL_SCORE.set(fundamental_value)
            METRIC_QUALITY.set(quality_value)
            _metric_values['fundamental_score'] = fundamental_value
            _metric_values['fundamental_metric_quality'] = quality_value

            logger.info(f"CoinGecko metrics updated: Score={fundamental_value:.1f}, Quality={quality_value:.1f}")
            time.sleep(60)
        except Exception as e:
            logger.error(f"Error updating metrics: {e}")
            time.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown"""
    global _glassnode_client
    logger.info("Fundamental AI Module starting up...")
    # LIVE_INTEGRATION: initialise Glassnode client
    _glassnode_client = GlassnodeServiceClient()
    if os.getenv("GLASSNODE_API_KEY", ""):
        logger.info("[FUNDAMENTAL] Glassnode API key configured – LIVE mode active")
    elif os.getenv("TWELVE_DATA_API_KEY", ""):
        logger.info("[FUNDAMENTAL] Twelve Data API key configured – LIVE fallback active")
    else:
        logger.info("[FUNDAMENTAL] API keys missing – deterministic fallback active")

    # Start background thread
    thread = threading.Thread(target=update_metrics_background, daemon=True)
    thread.start()

    yield

    logger.info("Fundamental AI Module shutting down...")

app = FastAPI(
    title="Fundamental AI Limited",
    description="On-Chain Metrics Analysis Engine",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    glassnode_configured = bool(os.getenv("GLASSNODE_API_KEY", ""))
    twelve_configured = bool(os.getenv("TWELVE_DATA_API_KEY", ""))
    return {
        "status": "ok",
        "service": "fundamental-ai",
        "version": "1.0.0",
        "glassnode_configured": glassnode_configured,
        "twelve_data_configured": twelve_configured,
        "data_mode": "LIVE" if (glassnode_configured or twelve_configured) else "MOCK",
    }

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    # Get standard metrics (registered Gauge/Counter/Histogram values)
    base_metrics = generate_latest().decode()

    # Add only mode marker; avoid duplicating already-registered metric names.
    mode = "REAL" if USE_REAL_API else "MOCK"
    custom_metrics = (
        f"# HELP fundamental_mode Operating mode (REAL API or MOCK data)\n"
        f"# TYPE fundamental_mode gauge\n"
        f"fundamental_mode{{mode=\"{mode}\"}} 1\n"
    )

    return Response(content=base_metrics + custom_metrics, media_type=CONTENT_TYPE_LATEST)

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Fundamental AI Limited",
        "description": "On-Chain Metrics Analysis",
        "endpoints": {
            "health": "/health",
            "metrics": "/metrics",
            "fundamental_metrics": "/fundamental/metrics",
            "docs": "/docs"
        }
    }


@app.get("/fundamental/metrics")
async def fundamental_metrics(
    symbol: str = Query(default="BTC", description="Asset symbol, e.g. BTC"),
    metrics: str = Query(
        default="mvrv,nupl",
        description="Comma-separated metric names: mvrv, nupl, transaction_volume, active_addresses",
    ),
) -> dict:
    """
    Fetch on-chain metrics for a symbol.
    LIVE_INTEGRATION: Uses GlassnodeServiceClient; falls back to mock if no API key.

    Example: GET /fundamental/metrics?symbol=BTC&metrics=mvrv,nupl
    """
    if _glassnode_client is None:
        return {"error": "service_not_initialized", "status": 503}

    metric_list: List[str] = [m.strip() for m in metrics.split(",") if m.strip()]
    result = await _glassnode_client.fetch_metrics(symbol.upper(), metric_list)
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
