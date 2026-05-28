"""
Pydantic models for AEGIS Analyzer
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict


class ModuleScore(BaseModel):
    """Single module analysis result"""
    name: str
    score: float = Field(..., ge=0, le=100)
    signal: str  # BULLISH, BEARISH, NEUTRAL
    confidence: float = Field(..., ge=0, le=1)


class AnalysisRequest(BaseModel):
    """Request to analyze market"""
    symbol: str = Field(default="BTC/USDT", description="Trading pair")
    timeframe: str = Field(default="4h", description="Analysis timeframe")

    # Module scores (optional, defaults to 50)
    touche: Optional[float] = Field(default=50, ge=0, le=100)
    fundamental: Optional[float] = Field(default=50, ge=0, le=100)
    quantum: Optional[float] = Field(default=50, ge=0, le=100)
    sentinel: Optional[float] = Field(default=50, ge=0, le=100)
    news: Optional[float] = Field(default=50, ge=0, le=100)


class ReportData(BaseModel):
    """Detailed analysis report"""
    weighted_score: float
    module_scores: Dict[str, float]
    recommendation: str
    confidence: float
    reason: str
    analysis_time: str


class AnalysisResponse(BaseModel):
    """Response with analysis results"""
    success: bool
    symbol: str
    timeframe: str

    # Recommendation
    recommendation: str  # BUY, SELL, HOLD
    confidence: float
    reason: str

    # Individual scores
    touche_score: float
    fundamental_score: float
    quantum_score: float
    sentinel_score: float
    news_score: float

    # Full report
    report: Optional[Dict] = None
    timestamp: str


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    version: str
    timestamp: str


class ReportResponse(BaseModel):
    """Text report response"""
    success: bool
    symbol: str
    timeframe: str
    report: str
    data: Optional[Dict] = None
    timestamp: str
