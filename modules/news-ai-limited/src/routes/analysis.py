"""
News AI Limited - Analysis Endpoints
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone
from ..signal_models import NewsSignal, ImpactFactors
from ..logging.logger_config import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["analysis"], prefix="/analyze")


class AnalysisRequest(BaseModel):
    """Request model for POST /analyze"""
    period: str = "24h"  # realtime, 1h, 24h, 7d
    countries: List[str] = ["USA", "China", "Russia", "Turkey"]
    crypto_symbols: Optional[List[str]] = None
    force_refresh: bool = False


class AnalysisResponse(BaseModel):
    """Response model for POST /analyze"""
    news_signal: NewsSignal
    execution_time_ms: int


@router.post("", response_model=AnalysisResponse)
async def analyze_news(request: AnalysisRequest):
    """
    Trigger news analysis for specified period and countries

    Returns NewsSignal object with crypto_impact_score (0-100) and confidence_level.
    This signal is published to Consensus Engine.
    """
    import time
    start_time = time.time()

    try:
        logger.info(
            "news_analysis_triggered",
            period=request.period,
            countries=request.countries,
        )

        # TODO: Call actual analysis pipeline
        # For now, return mock signal
        impact_factors = ImpactFactors(
            regulatory_score=72.5,
            market_mention_score=65.0,
            source_credibility=90.0,
            temporal_decay=0.85,
            sentiment_multiplier=1.05,
        )

        news_signal = NewsSignal(
            signal_type="NEWS",
            timestamp=datetime.now(timezone.utc),
            module_id="news-ai-limited-v1",
            crypto_impact_score=72.5,
            confidence_level=85.0,
            news_items_count=47,
            analysis_period=request.period,
            primary_countries=request.countries,
            impact_factors=impact_factors,
            top_news_items=[],
            aggregated_sentiment=0.15,
            version="1.0",
        )

        execution_time = int((time.time() - start_time) * 1000)

        return AnalysisResponse(
            news_signal=news_signal,
            execution_time_ms=execution_time,
        )

    except Exception as e:
        logger.error(f"news_analysis_error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
