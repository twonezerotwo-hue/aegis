"""
News AI Limited - Analysis Endpoints
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional

from ..signal_models import NewsSignal
from ..logging.logger_config import get_logger
from .news_runtime import build_live_news_signal

logger = get_logger(__name__)

router = APIRouter(tags=["analysis"], prefix="/analyze")


class AnalysisRequest(BaseModel):
    period: str = "24h"
    countries: List[str] = ["USA", "China", "Russia", "Turkey"]
    crypto_symbols: Optional[List[str]] = None
    force_refresh: bool = False


class AnalysisResponse(BaseModel):
    news_signal: NewsSignal
    execution_time_ms: int
    source: str
    timestamp: Optional[str] = None
    verified: bool = False
    fallback_used: bool = False
    data_status: str = "UNKNOWN"
    warnings: List[str] = []


@router.post("", response_model=AnalysisResponse)
async def analyze_news(request: Request, payload: AnalysisRequest):
    import time

    start_time = time.time()
    try:
        logger.info(
            "news_analysis_triggered",
            period=payload.period,
            countries=payload.countries,
        )
        registry = getattr(request.app.state, "registry", None)
        result = await build_live_news_signal(
            registry=registry,
            period=payload.period,
            countries=payload.countries,
            limit=10,
            horizon=None,
        )
        execution_time = int((time.time() - start_time) * 1000)
        return AnalysisResponse(
            news_signal=result["news_signal"],
            execution_time_ms=execution_time,
            source=result["source"],
            timestamp=result.get("timestamp"),
            verified=result.get("verified", False),
            fallback_used=result.get("fallback_used", False),
            data_status=result.get("data_status", "UNKNOWN"),
            warnings=result.get("warnings", []),
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"news_analysis_error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
