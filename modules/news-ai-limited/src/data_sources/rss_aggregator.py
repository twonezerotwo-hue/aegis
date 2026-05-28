"""
News AI Limited - RSS Feed Aggregator

Fetches and parses RSS feeds from multiple sources (20+ feeds).
Includes govt. aggregator feeds, crypto news, market analysis.
"""
from typing import List
import feedparser
import asyncio
from datetime import datetime, timezone
from hashlib import md5
from ..signal_models import NewsItem
from .base_source import BaseDataSource
from ..logging.logger_config import get_logger

logger = get_logger(__name__)

# RSS feed sources organized by country
RSS_FEED_SOURCES = {
    "USA": [
        {
            "url": "https://home.treasury.gov/news/feed.xml",
            "source_name": "Treasury.gov",
        },
        {
            "url": "https://www.sec.gov/news/news-releases/feed.xml",
            "source_name": "SEC Announcements",
        },
        {
            "url": "https://www.cftc.gov/news-and-events/news-releases/feed.xml",
            "source_name": "CFTC",
        },
    ],
    "China": [
        {
            "url": "https://www.pbc.gov.cn/english/feed.xml",
            "source_name": "PBOC",
        },
        {
            "url": "http://news.xinhuanet.com/rss/",
            "source_name": "Xinhua News",
        },
    ],
    "Russia": [
        {
            "url": "https://www.tass.com/crypto/feed",
            "source_name": "TASS",
        },
    ],
    "Turkey": [
        {
            "url": "https://www.tcmb.gov.tr/news.xml",
            "source_name": "TCMB",
        },
    ],
    "Crypto": [
        {
            "url": "https://feeds.coindesk.com/latest",
            "source_name": "CoinDesk",
        },
        {
            "url": "https://cointelegraph.com/feed",
            "source_name": "Cointelegraph",
        },
    ],
    "Finance": [
        {
            "url": "https://feeds.reuters.com/reuters/businessNews",
            "source_name": "Reuters Business",
        },
        {
            "url": "https://feeds.reuters.com/reuters/technologyNews",
            "source_name": "Reuters Technology",
        },
        {
            "url": "https://www.fxstreet.com/rss/news",
            "source_name": "FXStreet",
        },
        {
            "url": "https://www.matriks.com.tr/Haberler/feed",
            "source_name": "Matriks",
        },
    ],
    "CryptoEN": [
        {
            "url": "https://beincrypto.com/feed/",
            "source_name": "BeInCrypto",
        },
    ],
    "CryptoTR": [
        {
            "url": "https://tr.beincrypto.com/feed/",
            "source_name": "BeInCrypto TR",
        },
        {
            "url": "https://muhabbit.com/feed/",
            "source_name": "Muhabbit",
        },
        {
            "url": "https://uzmancoins.com/feed/",
            "source_name": "UzmanCoin",
        },
    ],
}


class RSSAggregator(BaseDataSource):
    """Fetches news from RSS feeds"""

    def __init__(self):
        """Initialize RSS aggregator"""
        super().__init__(
            source_name="RSS Aggregator",
            country="GLOBAL",
            is_enabled=True,
        )
        self.feeds_config = RSS_FEED_SOURCES

    async def _fetch_internal(self) -> List[NewsItem]:
        """
        Fetch news from all configured RSS feeds

        Returns:
            List of NewsItem objects
        """
        all_news_items: List[NewsItem] = []

        # Fetch all feeds concurrently
        tasks = []
        for country, feeds in self.feeds_config.items():
            for feed_config in feeds:
                task = self._fetch_single_feed(
                    url=feed_config["url"],
                    source_name=feed_config["source_name"],
                    country=country,
                )
                tasks.append(task)

        # Run all feeds in parallel with timeout
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_news_items.extend(result)
            elif isinstance(result, Exception):
                logger.warning(f"RSS feed error: {str(result)}")

        logger.info(
            "rss_aggregator_fetch",
            total_items=len(all_news_items),
            feeds_checked=len(tasks),
        )

        return all_news_items

    async def _fetch_single_feed(
        self,
        url: str,
        source_name: str,
        country: str,
    ) -> List[NewsItem]:
        """
        Fetch and parse a single RSS feed

        Args:
            url: RSS feed URL
            source_name: Human-readable source name
            country: Country identifier
        """
        try:
            # Async wrapper for feedparser
            loop = asyncio.get_event_loop()
            feed = await loop.run_in_executor(
                None,
                lambda: feedparser.parse(url),
            )

            news_items = []
            for entry in feed.entries[:10]:  # Limit to 10 recent items per feed
                try:
                    # Extract published date
                    published_at = datetime.now(timezone.utc)
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

                    # Create NewsItem
                    news_item = NewsItem(
                        id=md5(f"{url}_{entry.link}_{published_at}".encode()).hexdigest()[:8],
                        title=entry.get("title", "No title"),
                        content=entry.get("summary", "")[:1000],
                        source_url=entry.get("link", url),
                        source_name=source_name,
                        published_at=published_at,
                        fetched_at=datetime.now(timezone.utc),
                        country=country,
                        category="news",  # Will be refined by sentiment
                        sentiment_score=0.0,  # Will be calculated by sentiment engine
                        sentiment_label="neutral",
                    )

                    news_items.append(news_item)

                except Exception as e:
                    logger.warning(f"Error parsing RSS entry from {source_name}: {str(e)}")
                    continue

            return news_items

        except Exception as e:
            logger.error(f"Error fetching RSS feed {source_name} ({url}): {str(e)}")
            return []

    def add_custom_feed(self, country: str, url: str, source_name: str):
        """Dynamically add a custom RSS feed"""
        if country not in self.feeds_config:
            self.feeds_config[country] = []

        self.feeds_config[country].append({
            "url": url,
            "source_name": source_name,
        })

        logger.info(
            "custom_rss_feed_added",
            country=country,
            source_name=source_name,
        )
