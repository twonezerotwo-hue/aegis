"""
News AI Limited - Base Data Source Class

Abstract base class for all data sources (RSS, APIs, Web Scraping).
Implements common resilience patterns: circuit breaker, retry, rate limiting.
"""
from abc import ABC, abstractmethod
from typing import List
from ..signal_models import NewsItem
from ..logging.logger_config import get_logger
from pybreaker import CircuitBreaker
from tenacity import retry, wait_exponential, stop_after_attempt
import asyncio

logger = get_logger(__name__)


class BaseDataSource(ABC):
    """Abstract base class for all data sources"""

    def __init__(self, source_name: str, country: str, is_enabled: bool = True, max_failures: int = 5):
        """
        Initialize data source with resilience patterns

        Args:
            source_name: Name of source (e.g., "Reuters", "SEC", "CoinDesk")
            country: Country code (USA, China, Russia, Turkey)
            is_enabled: Whether source is active
            max_failures: Threshold for circuit breaker
        """
        self.source_name = source_name
        self.country = country
        self.is_enabled = is_enabled

        # Circuit breaker: Fail fast after N failures
        self.circuit_breaker = CircuitBreaker(
            fail_max=max_failures,
            reset_timeout=60,  # Try again after 60 seconds
            exclude=[asyncio.TimeoutError],
        )

        self.total_fetches = 0
        self.failed_fetches = 0

    async def fetch(self) -> List[NewsItem]:
        """
        Fetch news from this source

        Implements:
        1. Circuit breaker (fail fast if too many errors)
        2. Retry logic (exponential backoff)
        3. Error handling and logging

        Returns:
            List of NewsItem objects
        """
        if not self.is_enabled:
            logger.info(f"source_disabled: {self.source_name}")
            return []

        try:
            self.total_fetches += 1

            # Circuit breaker protection
            if self.circuit_breaker.fail_counter >= self.circuit_breaker.fail_max:
                logger.warning(
                    "circuit_breaker_open",
                    source=self.source_name,
                    fail_counter=self.circuit_breaker.fail_counter,
                )
                return []

            # Actual fetch with retry logic
            news_items = await self._fetch_with_retry()

            logger.info(
                "source_fetch_success",
                source=self.source_name,
                items_count=len(news_items),
            )

            return news_items

        except Exception as e:
            self.failed_fetches += 1
            self.circuit_breaker.fail_counter += 1
            logger.error(
                "source_fetch_failed",
                source=self.source_name,
                error=str(e),
                fail_counter=self.circuit_breaker.fail_counter,
            )
            return []

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _fetch_with_retry(self) -> List[NewsItem]:
        """Fetch with automatic retry (exponential backoff)"""
        return await self._fetch_internal()

    @abstractmethod
    async def _fetch_internal(self) -> List[NewsItem]:
        """
        Actual fetch implementation (to be overridden by subclasses)

        Returns:
            List of NewsItem objects
        """
        pass

    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        if self.total_fetches == 0:
            return 1.0
        return (self.total_fetches - self.failed_fetches) / self.total_fetches

    @property
    def is_healthy(self) -> bool:
        """Check if source is healthy (circuit not open)"""
        return self.circuit_breaker.fail_counter < self.circuit_breaker.fail_max
