"""
News AI Limited - Signals Retrieval Endpoints
AEGIS v7.1: horizon query param support (short/medium/long).
"""
from fastapi import APIRouter, Query, Request

from ..logging.logger_config import get_logger
from .news_runtime import build_live_news_signal

logger = get_logger(__name__)

router = APIRouter(tags=["signals"], prefix="/signals")

_HORIZON_CONFIG: dict[str, dict] = {
    "short": {"window_days": 7, "analysis_period": "7d", "source_priority": "breaking"},
    "medium": {"window_days": 30, "analysis_period": "30d", "source_priority": "trend"},
    "long": {"window_days": 90, "analysis_period": "90d", "source_priority": "macro"},
}
_VALID_HORIZONS = {"short", "medium", "long"}


@router.get("", response_model=dict)
async def get_signals(
    request: Request,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    period: str = Query("24h"),
    horizon: str = Query("medium", description="Investment horizon: short | medium | long"),
):
    if horizon not in _VALID_HORIZONS:
        horizon = "medium"

    hcfg = _HORIZON_CONFIG[horizon]
    effective_period = hcfg["analysis_period"]
    source_priority = hcfg["source_priority"]

    logger.info(
        "signals_retrieved",
        limit=limit,
        offset=offset,
        period=effective_period,
        horizon=horizon,
        source_priority=source_priority,
    )

    registry = getattr(request.app.state, "registry", None)
    result = await build_live_news_signal(
        registry=registry,
        period=effective_period,
        countries=None,
        limit=limit,
        horizon=horizon,
    )
    signal = result["news_signal"]

    return {
        "signals": [signal.model_dump(mode="json")],
        "total_count": 1 if result.get("verified") else 0,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total_pages": 1,
        },
        "horizon_applied": horizon,
        "source_priority": source_priority,
        "window_days": hcfg["window_days"],
        "source": result["source"],
        "timestamp": result.get("timestamp"),
        "verified": result.get("verified", False),
        "fallback_used": result.get("fallback_used", False),
        "data_status": result.get("data_status", "UNKNOWN"),
        "warnings": result.get("warnings", []),
    }
