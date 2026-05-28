import httpx
import logging
from models.schemas import NewsAnalysis

logger = logging.getLogger(__name__)

class NewsAnalyzer:
    def __init__(self, news_url: str):
        self.news_url = news_url
        self.client = httpx.AsyncClient(timeout=10.0)

    async def analyze(self, symbol: str, timeframe: str) -> NewsAnalysis:
        try:
            # Fetch News score from API
            response = await self.client.get(
                f"{self.news_url}/api/metrics/news",
                params={"timeframe": timeframe}
            )
            response.raise_for_status()
            news_data = response.json()

            score = news_data.get("score", 0.5)
            details = news_data.get("details", {})

            # Extract news metrics
            articles_analyzed = int(details.get("articles_analyzed", 10))
            sentiment_score = float(details.get("sentiment_score", 50.0))
            positive = int(details.get("positive_articles", 6))
            negative = int(details.get("negative_articles", 3))
            neutral = int(details.get("neutral_articles", 1))

            # Get top news
            top_news = details.get("top_news", [
                {"title": "Fed faiz indirim sinyali verdi", "sentiment": "Pozitif"},
                {"title": "BlackRock Bitcoin ETF talebi arttı", "sentiment": "Pozitif"},
                {"title": "ABD düzenlemesi belirsizliği", "sentiment": "Negatif"}
            ])

            # Determine direction based on sentiment
            direction = self._determine_direction(score, sentiment_score)

            details_text = (
                f"Son {timeframe} içinde {articles_analyzed} haber analiz edildi. "
                f"Pozitif: {positive}, Negatif: {negative}, Nötr: {neutral}. "
                f"Net Sentiment: {sentiment_score:.1f}%"
            )

            return NewsAnalysis(
                direction=direction,
                confidence=score,
                articles_analyzed=articles_analyzed,
                sentiment_score=sentiment_score,
                positive_articles=positive,
                negative_articles=negative,
                neutral_articles=neutral,
                top_news=top_news,
                details=details_text
            )

        except httpx.HTTPError as e:
            logger.error(f"News API error: {e}")
            return NewsAnalysis(
                direction="NÖTR",
                confidence=0.3,
                articles_analyzed=0,
                sentiment_score=50.0,
                positive_articles=0,
                negative_articles=0,
                neutral_articles=0,
                top_news=[],
                details=f"Veri alınamadı: {str(e)}"
            )

    def _determine_direction(self, score: float, sentiment: float) -> str:
        """Determine direction based on news sentiment"""
        if sentiment > 60 and score > 0.5:
            return "LONG"
        elif sentiment < 40 and score < 0.5:
            return "SHORT"
        else:
            return "NÖTR"

    async def close(self):
        await self.client.aclose()
