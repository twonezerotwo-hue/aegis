"""
News AI Limited - Signals Retrieval Endpoints
AEGIS v7.1: horizon query param support (short/medium/long).
"""
from fastapi import APIRouter, Query
from datetime import datetime, timezone
from ..signal_models import NewsSignal, ImpactFactors
from ..logging.logger_config import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["signals"], prefix="/signals")

# Horizon → (window_days, analysis_period, source_priority)
_HORIZON_CONFIG: dict[str, dict] = {
    "short":  {"window_days": 7,  "analysis_period": "7d",  "source_priority": "breaking"},
    "medium": {"window_days": 30, "analysis_period": "30d", "source_priority": "trend"},
    "long":   {"window_days": 90, "analysis_period": "90d", "source_priority": "macro"},
}
_VALID_HORIZONS = {"short", "medium", "long"}


@router.get("", response_model=dict)
async def get_signals(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    period: str = Query("24h"),
    horizon: str = Query("medium", description="Investment horizon: short | medium | long"),
):
    """
    Retrieve recent news signals from the system.

    When `horizon` is supplied the analysis window and source priority are
    adjusted automatically: short→7d/breaking, medium→30d/trend, long→90d/macro.
    Returns paginated list of NewsSignal objects with metadata.
    """
    if horizon not in _VALID_HORIZONS:
        horizon = "medium"

    hcfg = _HORIZON_CONFIG[horizon]
    # Horizon overrides the raw `period` param so all downstream callers get
    # the correct analysis window for the selected investment horizon.
    effective_period = hcfg["analysis_period"]
    source_priority  = hcfg["source_priority"]

    logger.info(
        "signals_retrieved",
        limit=limit,
        offset=offset,
        period=effective_period,
        horizon=horizon,
        source_priority=source_priority,
    )

    # TODO: Fetch from database/cache
    # For now, return mock signals
    impact_factors = ImpactFactors(
        regulatory_score=72.5,
        market_mention_score=65.0,
        source_credibility=90.0,
        temporal_decay=0.85,
        sentiment_multiplier=1.05,
    )

    sample_signal = NewsSignal(
        signal_type="NEWS",
        timestamp=datetime.now(timezone.utc),
        module_id="news-ai-limited-v1",
        crypto_impact_score=72.5,
        confidence_level=85.0,
        news_items_count=47,
        analysis_period=effective_period,
        primary_countries=["USA", "China"],
        impact_factors=impact_factors,
        top_news_items=[],
        aggregated_sentiment=0.15,
        version="1.0",
    )

    return {
        "signals": [sample_signal],
        "total_count": 1,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total_pages": 1,
        },
        "horizon_applied": horizon,
        "source_priority": source_priority,
        "window_days": hcfg["window_days"],
    }
