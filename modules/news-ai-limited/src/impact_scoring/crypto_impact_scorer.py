"""
News AI Limited - Impact Scoring System

Calculates impact score (0-100) based on:
1. Sentiment strength
2. Regulatory importance
3. Market mention frequency
4. Source credibility
5. Temporal decay (recent = higher impact)

Formula:
impact_score = (
    sentiment_factor * 20 +          (0-20)
    regulatory_factor * 25 +         (0-25)
    market_mention_factor * 20 +     (0-20)
    credibility_factor * 20 +        (0-20)
    temporal_factor * 15              (0-15)
) * decay_factor
"""

from typing import Dict, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import math
import numpy as np
from ..signal_models import NewsItem
from .sentiment_engine import SentimentScore, SentimentLabel
from ..logging.logger_config import get_logger

logger = get_logger(__name__)


class RegulatoryLevel(int, Enum):
    """Regulatory importance level"""
    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class SourceCredibility(float, Enum):
    """Source credibility score (0-1)"""
    UNRELIABLE = 0.3
    LOW = 0.5
    MEDIUM = 0.7
    HIGH = 0.85
    OFFICIAL = 0.95


@dataclass
class ImpactFactors:
    """Individual impact factors breakdown"""
    sentiment_factor: float  # 0-20
    regulatory_factor: float  # 0-25
    market_mention_factor: float  # 0-20
    credibility_factor: float  # 0-20
    temporal_factor: float  # 0-15
    decay_factor: float  # Exponential decay (0-1)


@dataclass
class ImpactScore:
    """Complete impact scoring result"""
    news_id: str
    impact_score: float  # 0-100
    factors: ImpactFactors
    sentiment: SentimentLabel
    regulatory_level: RegulatoryLevel
    source_credibility: SourceCredibility
    direction: str  # "BULLISH", "BEARISH", "NEUTRAL"
    magnitude: str  # "CRITICAL", "HIGH", "MEDIUM", "LOW"
    ttl_minutes: int  # Time to live (minutes)
    calculated_at: datetime


class CryptoRegulatoryKeywords:
    """
    Regulatory triggers that increase impact score
    Organized by severity
    """

    CRITICAL_TERMS = {
        # Direct crypto regulation
        "bitcoin ban",
        "cryptocurrency ban",
        "stablecoin regulation",
        "cbdc launch",
        "fed digital currency",
        "sec enforcement",
        "cftc enforcement",
        # Exchange closures
        "exchange shutdown",
        "delisting",
        "defi regulation",
        # Security incidents
        "exchange hack",
        "security breach",
        "10 billion loss",
        # Government actions
        "executive order crypto",
        "legislative bill crypto",
        "sanctions crypto",
    }

    HIGH_TERMS = {
        # Regulatory discussions
        "crypto regulation",
        "regulatory framework",
        "compliance requirement",
        "aml kyc",
        "anti-money laundering",
        "regulatory approval",
        # Market impact
        "market manipulation",
        "insider trading",
        "price rigging",
        # Minor bans
        "mining ban",
        "staking restriction",
    }

    MEDIUM_TERMS = {
        # Central bank discussions
        "central bank digital",
        "cbdc pilot",
        "fed policy",
        "imf report",
        "world bank",
        # Corporate action
        "company acquisition",
        "company investment",
        "partnership announcement",
        # Technical upgrades
        "network upgrade",
        "protocol update",
        "fork",
    }

    LOW_TERMS = {
        # General discussion
        "cryptocurrency discussion",
        "crypto news",
        "bitcoin analysis",
        "ethereum update",
        # Minor events
        "price forecast",
        "analyst prediction",
        "market analysis",
    }


class ImpactScoringEngine:
    """
    Calculates impact score for news items

    Impact combines multiple factors to determine:
    - How much this news matters for trading
    - How long the impact persists
    - Bullish vs bearish direction
    """

    def __init__(self):
        """Initialize impact scoring engine"""
        self.regulatory_keywords = CryptoRegulatoryKeywords()
        self.source_credibility_map = self._build_source_credibility_map()

    def _build_source_credibility_map(self) -> Dict[str, SourceCredibility]:
        """Build source name → credibility mapping"""
        return {
            # Official sources (highest)
            "Treasury.gov": SourceCredibility.OFFICIAL,
            "SEC Announcements": SourceCredibility.OFFICIAL,
            "CFTC": SourceCredibility.OFFICIAL,
            "PBOC": SourceCredibility.OFFICIAL,
            "TCMB": SourceCredibility.OFFICIAL,
            "Federal Reserve": SourceCredibility.OFFICIAL,
            # Major news organizations
            "Reuters": SourceCredibility.HIGH,
            "Bloomberg": SourceCredibility.HIGH,
            "Wall Street Journal": SourceCredibility.HIGH,
            "Financial Times": SourceCredibility.HIGH,
            # Crypto-specific (high)
            "CoinDesk": SourceCredibility.HIGH,
            "The Block": SourceCredibility.HIGH,
            "Cointelegraph": SourceCredibility.MEDIUM,
            "Coinbase Blog": SourceCredibility.HIGH,
            # Default
            "default": SourceCredibility.MEDIUM,
        }

    def calculate_impact_score(
        self,
        news_item: NewsItem,
        sentiment_score: SentimentScore,
    ) -> ImpactScore:
        """
        Calculate complete impact score for a news item

        Args:
            news_item: News article
            sentiment_score: Pre-calculated sentiment

        Returns:
            ImpactScore with breakdown and magnitude classification
        """
        # Prepare text
        text = f"{news_item.title} {news_item.description}".lower()

        # 1. Sentiment factor (0-20)
        sentiment_factor = self._calculate_sentiment_factor(sentiment_score)

        # 2. Regulatory factor (0-25)
        regulatory_level, regulatory_factor = self._calculate_regulatory_factor(text)

        # 3. Market mention factor (0-20)
        market_mention_factor = self._calculate_market_mention_factor(
            text, news_item.mention_count
        )

        # 4. Credibility factor (0-20)
        source_credibility = self.get_source_credibility(news_item.source)
        credibility_factor = float(source_credibility) * 20

        # 5. Temporal factor (0-15)
        temporal_factor = self._calculate_temporal_factor(news_item.published_at)

        # Calculate decay (72-hour half life)
        decay_factor = self._calculate_decay_factor(news_item.published_at)

        # Combine factors
        raw_score = (
            sentiment_factor
            + regulatory_factor
            + market_mention_factor
            + credibility_factor
            + temporal_factor
        )

        # Apply decay
        final_score = raw_score * decay_factor

        # Normalize to 0-100 scale
        impact_score = min(100.0, final_score)

        # Determine magnitude
        if impact_score >= 75:
            magnitude = "CRITICAL"
        elif impact_score >= 50:
            magnitude = "HIGH"
        elif impact_score >= 25:
            magnitude = "MEDIUM"
        else:
            magnitude = "LOW"

        # Calculate TTL (minutes article remains relevant)
        ttl_minutes = self._calculate_ttl(impact_score, sentiment_score.sentiment)

        # Direction
        direction = sentiment_score.sentiment.value.upper()

        factors = ImpactFactors(
            sentiment_factor=sentiment_factor,
            regulatory_factor=regulatory_factor,
            market_mention_factor=market_mention_factor,
            credibility_factor=credibility_factor,
            temporal_factor=temporal_factor,
            decay_factor=decay_factor,
        )

        logger.info(
            "impact_score_calculated",
            impact_score=f"{impact_score:.1f}",
            magnitude=magnitude,
            regulatory_level=regulatory_level.name,
            direction=direction,
            ttl_minutes=ttl_minutes,
        )

        return ImpactScore(
            news_id=news_item.id,
            impact_score=impact_score,
            factors=factors,
            sentiment=sentiment_score.sentiment,
            regulatory_level=regulatory_level,
            source_credibility=source_credibility,
            direction=direction,
            magnitude=magnitude,
            ttl_minutes=ttl_minutes,
            calculated_at=datetime.now(timezone.utc),
        )

    def _calculate_sentiment_factor(self, sentiment_score: SentimentScore) -> float:
        """
        Convert sentiment confidence to 0-20 factor

        Strong sentiment (high confidence) = higher factor
        Weak sentiment (low confidence) = lower factor
        """
        confidence = sentiment_score.confidence
        return confidence * 20.0

    def _calculate_regulatory_factor(self, text: str) -> Tuple[RegulatoryLevel, float]:
        """
        Calculate regulatory importance factor

        Returns:
            (regulatory_level, factor_0_to_25)
        """
        # Check for regulatory keywords
        text_lower = text.lower()

        if any(term in text_lower for term in self.regulatory_keywords.CRITICAL_TERMS):
            level = RegulatoryLevel.CRITICAL
            factor = 25.0

        elif any(term in text_lower for term in self.regulatory_keywords.HIGH_TERMS):
            level = RegulatoryLevel.HIGH
            factor = 18.0

        elif any(term in text_lower for term in self.regulatory_keywords.MEDIUM_TERMS):
            level = RegulatoryLevel.MEDIUM
            factor = 12.0

        elif any(term in text_lower for term in self.regulatory_keywords.LOW_TERMS):
            level = RegulatoryLevel.LOW
            factor = 6.0

        else:
            level = RegulatoryLevel.NONE
            factor = 0.0

        return level, factor

    def _calculate_market_mention_factor(
        self, text: str, mention_count: int = 0
    ) -> float:
        """
        Calculate market mention factor

        More mentions = more important
        Max 20 points
        """
        # Base mention count
        base_mentions = mention_count

        # Count additional key market mentions
        market_terms = ["bitcoin", "ethereum", "btc", "eth", "crypto", "defi"]
        additional_mentions = sum(text.count(term) for term in market_terms)

        total_mentions = base_mentions + additional_mentions

        # Logarithmic scaling to 0-20
        # 1 mention = 0, 10 mentions = 10, 100+ = 20
        with np.errstate(all="ignore"):
            factor = min(20.0, np.log1p(total_mentions) * 5)

        return float(max(0.0, factor))

    def _calculate_temporal_factor(self, published_at: datetime) -> float:
        """
        Calculate temporal importance factor

        Newer articles = higher factor
        24+ hours old = lower factor
        Returns 0-15
        """
        age_minutes = (datetime.now(timezone.utc) - published_at).total_seconds() / 60

        if age_minutes < 30:  # Very fresh
            return 15.0
        elif age_minutes < 120:  # 2 hours old
            return 12.0
        elif age_minutes < 480:  # 8 hours old
            return 9.0
        elif age_minutes < 1440:  # 24 hours old
            return 6.0
        else:  # Older than 24 hours
            return max(0.0, 6.0 - (age_minutes - 1440) / 240)

    def _calculate_decay_factor(self, published_at: datetime) -> float:
        """
        Calculate exponential decay factor

        72-hour half-life:
        - 0 hours old = 1.0 (100%)
        - 72 hours old = 0.5 (50%)
        - 144 hours old = 0.25 (25%)

        Returns 0-1
        """
        age_hours = (datetime.now(timezone.utc) - published_at).total_seconds() / 3600
        half_life_hours = 72.0

        decay = math.exp(-age_hours / half_life_hours * math.log(2))

        return float(np.clip(decay, 0.0, 1.0))

    def _calculate_ttl(self, impact_score: float, sentiment: SentimentLabel) -> int:
        """
        Calculate time-to-live in minutes

        Impact directly affects relevance duration:
        - CRITICAL (75+): 1440 minutes (24 hours)
        - HIGH (50-74): 720 minutes (12 hours)
        - MEDIUM (25-49): 360 minutes (6 hours)
        - LOW (<25): 120 minutes (2 hours)

        Bullish news lasts longer than bearish
        """
        base_ttl = {
            "CRITICAL": 1440,
            "HIGH": 720,
            "MEDIUM": 360,
            "LOW": 120,
        }

        if impact_score >= 75:
            ttl = base_ttl["CRITICAL"]
        elif impact_score >= 50:
            ttl = base_ttl["HIGH"]
        elif impact_score >= 25:
            ttl = base_ttl["MEDIUM"]
        else:
            ttl = base_ttl["LOW"]

        # Bullish news lasts 20% longer (market euphoria)
        if sentiment == SentimentLabel.BULLISH:
            ttl = int(ttl * 1.2)

        return ttl

    def get_source_credibility(self, source_name: str) -> SourceCredibility:
        """Get credibility score for a source"""
        return self.source_credibility_map.get(
            source_name,
            self.source_credibility_map["default"],
        )

    async def score_batch(
        self,
        items_with_sentiment: List[Tuple[NewsItem, SentimentScore]],
    ) -> List[ImpactScore]:
        """
        Score multiple items with sentiment

        Args:
            items_with_sentiment: List of (NewsItem, SentimentScore) tuples

        Returns:
            List of ImpactScore objects
        """
        results = [
            self.calculate_impact_score(item, sentiment)
            for item, sentiment in items_with_sentiment
        ]

        return results

    def get_impact_stats(self, scores: List[ImpactScore]) -> Dict:
        """Get statistics from batch impact scoring"""
        if not scores:
            return {}

        magnitudes = [s.magnitude for s in scores]
        critical_count = sum(1 for m in magnitudes if m == "CRITICAL")
        high_count = sum(1 for m in magnitudes if m == "HIGH")
        medium_count = sum(1 for m in magnitudes if m == "MEDIUM")
        low_count = sum(1 for m in magnitudes if m == "LOW")

        avg_impact = np.mean([s.impact_score for s in scores])
        max_impact = max([s.impact_score for s in scores])
        min_impact = min([s.impact_score for s in scores])

        bullish_count = sum(1 for s in scores if s.sentiment == SentimentLabel.BULLISH)
        bearish_count = sum(1 for s in scores if s.sentiment == SentimentLabel.BEARISH)

        return {
            "total_scored": len(scores),
            "critical_count": critical_count,
            "high_count": high_count,
            "medium_count": medium_count,
            "low_count": low_count,
            "avg_impact_score": float(avg_impact),
            "max_impact_score": float(max_impact),
            "min_impact_score": float(min_impact),
            "bullish_count": bullish_count,
            "bearish_count": bearish_count,
            "top_stories": [
                {
                    "news_id": s.news_id,
                    "impact_score": f"{s.impact_score:.1f}",
                    "magnitude": s.magnitude,
                    "direction": s.direction,
                }
                for s in sorted(scores, key=lambda x: x.impact_score, reverse=True)[:5]
            ],
        }


# Global impact engine instance
_impact_engine = None


async def get_impact_engine() -> ImpactScoringEngine:
    """Get global impact scoring engine instance (singleton)"""
    global _impact_engine
    if _impact_engine is None:
        _impact_engine = ImpactScoringEngine()
    return _impact_engine
