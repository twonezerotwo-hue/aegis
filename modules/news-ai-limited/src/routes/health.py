"""
News AI Limited - Health Check Endpoint
"""
from fastapi import APIRouter, Request
from datetime import datetime, timezone

from ..logging.logger_config import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(request: Request):
    registry = getattr(request.app.state, "registry", None)
    summary = registry.get_health_summary() if registry is not None else {}
    sources_available = int(summary.get("healthy_sources", 0))
    enabled_sources = int(summary.get("enabled_sources", 0))
    timestamp = datetime.now(timezone.utc).isoformat()
    return {
        "status": "healthy" if registry is not None else "degraded",
        "service": "news-ai-limited",
        "version": "1.0.0",
        "timestamp": timestamp,
        "components": {
            "source_registry": "ready" if registry is not None else "missing",
            "rss_sources": "ready" if enabled_sources > 0 else "degraded",
            "official_sources": "ready" if sources_available > 0 else "degraded",
        },
        "sources_available": sources_available,
        "enabled_sources": enabled_sources,
        "cache_hit_rate": None,
        "last_signal_at": None,
    }
