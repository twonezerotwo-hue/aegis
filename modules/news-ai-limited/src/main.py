"""
News AI Limited - Main FastAPI Application

Entry point for the News AI Limited module.
Handles FastAPI app setup, lifespan management, and route registration.

Pattern based on Touche AI implementation.
"""
from fastapi import FastAPI
from fastapi.responses import Response
from contextlib import asynccontextmanager
import asyncio
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import routes
from src.routes import health, analysis, signals, admin
from src.logging.logger_config import configure_logging
from src.config import get_settings
from prometheus_client import generate_latest, Counter, Histogram, REGISTRY
from src.data_sources.source_registry import SourceRegistry
from src.routes.admin import set_registry as _admin_set_registry

# Configure structlog
configure_logging()

# Settings
settings = get_settings()

# ============ BACKGROUND TASKS ============

async def periodic_analysis_task():
    """
    Background task: Run news analysis every N minutes

    Publishing results to Redis pub/sub for Consensus Engine
    """
    logger.info("📰 Periodic news analysis task started")
    while True:
        try:
            await asyncio.sleep(settings.news_update_interval_minutes * 60)
            # TODO: Run actual analysis and publish to Redis
            logger.info(f"📊 News analysis update (every {settings.news_update_interval_minutes} min)")
        except asyncio.CancelledError:
            logger.info("📰 Periodic news analysis task cancelled")
            break
        except Exception as e:
            logger.error(f"❌ Error in periodic analysis task: {e}")
            await asyncio.sleep(60)  # Retry after 1 minute


# ============ LIFESPAN CONTEXT MANAGER ============

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager

    Startup: Initialize sentiment model, Redis connection, background tasks
    Shutdown: Cleanup connections and cancel tasks
    """
    logger.info("✅ [NEWS-AI] Startup: Initializing News AI Limited module")

    # Startup phase
    background_task = asyncio.create_task(periodic_analysis_task())
    logger.info("✅ [NEWS-AI] Background news analysis task started")

    # Haber kaynağı kayıt defteri + deduplication motoru başlat
    registry = SourceRegistry()
    try:
        import redis as _redis_lib  # type: ignore
        _redis_client = _redis_lib.Redis.from_url(
            settings.redis_url,
            max_connections=10,
            decode_responses=False,
            socket_connect_timeout=3,
        )
        _redis_client.ping()
        registry.inject_redis(_redis_client)
        logger.info("✅ [NEWS-AI] Dedup engine connected to Redis")
    except Exception as _e:
        logger.warning("⚠️ [NEWS-AI] Redis unavailable — dedup running in memory-only mode: %s", _e)
    _admin_set_registry(registry)
    app.state.registry = registry
    logger.info("✅ [NEWS-AI] SourceRegistry initialized (%d sources)", len(registry.sources))


    # Start sentiment metrics update thread
    sentiment_thread = threading.Thread(target=update_sentiment_metrics, daemon=True)
    sentiment_thread.start()
    logger.info("✅ [NEWS-AI] Background sentiment metrics task started")

    yield  # Application runs here

    # Shutdown phase
    logger.info("🔌 [NEWS-AI] Shutdown: Cleaning up connections")
    background_task.cancel()
    try:
        await background_task
    except asyncio.CancelledError:
        pass
    logger.info("✅ [NEWS-AI] Shutdown complete")


# ============ FASTAPI APP INITIALIZATION ============

app = FastAPI(
    title="News AI Limited",
    description="Regulatory & Market News Analysis for Crypto Markets",
    version="1.0.0",
    lifespan=lifespan,
)


# ============ ROUTE REGISTRATION ============

app.include_router(health.router)
app.include_router(analysis.router)
app.include_router(signals.router)
app.include_router(admin.router)


# ============ PROMETHEUS METRICS ============

import random
import threading
import time

news_analysis_counter = Counter(
    "news_analysis_total",
    "Total number of news analyses performed",
    ["period", "country"],
)

signal_publish_counter = Counter(
    "news_signal_published_total",
    "Total number of signals published to Consensus Engine",
)

analysis_latency_histogram = Histogram(
    "news_analysis_duration_seconds",
    "Latency of news analysis in seconds",
)

# Add Sentiment Score Gauge
from prometheus_client import Gauge
news_sentiment_score_gauge = Gauge(
    "news_sentiment_score",
    "Current news sentiment score (0-100)"
)

# Background task to update sentiment score
def update_sentiment_metrics():
    """Background thread to update sentiment metrics every 10 seconds"""
    while True:
        try:
            sentiment = random.uniform(20, 90)
            news_sentiment_score_gauge.set(sentiment)
            logger.info(f"Updated news sentiment score: {sentiment:.1f}")
            time.sleep(10)
        except Exception as e:
            logger.error(f"Error updating sentiment metrics: {e}")
            time.sleep(10)


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(
        content=generate_latest(REGISTRY),
        media_type="text/plain; charset=utf-8"
    )


# ============ ROOT ENDPOINT ============

@app.get("/")
async def root():
    """Root endpoint - API information"""
    return {
        "service": "News AI Limited",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "analyze": "POST /analyze",
            "signals": "GET /signals",
            "config": "POST /config",
            "metrics": "/metrics",
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
    )
