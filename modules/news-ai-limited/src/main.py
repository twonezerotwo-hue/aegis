"""
News AI Limited - Main FastAPI Application
"""
from fastapi import FastAPI
from fastapi.responses import Response
from contextlib import asynccontextmanager
import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from src.routes import health, analysis, signals, admin
from src.routes.news_runtime import build_live_news_signal
from src.logging.logger_config import configure_logging
from src.config import get_settings
from prometheus_client import generate_latest, Counter, Histogram, REGISTRY, Gauge
from src.data_sources.source_registry import SourceRegistry
from src.routes.admin import set_registry as _admin_set_registry

configure_logging()
settings = get_settings()

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

news_sentiment_score_gauge = Gauge(
    "news_sentiment_score",
    "Current news sentiment score (0-100)",
)


async def periodic_analysis_task(app: FastAPI):
    """Background task: periodically build a live news signal and update Prometheus gauge."""
    logger.info("Periodic news analysis task started")
    while True:
        try:
            registry = getattr(app.state, "registry", None)
            if registry is not None:
                result = await build_live_news_signal(
                    registry=registry,
                    period="24h",
                    countries=None,
                    limit=20,
                    horizon="medium",
                )
                if result.get("verified"):
                    signal = result["news_signal"]
                    news_sentiment_score_gauge.set(float(signal.crypto_impact_score))
            await asyncio.sleep(settings.news_update_interval_minutes * 60)
        except asyncio.CancelledError:
            logger.info("Periodic news analysis task cancelled")
            break
        except Exception as exc:  # noqa: BLE001
            logger.error("Error in periodic analysis task: %s", exc)
            await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[NEWS-AI] Startup: Initializing News AI Limited module")

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
        logger.info("[NEWS-AI] Dedup engine connected to Redis")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[NEWS-AI] Redis unavailable - dedup running in memory-only mode: %s", exc)

    _admin_set_registry(registry)
    app.state.registry = registry
    logger.info("[NEWS-AI] SourceRegistry initialized (%d sources)", len(registry.sources))

    background_task = asyncio.create_task(periodic_analysis_task(app))
    logger.info("[NEWS-AI] Background news analysis task started")

    yield

    logger.info("[NEWS-AI] Shutdown: Cleaning up connections")
    background_task.cancel()
    try:
        await background_task
    except asyncio.CancelledError:
        pass
    logger.info("[NEWS-AI] Shutdown complete")


app = FastAPI(
    title="News AI Limited",
    description="Regulatory & Market News Analysis for Crypto Markets",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(analysis.router)
app.include_router(signals.router)
app.include_router(admin.router)


@app.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(REGISTRY),
        media_type="text/plain; charset=utf-8",
    )


@app.get("/")
async def root():
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
