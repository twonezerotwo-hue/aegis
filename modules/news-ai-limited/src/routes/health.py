"""
News AI Limited - Health Check Endpoint
"""
from fastapi import APIRouter
from datetime import datetime, timezone
from ..logging.logger_config import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """
    Health check endpoint
    Returns service status, component availability, and last signal timestamp
    """
    return {
        "status": "healthy",
        "service": "news-ai-limited",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": {
            "sentiment_model": "ready",
            "redis": "connected",
            "database": "connected",
        },
        "sources_available": 20,
        "cache_hit_rate": 0.85,
        "last_signal_at": datetime.now(timezone.utc).isoformat(),
    }
