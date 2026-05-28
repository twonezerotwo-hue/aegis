"""
Historical News Fetcher — connects to news-ai-limited service for real sentiment data.

This module provides a NewsApiFetcher class that calls the live news-ai-limited
service to retrieve real sentiment scores for backtest use.

Docker internal URL: http://news-ai-limited:8006
Endpoints used:
  - GET /signals  → aggregated_sentiment (-1 to +1), crypto_impact_score (0-100)
  - POST /analyze → per-symbol analysis
"""

import os
import logging
from datetime import datetime
from typing import Optional

import requests

logger = logging.getLogger(__name__)

NEWS_API_BASE = os.environ.get("NEWS_URL", "http://news-ai-limited:8006")
_REQUEST_TIMEOUT = 10  # seconds


class NewsApiFetcher:
    """
    Fetches sentiment from the news-ai-limited microservice.

    For historical backtests:
      - Recent dates (within last 30 days): uses live API sentiment.
      - Older dates: returns neutral (0.0) since no historical archive exists.
    """

    def __init__(self, base_url: str = NEWS_API_BASE):
        self._base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})
        self._cached_sentiment: Optional[float] = None
        self._cache_ts: Optional[datetime] = None

    # ------------------------------------------------------------------ #
    #  Public API expected by backtest_routes.py                          #
    # ------------------------------------------------------------------ #
    def fetch_daily_sentiment(self, symbol: str, date: datetime) -> float:
        """
        Return sentiment score in [-1, +1] range for the given symbol/date.

        Strategy:
          1. If `date` is within the last 30 days → call live API.
          2. Otherwise → return 0.0 (neutral) since no historical archive.
        """
        now = datetime.utcnow()
        days_ago = (now - date).days if hasattr(date, "day") else 9999

        if days_ago > 30:
            return 0.0  # no historical data available

        return self._get_live_sentiment(symbol)

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                   #
    # ------------------------------------------------------------------ #
    def _get_live_sentiment(self, symbol: str) -> float:
        """Call /signals and return aggregated_sentiment."""
        # Use cached value if fresh (< 60 s)
        now = datetime.utcnow()
        if (
            self._cached_sentiment is not None
            and self._cache_ts is not None
            and (now - self._cache_ts).total_seconds() < 60
        ):
            return self._cached_sentiment

        try:
            resp = self._session.get(
                f"{self._base_url}/signals",
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            signals = data.get("signals", [])
            if signals:
                sentiment = float(signals[0].get("aggregated_sentiment", 0.0))
            else:
                sentiment = 0.0

            self._cached_sentiment = sentiment
            self._cache_ts = now
            logger.debug("Live news sentiment fetched: %.4f", sentiment)
            return sentiment

        except Exception as exc:
            logger.warning("Failed to fetch live news sentiment: %s", exc)
            return self._cached_sentiment if self._cached_sentiment is not None else 0.0


# ------------------------------------------------------------------ #
#  Factory function imported by backtest_routes.py                    #
# ------------------------------------------------------------------ #
def get_news_fetcher() -> Optional[NewsApiFetcher]:
    """
    Return a NewsApiFetcher if the news-ai-limited service is reachable,
    otherwise return None (caller will fall back to volume-based simulation).
    """
    base = NEWS_API_BASE
    try:
        r = requests.get(f"{base}/health", timeout=5)
        if r.status_code == 200:
            logger.info("✅ News fetcher connected to %s", base)
            return NewsApiFetcher(base)
    except Exception as exc:
        logger.warning("⚠️ News service unreachable at %s: %s", base, exc)

    return None
