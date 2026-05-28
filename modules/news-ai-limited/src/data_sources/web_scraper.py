"""
News AI Limited - Web Scraper

Backup web scraping using BeautifulSoup for static pages and Selenium for JavaScript-heavy sites.
Rate-limited and resilient to handle various page structures.
"""
from typing import List, Dict, Optional
import aiohttp
import asyncio
from datetime import datetime, timezone
from hashlib import md5
from bs4 import BeautifulSoup
from ..signal_models import NewsItem
from .base_source import BaseDataSource
from ..logging.logger_config import get_logger
from aiolimiter import AsyncLimiter

logger = get_logger(__name__)


class WebScraper(BaseDataSource):
    """
    Web scraper for backup news sources

    Scrapes news from websites that don't have RSS feeds or APIs.
    Uses rate limiting to be respectful to servers.
    """

    def __init__(self):
        """Initialize web scraper"""
        super().__init__(
            source_name="Web Scraper",
            country="GLOBAL",
            is_enabled=True,
            max_failures=3,
        )
        self.session: Optional[aiohttp.ClientSession] = None

        # Rate limiter: 1 request per 2 seconds per domain
        self.rate_limiter = AsyncLimiter(max_rate=1, time_period=2)

        # Backup scraping targets (when RSS/APIs not available)
        self.scrape_targets = [
            {
                "url": "https://www.bloomberg.com/crypto",
                "name": "Bloomberg Crypto",
                "country": "USA",
                "selectors": {
                    "articles": "article, div[class*='article'], li[class*='story']",
                    "title": "h2, h3, a[class*='headline']",
                    "link": "a",
                }
            },
            {
                "url": "https://www.reuters.com/technology/cryptocurrencies/",
                "name": "Reuters Crypto",
                "country": "USA",
                "selectors": {
                    "articles": "h3[data-testid='Link'], article",
                    "title": "h3, span[data-testid='Heading']",
                    "link": "a",
                }
            },
            {
                "url": "https://finance.yahoo.com/news",
                "name": "Yahoo Finance",
                "country": "USA",
                "selectors": {
                    "articles": "li[class*='story'], article",
                    "title": "h3, a[class*='headline']",
                    "link": "a",
                }
            },
        ]

    async def __aenter__(self):
        """Context manager entry"""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *args):
        """Context manager exit"""
        if self.session:
            await self.session.close()

    async def _fetch_internal(self) -> List[NewsItem]:
        """
        Fetch news from all scrape targets

        Returns:
            List of NewsItem objects
        """
        if not self.session:
            self.session = aiohttp.ClientSession()

        all_news_items: List[NewsItem] = []

        tasks = [
            self._scrape_target(target)
            for target in self.scrape_targets
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_news_items.extend(result)
            elif isinstance(result, Exception):
                logger.warning(f"Web scrape error: {str(result)}")

        logger.info(
            "web_scraper_fetch",
            total_items=len(all_news_items),
            targets_scraped=len(self.scrape_targets),
        )

        return all_news_items

    async def _scrape_target(self, target: Dict) -> List[NewsItem]:
        """
        Scrape a single target website

        Args:
            target: Dict with url, name, country, and CSS selectors

        Returns:
            List of NewsItem objects
        """
        try:
            # Rate limiting
            async with self.rate_limiter:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }

                timeout = aiohttp.ClientTimeout(total=15)
                async with self.session.get(
                    target["url"],
                    headers=headers,
                    timeout=timeout,
                    allow_redirects=True,
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"Scrape failed for {target['name']}: HTTP {resp.status}")
                        return []

                    html = await resp.text()

            # Parse HTML
            soup = BeautifulSoup(html, "html.parser")
            news_items = []

            # Find articles using selectors
            selectors = target.get("selectors", {})
            article_selector = selectors.get("articles", "article")
            title_selector = selectors.get("title", "h2, h3")
            link_selector = selectors.get("link", "a")

            articles = soup.select(article_selector)[:10]  # Limit to 10 articles

            for article in articles:
                try:
                    # Extract title
                    title_elem = article.select_one(title_selector)
                    title = (
                        title_elem.get_text(strip=True)
                        if title_elem
                        else "No title"
                    )

                    # Extract link
                    link_elem = article.select_one(link_selector)
                    link = link_elem.get("href", target["url"]) if link_elem else target["url"]

                    # Make absolute URL
                    if link.startswith("/"):
                        from urllib.parse import urljoin
                        link = urljoin(target["url"], link)
                    elif not link.startswith("http"):
                        link = target["url"]

                    # Create NewsItem
                    news_item = NewsItem(
                        id=md5(f"{link}".encode()).hexdigest()[:8],
                        title=title[:200],
                        content=f"{target['name']}: {title}"[:1000],
                        source_url=link,
                        source_name=target["name"],
                        published_at=datetime.now(timezone.utc),
                        fetched_at=datetime.now(timezone.utc),
                        country=target["country"],
                        category="news",
                        sentiment_score=0.0,
                        sentiment_label="neutral",
                    )

                    news_items.append(news_item)

                except Exception as e:
                    logger.debug(f"Error parsing article from {target['name']}: {str(e)}")
                    continue

            logger.info(
                "web_scraper_target_success",
                target=target["name"],
                items_count=len(news_items),
            )

            return news_items

        except asyncio.TimeoutError:
            logger.warning(f"Web scraper timeout for {target['name']}")
            return []
        except Exception as e:
            logger.error(f"Error scraping {target['name']}: {str(e)}")
            return []

    def add_scrape_target(self, url: str, name: str, country: str, selectors: Optional[Dict] = None):
        """
        Dynamically add a scrape target

        Args:
            url: URL to scrape
            name: Source name
            country: Country identifier
            selectors: CSS selectors for articles, titles, links
        """
        target = {
            "url": url,
            "name": name,
            "country": country,
            "selectors": selectors or {
                "articles": "article, div[class*='article']",
                "title": "h2, h3",
                "link": "a",
            }
        }

        self.scrape_targets.append(target)
        logger.info(
            "scrape_target_added",
            name=name,
            url=url,
        )

    def remove_scrape_target(self, name: str):
        """
        Remove a scrape target by name

        Args:
            name: Name of the scrape target to remove
        """
        self.scrape_targets = [
            t for t in self.scrape_targets
            if t["name"] != name
        ]
        logger.info("scrape_target_removed", name=name)
