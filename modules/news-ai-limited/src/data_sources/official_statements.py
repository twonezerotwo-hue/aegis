"""
News AI Limited - Official Government Statements API Client

Fetches news from official government and central bank sources.
Supports Treasury, SEC, PBOC, TCMB, and other official channels.
"""
from typing import List, Optional
import aiohttp
import asyncio
from datetime import datetime, timezone
from hashlib import md5
from bs4 import BeautifulSoup
from ..signal_models import NewsItem
from .base_source import BaseDataSource
from ..logging.logger_config import get_logger

logger = get_logger(__name__)


class OfficialStatementsAPI(BaseDataSource):
    """Fetches news from official government and central bank APIs"""

    def __init__(self):
        """Initialize official statements API client"""
        super().__init__(
            source_name="Official Statements",
            country="GLOBAL",
            is_enabled=True,
        )
        self.session: Optional[aiohttp.ClientSession] = None

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
        Fetch news from all official sources

        Returns:
            List of NewsItem objects
        """
        if not self.session:
            self.session = aiohttp.ClientSession()

        all_news_items: List[NewsItem] = []

        # Fetch from all official sources concurrently
        tasks = [
            self._fetch_treasury(),
            self._fetch_sec(),
            self._fetch_pboc(),
            self._fetch_tcmb(),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_news_items.extend(result)
            elif isinstance(result, Exception):
                logger.warning(f"Official API fetch error: {str(result)}")

        logger.info(
            "official_statements_fetch",
            total_items=len(all_news_items),
        )

        return all_news_items

    async def _fetch_treasury(self) -> List[NewsItem]:
        """Fetch from US Treasury"""
        try:
            # Treasury has a press releases page
            url = "https://home.treasury.gov/news/press-releases"
            headers = {"User-Agent": "Mozilla/5.0"}

            async with self.session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return []

                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")

                news_items = []
                for article in soup.find_all("article")[:10]:
                    try:
                        title_tag = article.find("h2") or article.find("h3")
                        title = title_tag.get_text(strip=True) if title_tag else "No title"

                        link_tag = article.find("a")
                        link = link_tag["href"] if link_tag else url

                        # Make absolute URL
                        if not link.startswith("http"):
                            link = "https://home.treasury.gov" + link

                        news_item = NewsItem(
                            id=md5(f"{link}".encode()).hexdigest()[:8],
                            title=title[:200],
                            content=f"US Treasury press release: {title}"[:1000],
                            source_url=link,
                            source_name="US Treasury",
                            published_at=datetime.now(timezone.utc),
                            fetched_at=datetime.now(timezone.utc),
                            country="USA",
                            category="regulatory",
                            sentiment_score=0.0,
                            sentiment_label="neutral",
                        )
                        news_items.append(news_item)
                    except Exception as e:
                        logger.warning(f"Error parsing Treasury article: {str(e)}")
                        continue

                return news_items

        except Exception as e:
            logger.error(f"Error fetching Treasury statements: {str(e)}")
            return []

    async def _fetch_sec(self) -> List[NewsItem]:
        """Fetch from US SEC"""
        try:
            # SEC has a REST API for press releases
            url = "https://www.sec.gov/news/press-releases"
            headers = {"User-Agent": "Mozilla/5.0"}

            async with self.session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return []

                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")

                news_items = []
                for article in soup.find_all("div", class_="news-item")[:10]:
                    try:
                        title_tag = article.find("h2")
                        title = title_tag.get_text(strip=True) if title_tag else "No title"

                        link_tag = article.find("a")
                        link = link_tag["href"] if link_tag else url

                        news_item = NewsItem(
                            id=md5(f"{link}".encode()).hexdigest()[:8],
                            title=title[:200],
                            content=f"SEC press release: {title}"[:1000],
                            source_url=link if link.startswith("http") else f"https://www.sec.gov{link}",
                            source_name="US SEC",
                            published_at=datetime.now(timezone.utc),
                            fetched_at=datetime.now(timezone.utc),
                            country="USA",
                            category="regulatory",
                            sentiment_score=0.0,
                            sentiment_label="neutral",
                        )
                        news_items.append(news_item)
                    except Exception as e:
                        logger.warning(f"Error parsing SEC article: {str(e)}")
                        continue

                return news_items

        except Exception as e:
            logger.error(f"Error fetching SEC statements: {str(e)}")
            return []

    async def _fetch_pboc(self) -> List[NewsItem]:
        """Fetch from People's Bank of China"""
        try:
            # PBOC news page (English version)
            url = "https://www.pbc.gov.cn/english/130490/130516/"
            headers = {"User-Agent": "Mozilla/5.0"}

            async with self.session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return []

                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")

                news_items = []
                for article in soup.find_all("li")[:10]:
                    try:
                        link_tag = article.find("a")
                        if not link_tag:
                            continue

                        title = link_tag.get_text(strip=True)
                        href = link_tag.get("href", "")

                        if not title or not href:
                            continue

                        news_item = NewsItem(
                            id=md5(f"{href}".encode()).hexdigest()[:8],
                            title=title[:200],
                            content=f"PBOC announcement: {title}"[:1000],
                            source_url=href if href.startswith("http") else f"https://www.pbc.gov.cn{href}",
                            source_name="People's Bank of China",
                            published_at=datetime.now(timezone.utc),
                            fetched_at=datetime.now(timezone.utc),
                            country="China",
                            category="regulatory",
                            sentiment_score=0.0,
                            sentiment_label="neutral",
                        )
                        news_items.append(news_item)
                    except Exception as e:
                        logger.warning(f"Error parsing PBOC article: {str(e)}")
                        continue

                return news_items

        except Exception as e:
            logger.error(f"Error fetching PBOC statements: {str(e)}")
            return []

    async def _fetch_tcmb(self) -> List[NewsItem]:
        """Fetch from Turkish Central Bank"""
        try:
            # TCMB news page
            url = "https://www.tcmb.gov.tr/wps/wcm/connect/EN/TCMB2/Main+Menu/Press+Office/News"
            headers = {"User-Agent": "Mozilla/5.0"}

            async with self.session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return []

                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")

                news_items = []
                for article in soup.find_all("a", {"class": "featured-article"})[:10]:
                    try:
                        title = article.get_text(strip=True)
                        href = article.get("href", "")

                        news_item = NewsItem(
                            id=md5(f"{href}".encode()).hexdigest()[:8],
                            title=title[:200],
                            content=f"TCMB announcement: {title}"[:1000],
                            source_url=href if href.startswith("http") else f"https://www.tcmb.gov.tr{href}",
                            source_name="Turkish Central Bank",
                            published_at=datetime.now(timezone.utc),
                            fetched_at=datetime.now(timezone.utc),
                            country="Turkey",
                            category="regulatory",
                            sentiment_score=0.0,
                            sentiment_label="neutral",
                        )
                        news_items.append(news_item)
                    except Exception as e:
                        logger.warning(f"Error parsing TCMB article: {str(e)}")
                        continue

                return news_items

        except Exception as e:
            logger.error(f"Error fetching TCMB statements: {str(e)}")
            return []
