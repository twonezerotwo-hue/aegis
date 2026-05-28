"""
News AI Limited - Consensus Engine Integration

Builds NewsSignal objects and publishes to Consensus Engine via Redis Pub/Sub.

Pipeline:
1. Fetch news from data sources
2. Analyze sentiment
3. Calculate impact score
4. Build NewsSignal (matches Consensus format)
5. Publish to Redis channel: consensus:signals:news
6. Consensus Engine consumes and aggregates
"""

from typing import Dict, List, Optional
from dataclasses import asdict
from datetime import datetime, timezone
import json
import asyncio
import aioredis
from ..signal_models import NewsSignal, NewsItem
from ..sentiment.sentiment_engine import SentimentEngine, SentimentLabel
from ..impact_scoring.crypto_impact_scorer import ImpactScoringEngine, ImpactScore
from ..logging.logger_config import get_logger
from ..config import get_settings

logger = get_logger(__name__)


class NewsSignalBuilder:
    """Builds NewsSignal objects for Consensus Engine"""

    @staticmethod
    def from_impact_score(
        impact_score: ImpactScore,
        news_item: NewsItem,
    ) -> NewsSignal:
        """
        Build NewsSignal from impact scoring result

        Args:
            impact_score: Calculated impact score
            news_item: Original news item

        Returns:
            NewsSignal compatible with Consensus Engine
        """
        # Convert sentiment to numeric score (-1 to +1)
        sentiment_map = {
            SentimentLabel.BEARISH: -1.0,
            SentimentLabel.NEUTRAL: 0.0,
            SentimentLabel.BULLISH: 1.0,
        }
        sentiment_numeric = sentiment_map[impact_score.sentiment]

        # Timestamp
        published = datetime.fromisoformat(news_item.published_at)
        created_at = datetime.now(timezone.utc)

        signal = NewsSignal(
            # Metadata
            signal_id=f"news_{impact_score.news_id}",
            phase=6,  # News AI is phase 6
            timestamp=created_at,
            symbol=news_item.symbol or "GENERIC",
            # Core sentiment
            base_signal=sentiment_numeric,  # -1 to +1
            confidence=impact_score.factors.credibility_factor / 20.0,  # Normalize to 0-1
            # Impact breakdown
            signal_strength=impact_score.impact_score / 100.0,  # Normalize to 0-1
            impact_magnitude=impact_score.magnitude,  # CRITICAL, HIGH, MEDIUM, LOW
            regulatory_relevance=impact_score.regulatory_level.value,  # 0-4
            # Metadata
            source=news_item.source or "Unknown",
            title=news_item.title,
            description=news_item.description[:200],  # Truncate
            published_at=published,
            # TTL & Decay
            time_to_live_minutes=impact_score.ttl_minutes,
            decay_rate=impact_score.factors.decay_factor,
            # Factors breakdown
            factors={
                "sentiment": impact_score.factors.sentiment_factor / 20.0,
                "regulatory": impact_score.factors.regulatory_factor / 25.0,
                "market_mention": impact_score.factors.market_mention_factor / 20.0,
                "credibility": impact_score.factors.credibility_factor / 20.0,
                "temporal": impact_score.factors.temporal_factor / 15.0,
            },
        )

        return signal


class ConsensusIntegrationManager:
    """
    Manages integration with Consensus Engine

    Responsibilities:
    - Connect to Redis
    - Publish NewsSignal objects
    - Handle Pub/Sub messaging
    - Track published signals
    """

    def __init__(self):
        """Initialize consensus integration"""
        self.settings = get_settings()
        self.redis_client: Optional[aioredis.Redis] = None
        self.channel_name = "consensus:signals:news"
        self.published_count = 0
        self.failed_count = 0

    async def connect(self) -> bool:
        """
        Connect to Redis

        Returns:
            Success status
        """
        try:
            self.redis_client = await aioredis.create_redis_pool(
                f"redis://{self.settings.redis_host}:{self.settings.redis_port}",
                encoding="utf-8",
            )

            # Test connection
            await self.redis_client.ping()

            logger.info(
                "redis_connected",
                host=self.settings.redis_host,
                port=self.settings.redis_port,
            )

            return True

        except Exception as e:
            logger.error(f"redis_connection_failed: {e}")
            self.redis_client = None
            return False

    async def disconnect(self) -> None:
        """Disconnect from Redis"""
        if self.redis_client:
            self.redis_client.close()
            await self.redis_client.wait_closed()
            logger.info("redis_disconnected")

    async def publish_signal(self, signal: NewsSignal) -> bool:
        """
        Publish a NewsSignal to Consensus Engine

        Args:
            signal: NewsSignal to publish

        Returns:
            Success status
        """
        if not self.redis_client:
            logger.warning("redis_not_connected")
            return False

        try:
            # Convert to JSON
            signal_dict = asdict(signal)

            # Handle datetime serialization
            signal_dict["timestamp"] = signal.timestamp.isoformat()
            signal_dict["published_at"] = signal.published_at.isoformat()

            signal_json = json.dumps(signal_dict)

            # Publish to Redis channel
            subscribers = await self.redis_client.publish(
                self.channel_name,
                signal_json,
            )

            self.published_count += 1

            logger.info(
                "signal_published",
                signal_id=signal.signal_id,
                subscribers=subscribers,
                impact_score=signal.signal_strength * 100,
            )

            return True

        except Exception as e:
            self.failed_count += 1
            logger.error(
                "signal_publish_failed",
                signal_id=signal.signal_id,
                error=str(e),
            )
            return False

    async def publish_batch(self, signals: List[NewsSignal]) -> Dict[str, int]:
        """
        Publish multiple signals

        Args:
            signals: List of NewsSignal objects

        Returns:
            Stats dict with success/failure counts
        """
        tasks = [self.publish_signal(signal) for signal in signals]
        results = await asyncio.gather(*tasks)

        success_count = sum(1 for r in results if r)
        failure_count = len(results) - success_count

        return {
            "total": len(signals),
            "published": success_count,
            "failed": failure_count,
            "cumulative_published": self.published_count,
            "cumulative_failed": self.failed_count,
        }

    async def get_weighting_recommendation(self) -> Dict:
        """
        Get recommended weighting for consensus aggregation

        Based on News AI performance, suggest optimal weight vs other phases

        Returns:
            Weighting recommendation dict
        """
        total_published = self.published_count + self.failed_count

        if total_published == 0:
            # Default until we have data
            return {
                "phase": 6,
                "recommended_weight": 0.333,  # Equal 3-way split
                "reason": "news_ai_no_signal_history",
                "confidence": 0.0,
            }

        # Success rate
        success_rate = self.published_count / total_published if total_published > 0 else 0

        # Adjust weight based on reliability
        if success_rate > 0.95:
            weight = 0.35  # Slightly higher
            confidence = 0.9
        elif success_rate > 0.85:
            weight = 0.333  # Equal share
            confidence = 0.8
        elif success_rate > 0.70:
            weight = 0.30  # Slightly lower
            confidence = 0.6
        else:
            weight = 0.25  # Lower until reliability improves
            confidence = 0.4

        return {
            "phase": 6,
            "recommended_weight": weight,
            "success_rate": success_rate,
            "confidence": confidence,
            "total_signals_published": self.published_count,
            "total_failures": self.failed_count,
            "reason": f"reliability_{int(success_rate*100)}pct",
        }

    def get_stats(self) -> Dict:
        """Get integration statistics"""
        total = self.published_count + self.failed_count

        return {
            "published_signals": self.published_count,
            "failed_signals": self.failed_count,
            "total_attempts": total,
            "success_rate": (
                self.published_count / total if total > 0 else 0
            ),
            "redis_connected": self.redis_client is not None,
            "channel": self.channel_name,
        }


class NewsAISignalPipeline:
    """
    Complete pipeline from news → consensus signal

    Orchestrates:
    1. News fetching (done by main.py)
    2. Sentiment analysis
    3. Impact scoring
    4. Signal building
    5. Consensus publishing
    """

    def __init__(
        self,
        sentiment_engine: SentimentEngine,
        impact_engine: ImpactScoringEngine,
        consensus_manager: ConsensusIntegrationManager,
    ):
        """Initialize pipeline"""
        self.sentiment_engine = sentiment_engine
        self.impact_engine = impact_engine
        self.consensus_manager = consensus_manager

    async def process_news_items(
        self,
        news_items: List[NewsItem],
    ) -> Dict:
        """
        Process news items through full pipeline

        Args:
            news_items: Raw news items from data sources

        Returns:
            Pipeline execution stats
        """
        if not news_items:
            logger.warning("no_news_items_to_process")
            return {"processed": 0, "published": 0, "failed": 0}

        logger.info("pipeline_started", news_count=len(news_items))

        # Step 1: Sentiment analysis
        sentiment_scores = await self.sentiment_engine.analyze_batch(news_items)

        # Step 2: Impact scoring
        impact_scores = await self.impact_engine.score_batch(
            [(item, sentiment) for item, sentiment in zip(news_items, sentiment_scores)]
        )

        # Step 3: Filter high-impact only (impact > 30)
        high_impact_scores = [s for s in impact_scores if s.impact_score > 30]

        logger.info(
            "high_impact_filtered",
            total_scored=len(impact_scores),
            high_impact_count=len(high_impact_scores),
        )

        # Step 4: Build signals
        signals = [
            NewsSignalBuilder.from_impact_score(
                impact,
                next(ni for ni in news_items if ni.id == impact.news_id),
            )
            for impact in high_impact_scores
        ]

        # Step 5: Publish to consensus
        publish_stats = await self.consensus_manager.publish_batch(signals)

        logger.info(
            "pipeline_completed",
            processed=len(news_items),
            published=publish_stats["published"],
            failed=publish_stats["failed"],
        )

        return {
            **publish_stats,
            "sentiment_analyzed": len(sentiment_scores),
            "impact_scored": len(impact_scores),
            "high_impact": len(high_impact_scores),
        }


# Global instances
_sentiment_engine = None
_impact_engine = None
_consensus_manager = None
_pipeline = None


async def initialize_news_ai_pipeline() -> NewsAISignalPipeline:
    """Initialize and return global News AI pipeline"""
    global _sentiment_engine, _impact_engine, _consensus_manager, _pipeline

    if _pipeline is not None:
        return _pipeline

    # Initialize engines
    from .sentiment_engine import get_sentiment_engine
    from .crypto_impact_scorer import get_impact_engine

    _sentiment_engine = await get_sentiment_engine()
    _impact_engine = await get_impact_engine()
    _consensus_manager = ConsensusIntegrationManager()

    # Connect to Redis
    connected = await _consensus_manager.connect()

    if not connected:
        logger.warning("consensus_integration_not_available")

    # Create pipeline
    _pipeline = NewsAISignalPipeline(
        _sentiment_engine,
        _impact_engine,
        _consensus_manager,
    )

    logger.info("news_ai_pipeline_initialized")

    return _pipeline


async def get_news_ai_pipeline() -> NewsAISignalPipeline:
    """Get global News AI pipeline instance"""
    global _pipeline
    if _pipeline is None:
        _pipeline = await initialize_news_ai_pipeline()
    return _pipeline
