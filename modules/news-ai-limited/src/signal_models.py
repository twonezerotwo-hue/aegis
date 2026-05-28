"""
News AI Limited - Signal Models (Pydantic)

Defines NewsItem, ImpactFactors, and NewsSignal models for consumption by Consensus Engine.
NewsSignal format mirrors ToucheSignal and FundamentalSignal for seamless integration.
"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional
import uuid


class NewsItem(BaseModel):
    """Individual news article/statement"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str
    content: str  # First 1000 characters
    source_url: str
    source_name: str  # "Treasury.gov", "Reuters", "PBOC Announce", "CoinDesk", etc.
    published_at: datetime
    fetched_at: datetime
    country: str  # "USA", "China", "Russia", "Turkey"
    category: str  # "regulatory", "market_impact", "infrastructure", "adoption"
    sentiment_score: float = Field(ge=-1.0, le=1.0)  # -1.0 to 1.0
    sentiment_label: str  # "negative", "neutral", "positive"

    class Config:
        json_schema_extra = {
            "example": {
                "id": "abc123",
                "title": "Federal Reserve Issues Digital Currency Guidance",
                "content": "The Fed announced...",
                "source_url": "https://federalreserve.gov/news/article123",
                "source_name": "Federal Reserve",
                "published_at": "2026-04-13T10:30:00Z",
                "fetched_at": "2026-04-13T11:00:00Z",
                "country": "USA",
                "category": "regulatory",
                "sentiment_score": 0.25,
                "sentiment_label": "positive"
            }
        }


class ImpactFactors(BaseModel):
    """Impact scoring components (weighted calculation)"""
    regulatory_score: float = Field(ge=0, le=100)
    market_mention_score: float = Field(ge=0, le=100)
    source_credibility: float = Field(ge=0, le=100)
    temporal_decay: float = Field(ge=0.0, le=1.0)  # 0.0-1.0, decays over 72 hours
    sentiment_multiplier: float = Field(ge=0.7, le=1.3)  # 0.7-1.3x modifier

    class Config:
        json_schema_extra = {
            "example": {
                "regulatory_score": 85,
                "market_mention_score": 70,
                "source_credibility": 95,
                "temporal_decay": 0.92,
                "sentiment_multiplier": 1.1
            }
        }


class NewsSignal(BaseModel):
    """
    Signal published to Consensus Engine via Redis Pub/Sub.

    Format mirrors ToucheSignal (EQS score) and FundamentalSignal (score).
    Consensus Engine combines: Touche 33.3% + Fundamental 33.3% + News 33.3%
    """
    signal_type: str = "NEWS"
    timestamp: datetime
    module_id: str = "news-ai-limited-v1"

    # PRIMARY METRICS FOR CONSENSUS ENGINE (0-100 scale)
    crypto_impact_score: float = Field(ge=0, le=100, description="Main signal: 0-100, like EQS score")
    confidence_level: float = Field(ge=0, le=100, description="Signal reliability: 0-100")

    # METADATA FOR AUDIT & ANALYSIS
    news_items_count: int = Field(ge=0, description="Number of news items analyzed")
    analysis_period: str  # "realtime", "1h", "24h", "7d"
    primary_countries: List[str]  # e.g., ["USA", "China"]
    impact_factors: ImpactFactors

    # RAW DATA FOR DEBUGGING
    top_news_items: List[NewsItem] = Field(default_factory=list, max_items=10)
    aggregated_sentiment: float = Field(ge=-1.0, le=1.0, description="Average sentiment across all items")

    # VERSIONING & TRACEABILITY
    version: str = "1.0"
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    class Config:
        json_schema_extra = {
            "example": {
                "signal_type": "NEWS",
                "timestamp": "2026-04-13T12:00:00Z",
                "module_id": "news-ai-limited-v1",
                "crypto_impact_score": 72.5,
                "confidence_level": 85,
                "news_items_count": 47,
                "analysis_period": "24h",
                "primary_countries": ["USA", "China"],
                "impact_factors": {
                    "regulatory_score": 75,
                    "market_mention_score": 65,
                    "source_credibility": 90,
                    "temporal_decay": 0.85,
                    "sentiment_multiplier": 1.05
                },
                "aggregated_sentiment": 0.15,
                "version": "1.0",
                "correlation_id": "abc123def456"
            }
        }


class NewsSignalUpdate(BaseModel):
    """Signal published to Redis for Consensus Engine subscription"""
    signal: NewsSignal
    action: str = Field(default="UPDATE", description="UPDATE or ALERT")
    alert_severity: Optional[str] = Field(default=None, description="LOW, MEDIUM, HIGH")

    class Config:
        json_schema_extra = {
            "example": {
                "signal": {},
                "action": "UPDATE",
                "alert_severity": None
            }
        }
