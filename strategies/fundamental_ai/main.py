"""
AEGIS v7.2 - Fundamental API live/proxy data mode.

Fundamental AI Limited - On-Chain Metrics Analysis API
LIVE_INTEGRATION: Glassnode async client with Redis cache and explicit unavailable states.
"""
from fastapi import FastAPI, Query, Response
from contextlib import asynccontextmanager
import asyncio
from datetime import datetime, timezone
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
except Exception:
    random.seed(42)
    if "np" in dir():
        np.random.seed(42)

load_dotenv()

try:
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Counter, Gauge, Histogram
except Exception:  # pragma: no cover - optional metrics dependency
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4"

    def generate_latest(*args, **kwargs):
        return b""

    class _NoOpMetric:
        def labels(self, *args, **kwargs):
            return self

        def inc(self, *args, **kwargs):
            return None

        def dec(self, *args, **kwargs):
            return None

        def set(self, *args, **kwargs):
            return None

        def observe(self, *args, **kwargs):
            return None

    def Counter(*args, **kwargs):
        return _NoOpMetric()

    def Gauge(*args, **kwargs):
        return _NoOpMetric()

    def Histogram(*args, **kwargs):
        return _NoOpMetric()

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

try:
    from strategies.fundamental_ai.services.glassnode_client import GlassnodeServiceClient
except ModuleNotFoundError:
    from services.glassnode_client import GlassnodeServiceClient  # type: ignore[no-redef]

_glassnode_client: Optional[GlassnodeServiceClient] = None

GLASSNODE_API_KEY = os.getenv("GLASSNODE_API_KEY", "").strip()
CRYPTOQUANT_API_KEY = os.getenv("CRYPTOQUANT_API_KEY", "").strip()
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()

USE_REAL_API = (
    (GLASSNODE_API_KEY and not GLASSNODE_API_KEY.startswith("your_"))
    or (CRYPTOQUANT_API_KEY and not CRYPTOQUANT_API_KEY.startswith("your_"))
    or (TWELVE_DATA_API_KEY and not TWELVE_DATA_API_KEY.startswith("your_"))
)

if USE_REAL_API:
    logger.info("[FUNDAMENTAL] REAL API MODE - on-chain data enabled")
else:
    logger.info("[FUNDAMENTAL] LIVE-PROXY MODE - public proxy sources active")

REQUEST_COUNT = Counter("fundamental_requests_total", "Total requests", ["method", "endpoint"])
REQUEST_LATENCY = Histogram("fundamental_request_duration_seconds", "Request latency (seconds)", ["endpoint"])
ACTIVE_REQUESTS = Gauge("fundamental_active_requests", "Active requests")
METRIC_QUALITY = Gauge("fundamental_metric_quality", "Metric quality score")
FUNDAMENTAL_SCORE = Gauge("fundamental_score", "Fundamental analysis score")

_metric_values = {
    "fundamental_score": None,
    "fundamental_metric_quality": None,
    "timestamp": None,
    "source": "uninitialized",
    "verified": False,
    "data_status": "UNKNOWN",
    "warning": "No fundamental snapshot fetched yet.",
}


def _service_mode() -> str:
    if _metric_values.get("data_status") == "LIVE":
        return "REAL"
    if _metric_values.get("data_status") == "RECENT":
        return "CACHE_REAL"
    return "UNAVAILABLE"


async def _refresh_metric_snapshot(symbol: str = "BTC") -> None:
    if _glassnode_client is None:
        _metric_values.update(
            {
                "fundamental_score": None,
                "fundamental_metric_quality": None,
                "timestamp": None,
                "source": "service_not_initialized",
                "verified": False,
                "data_status": "UNKNOWN",
                "warning": "Fundamental client not initialized.",
            }
        )
        return

    result = await _glassnode_client.fetch_metrics(symbol, ["mvrv", "nupl"])
    mvrv = result.get("mvrv_z_score")
    nupl = result.get("nupl")

    score = None
    quality = None
    if isinstance(mvrv, (int, float)) and isinstance(nupl, (int, float)):
        nupl_norm = min(max((float(nupl) + 0.5) / 1.5, 0.0), 1.0)
        mvrv_norm = min(max((4.0 - float(mvrv)) / 4.0, 0.0), 1.0)
        score = round((nupl_norm * 0.6 + mvrv_norm * 0.4) * 100.0, 2)
        quality = 95.0 if result.get("verified") else 75.0 if result.get("data_status") == "RECENT" else 0.0

    _metric_values.update(
        {
            "fundamental_score": score,
            "fundamental_metric_quality": quality,
            "timestamp": result.get("timestamp"),
            "source": result.get("source", "unavailable"),
            "verified": bool(result.get("verified")),
            "data_status": result.get("data_status", "MISSING"),
            "warning": " ".join(result.get("warnings", [])) or None,
        }
    )


def update_metrics_background() -> None:
    """Background thread to update Prometheus metrics every 60 seconds using live sources."""
    while True:
        try:
            asyncio.run(_refresh_metric_snapshot())
            if _metric_values.get("fundamental_score") is not None:
                FUNDAMENTAL_SCORE.set(float(_metric_values["fundamental_score"]))
            if _metric_values.get("fundamental_metric_quality") is not None:
                METRIC_QUALITY.set(float(_metric_values["fundamental_metric_quality"]))
            time.sleep(60)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error updating fundamental metrics: %s", exc)
            time.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _glassnode_client
    logger.info("Fundamental AI Module starting up...")
    _glassnode_client = GlassnodeServiceClient()
    if GLASSNODE_API_KEY:
        logger.info("[FUNDAMENTAL] Glassnode API key configured - LIVE mode active")
    elif TWELVE_DATA_API_KEY:
        logger.info("[FUNDAMENTAL] Twelve Data API key configured - LIVE fallback active")
    else:
        logger.info("[FUNDAMENTAL] API keys missing - CoinGecko public proxy active")

    thread = threading.Thread(target=update_metrics_background, daemon=True)
    thread.start()

    yield

    logger.info("Fundamental AI Module shutting down...")


app = FastAPI(
    title="Fundamental AI Limited",
    description="On-Chain Metrics Analysis Engine",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    glassnode_configured = bool(GLASSNODE_API_KEY)
    twelve_configured = bool(TWELVE_DATA_API_KEY)
    return {
        "status": "ok",
        "service": "fundamental-ai",
        "version": "1.0.0",
        "glassnode_configured": glassnode_configured,
        "twelve_data_configured": twelve_configured,
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
        "# HELP fundamental_mode Operating mode (REAL, CACHE_REAL, UNAVAILABLE)\n"
        "# TYPE fundamental_mode gauge\n"
        f'fundamental_mode{{mode="{_service_mode()}"}} 1\n'
    )
    return Response(content=base_metrics + custom_metrics, media_type=CONTENT_TYPE_LATEST)


@app.get("/")
async def root():
    return {
        "service": "Fundamental AI Limited",
        "description": "On-Chain Metrics Analysis",
        "endpoints": {
            "health": "/health",
            "metrics": "/metrics",
            "fundamental_metrics": "/fundamental/metrics",
            "docs": "/docs",
        },
    }


@app.get("/fundamental/metrics")
async def fundamental_metrics(
    symbol: str = Query(default="BTC", description="Asset symbol, e.g. BTC"),
    metrics: str = Query(
        default="mvrv,nupl",
        description="Comma-separated metric names: mvrv, nupl, transaction_volume, active_addresses",
    ),
) -> dict:
    global _glassnode_client
    metric_list: List[str] = [m.strip() for m in metrics.split(",") if m.strip()]

    if not os.getenv("GLASSNODE_API_KEY", "").strip():
        payload = {
            "symbol": symbol.upper(),
            "source": "mock",
            "quality": "mock",
            "verified": False,
            "fallback_used": True,
            "data_status": "MOCK",
            "warnings": ["GLASSNODE_API_KEY missing; explicit mock fundamental metrics returned."],
            "timestamp": None,
        }
        if "mvrv" in metric_list:
            payload["mvrv_z_score"] = 1.87
        if "nupl" in metric_list:
            payload["nupl"] = 0.34
        return payload

    if _glassnode_client is None:
        _glassnode_client = GlassnodeServiceClient()

    data = await _glassnode_client.fetch_metrics(symbol.upper(), metric_list)
    return data if isinstance(data, dict) else {"symbol": symbol.upper(), "source": "unavailable", "data_status": "UNKNOWN"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
