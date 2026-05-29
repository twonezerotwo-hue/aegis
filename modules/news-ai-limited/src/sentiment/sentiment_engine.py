"""
News AI Limited - Sentiment Engine

Analyzes news sentiment using:
1. FinBERT (pre-trained financial sentiment model)
2. Ensemble voting mechanism
3. Crypto-specific lexicon augmentation
4. Confidence scoring
"""

from typing import Dict, List
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import numpy as np
from ..signal_models import NewsItem
from ..logging.logger_config import get_logger

logger = get_logger(__name__)


class SentimentLabel(str, Enum):
    """Sentiment classification"""
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    BULLISH = "bullish"


@dataclass
class SentimentScore:
    """Sentiment analysis result"""
    news_id: str
    sentiment: SentimentLabel
    confidence: float  # 0.0-1.0
    bearish_score: float  # 0.0-1.0
    neutral_score: float  # 0.0-1.0
    bullish_score: float  # 0.0-1.0
    model_scores: Dict[str, float]  # Individual model scores
    analyzed_at: datetime


class SentimentEngine:
    """
    Analyzes sentiment of news articles using ensemble of models

    Pipeline:
    1. FinBERT model (financial domain)
    2. Lexicon-based scoring (crypto-specific)
    3. Ensemble voting
    4. Confidence calculation
    """

    def __init__(self):
        """Initialize sentiment engine"""
        self.models = {}
        self._initialize_models()

    def _initialize_models(self) -> None:
        """
        Initialize all sentiment models

        Models loaded:
        - FinBERT (transformer)
        - Crypto lexicon (rule-based)
        - Pattern matcher (keyword-based)
        """
        try:
            # FinBERT model
            from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
            import torch

            model_name = "ProsusAI/finbert"

            tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
            model = AutoModelForSequenceClassification.from_pretrained(
                model_name,
                trust_remote_code=True,
            )

            device = 0 if torch.cuda.is_available() else -1

            self.finbert_pipeline = pipeline(
                "text-classification",
                model=model,
                tokenizer=tokenizer,
                device=device,
            )

            logger.info("finbert_model_loaded", device=device)

        except ImportError:
            logger.warning("finbert_model_not_available", error="transformers not installed")
            self.finbert_pipeline = None

        # Crypto-specific lexicon
        self._initialize_crypto_lexicon()

    def _initialize_crypto_lexicon(self) -> None:
        """Initialize crypto-specific sentiment lexicon"""
        # Bullish indicators
        self.bullish_keywords = {
            # Positive events
            "adoption",
            "partnership",
            "integration",
            "launch",
            "breakthrough",
            "surge",
            "bull",
            "record",
            "gains",
            "profit",
            "bullish",
            "boom",
            "rally",
            "approval",
            "bullrun",
            "moonshot",
            "pump",
            # Positive technical
            "breakout",
            "momentum",
            "support",
            "resistance_break",
            # Positive sentiment
            "excited",
            "optimistic",
            "confident",
            "revolutionary",
            "innovative",
            "game-changing",
        }

        # Bearish indicators
        self.bearish_keywords = {
            # Negative events
            "crash",
            "collapse",
            "fraud",
            "hack",
            "attack",
            "concern",
            "warning",
            "bearish",
            "decline",
            "loss",
            "losses",
            "regulation",
            "ban",
            "ban",
            "selloff",
            "dump",
            "panic",
            # Negative technical
            "breakdown",
            "resistance",
            "downtrend",
            # Negative sentiment
            "worried",
            "cautious",
            "skeptical",
            "risky",
            "volatile",
            "unstable",
        }

        # Neutral keywords
        self.neutral_keywords = {
            "update",
            "announcement",
            "report",
            "analysis",
            "statement",
            "discussion",
            "review",
            "forecast",
            "data",
            "information",
        }

    async def analyze_sentiment(self, news_item: NewsItem) -> SentimentScore:
        """
        Analyze sentiment of a news item

        Args:
            news_item: News article to analyze

        Returns:
            SentimentScore with detailed breakdown
        """
        model_scores: Dict[str, float] = {}

        # Prepare text (title + content)
        text = f"{news_item.title} {news_item.content}".lower()

        # 1. FinBERT analysis
        if self.finbert_pipeline:
            finbert_result = await self._analyze_finbert(text)
            model_scores["finbert"] = finbert_result
        else:
            finbert_result = 0.0

        # 2. Crypto lexicon analysis
        lexicon_result = self._analyze_lexicon(text)
        model_scores["lexicon"] = lexicon_result

        # 3. Pattern/keyword matching
        pattern_result = self._analyze_patterns(text)
        model_scores["pattern"] = pattern_result

        # Ensemble voting
        scores = np.array(list(model_scores.values()))
        mean_score = float(np.mean(scores))
        std_score = float(np.std(scores))

        # Normalize to -1 to +1 range
        # -1 = bearish, 0 = neutral, +1 = bullish
        normalized_score = np.clip(mean_score, -1.0, 1.0)

        # Determine sentiment class
        if normalized_score > 0.2:
            sentiment = SentimentLabel.BULLISH
            bullish = max(0.5, (normalized_score + 1) / 2)
            neutral = 0.2
            bearish = 1.0 - bullish - neutral
        elif normalized_score < -0.2:
            sentiment = SentimentLabel.BEARISH
            bearish = max(0.5, (-normalized_score + 1) / 2)
            neutral = 0.2
            bullish = 1.0 - bearish - neutral
        else:
            sentiment = SentimentLabel.NEUTRAL
            neutral = 0.7
            bullish = 0.15
            bearish = 0.15

        # Confidence = 1 - std_dev (higher agreement = higher confidence)
        confidence = max(0.3, 1.0 - std_score)

        logger.info(
            "sentiment_analyzed",
            sentiment=sentiment.value,
            confidence=f"{confidence:.2f}",
            mean_score=f"{mean_score:.2f}",
            models_count=len(model_scores),
        )

        return SentimentScore(
            news_id=news_item.id,
            sentiment=sentiment,
            confidence=confidence,
            bullish_score=float(bullish),
            neutral_score=float(neutral),
            bearish_score=float(bearish),
            model_scores=model_scores,
            analyzed_at=datetime.now(timezone.utc),
        )

    async def _analyze_finbert(self, text: str) -> float:
        """
        Analyze sentiment using FinBERT model

        Args:
            text: Text to analyze

        Returns:
            Score in range -1.0 to 1.0 (bearish to bullish)
        """
        try:
            # Truncate to avoid token limit
            max_length = 512
            if len(text) > max_length:
                text = text[:max_length]

            result = self.finbert_pipeline(text, top_k=None)

            # Result format: [{'label': 'positive', 'score': 0.95}, ...]
            scores_map = {r["label"].lower(): r["score"] for r in result}

            positive = scores_map.get("positive", 0.0)
            negative = scores_map.get("negative", 0.0)
            neutral = scores_map.get("neutral", 0.0)

            # Convert to -1 to +1 scale
            score = (positive - negative)

            return float(score)

        except Exception as e:
            logger.error(f"finbert_analysis_error: {e}")
            return 0.0

    def _analyze_lexicon(self, text: str) -> float:
        """
        Analyze sentiment using crypto lexicon

        Args:
            text: Text to analyze

        Returns:
            Score in range -1.0 to 1.0
        """
        words = text.split()
        word_set = set(words)

        bullish_count = len(word_set & self.bullish_keywords)
        bearish_count = len(word_set & self.bearish_keywords)
        neutral_count = len(word_set & self.neutral_keywords)

        total_sentiment_words = bullish_count + bearish_count

        if total_sentiment_words == 0:
            return 0.0

        # Calculate net sentiment
        net_sentiment = (bullish_count - bearish_count) / total_sentiment_words

        return float(np.clip(net_sentiment, -1.0, 1.0))

    def _analyze_patterns(self, text: str) -> float:
        """
        Analyze sentiment using pattern matching

        Args:
            text: Text to analyze

        Returns:
            Score in range -1.0 to 1.0
        """
        score = 0.0

        # Positive patterns
        if any(pattern in text for pattern in ["surge ", "rocket", "moon", "lambo"]):
            score += 0.3
        if any(pattern in text for pattern in ["bullish", "long", "buy"]):
            score += 0.2
        if "bull run" in text:
            score += 0.4

        # Negative patterns
        if any(pattern in text for pattern in ["crash", "dump", "panic"]):
            score -= 0.3
        if any(pattern in text for pattern in ["bearish", "short", "sell"]):
            score -= 0.2
        if "bear market" in text:
            score -= 0.4

        # Emergency patterns (double weight)
        if "hack" in text or "security breach" in text:
            score -= 0.5
        if "regulatory approval" in text or "etf approval" in text:
            score += 0.5

        return float(np.clip(score, -1.0, 1.0))

    async def analyze_batch(self, news_items: List[NewsItem]) -> List[SentimentScore]:
        """
        Analyze sentiment of multiple news items

        Args:
            news_items: List of news to analyze

        Returns:
            List of SentimentScore objects
        """
        import asyncio

        tasks = [self.analyze_sentiment(item) for item in news_items]
        results = await asyncio.gather(*tasks)

        return results

    def get_sentiment_stats(
        self, scores: List[SentimentScore]
    ) -> Dict:
        """Get statistics from batch sentiment analysis"""
        if not scores:
            return {}

        sentiments = [s.sentiment for s in scores]
        bullish_count = sum(1 for s in sentiments if s == SentimentLabel.BULLISH)
        neutral_count = sum(1 for s in sentiments if s == SentimentLabel.NEUTRAL)
        bearish_count = sum(1 for s in sentiments if s == SentimentLabel.BEARISH)

        total = len(scores)
        avg_confidence = np.mean([s.confidence for s in scores])
        avg_bullish = np.mean([s.bullish_score for s in scores])
        avg_bearish = np.mean([s.bearish_score for s in scores])

        # Market sentiment indicator (-1 to +1)
        market_sentiment = avg_bullish - avg_bearish

        return {
            "total_analyzed": total,
            "bullish_count": bullish_count,
            "neutral_count": neutral_count,
            "bearish_count": bearish_count,
            "bullish_pct": bullish_count / total if total > 0 else 0,
            "neutral_pct": neutral_count / total if total > 0 else 0,
            "bearish_pct": bearish_count / total if total > 0 else 0,
            "avg_confidence": float(avg_confidence),
            "avg_bullish_score": float(avg_bullish),
            "avg_bearish_score": float(avg_bearish),
            "market_sentiment": float(market_sentiment),  # -1 to +1
            "sentiment_direction": (
                "BULLISH" if market_sentiment > 0.1
                else "BEARISH" if market_sentiment < -0.1
                else "NEUTRAL"
            ),
        }


# Global sentiment engine instance
_sentiment_engine = None


async def get_sentiment_engine() -> SentimentEngine:
    """Get global sentiment engine instance (singleton)"""
    global _sentiment_engine
    if _sentiment_engine is None:
        _sentiment_engine = SentimentEngine()
    return _sentiment_engine
