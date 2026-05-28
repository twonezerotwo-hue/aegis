"""
Sentinel AI — Data Models

Pydantic modelleri makro ekonomik veriler için.
"""
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict


class MarketRegime(str, Enum):
    """Market regimes."""
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    STAGFLATION = "STAGFLATION"
    NEUTRAL = "NEUTRAL"
    PANIC = "PANIC"


class MacroIndicatorType(str, Enum):
    """Macro indicator types."""
    VIX = "VIX"
    DXY = "DXY"
    FEAR_GREED = "FEAR_GREED"
    FED_RATES = "FED_RATES"
    OIL_PRICES = "OIL_PRICES"


class MacroIndicator(BaseModel):
    """Single macro indicator reading."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    indicator_type: MacroIndicatorType
    value: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str
    metadata: Dict[str, Any] = {}


class VIXIndicator(BaseModel):
    """VIX (Volatility Index) indicator."""
    value: float  # VIX index level
    change_pct: float  # % change from previous
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    regime: str = "NORMAL"  # NORMAL, FEAR, EXTREME_FEAR


class DXYIndicator(BaseModel):
    """DXY (Dollar Index) indicator."""
    value: float  # DXY level
    change_pct: float  # % change
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    strength: str = "NEUTRAL"  # WEAK, NEUTRAL, STRONG


class FearGreedIndicator(BaseModel):
    """Fear & Greed Index indicator."""
    value: float  # 0-100 scale
    classification: str  # Extreme Fear, Fear, Neutral, Greed, Extreme Greed
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    components: Dict[str, float] = {}  # Individual component scores


class FedRatesIndicator(BaseModel):
    """Federal Reserve rates indicator."""
    current_rate: float  # Current FFR %
    trend: str = "STABLE"  # RISING, FALLING, STABLE
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    next_meeting: Optional[datetime] = None


class OilPricesIndicator(BaseModel):
    """Oil prices indicator (WTI)."""
    price_usd: float  # WTI price per barrel
    change_pct: float  # % change
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    trend: str = "NEUTRAL"  # UP, DOWN, NEUTRAL


class RiskMultiplier(BaseModel):
    """Risk multiplier calculation result."""
    value: float  # 0.1-1.0
    regime: MarketRegime
    components: Dict[str, float]  # {indicator: contribution}
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reasoning: str = ""
    signal_strength: float = 0.0  # 0-1, confidence in multiplier
    hedge_required: bool = False
    macro_note: str = ""


class SentinelDecision(BaseModel):
    """Final Sentinel AI decision."""
    risk_multiplier: RiskMultiplier
    recommendation: str  # REDUCE_SIZE, MAINTAIN, INCREASE_SIZE
    confidence: float  # 0-1
    market_regime: MarketRegime
    alerts: list = []
    metrics: Dict[str, Any] = {}
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
