"""
Sentinel AI — Fear & Greed Monitor

Fear & Greed Index izleme modülü.
"""
from typing import Optional
from datetime import datetime, timezone

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import FearGreedIndicator

logger = structlog.get_logger(__name__)


class FearGreedMonitor:
    """Fear & Greed Index monitoring."""

    def __init__(self, api_endpoint: str = "https://api.example.com/fear-greed"):
        """
        Args:
            api_endpoint: Fear & Greed API endpoint
        """
        self.api_endpoint = api_endpoint
        self.current_index = 50.0  # Default

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_fear_greed(self) -> Optional[FearGreedIndicator]:
        """
        Fetch Fear & Greed data from API.

        Returns:
            FearGreedIndicator or None
        """
        try:
            # Mock implementation - in production use aiohttp
            # Simulated Fear & Greed value (0-100)
            self.current_index = 50.0  # Would get from API

            # Classify
            if self.current_index < 20:
                classification = "Extreme Fear"
            elif self.current_index < 40:
                classification = "Fear"
            elif self.current_index < 60:
                classification = "Neutral"
            elif self.current_index < 80:
                classification = "Greed"
            else:
                classification = "Extreme Greed"

            indicator = FearGreedIndicator(
                value=self.current_index,
                classification=classification,
                timestamp=datetime.now(timezone.utc),
                components={
                    "momentum": 50.0,
                    "stock_price_strength": 50.0,
                    "junk_bond_demand": 50.0,
                    "market_volatility": 50.0,
                    "safe_haven_demand": 50.0,
                },
            )

            logger.info(
                "fear_greed_fetched",
                index=round(self.current_index, 1),
                classification=classification,
            )

            return indicator

        except Exception as e:
            logger.error("fear_greed_fetch_error", error=str(e))
            return None

    def calculate_multiplier_adjustment(self, index_value: float) -> float:
        """
        Fear & Greed değerine göre multiplier adjustment.

        Args:
            index_value: Fear & Greed index (0-100)

        Returns:
            Multiplier adjustment factor
        """
        multiplier = 1.0

        # Index < 20 (Extreme Fear) → multiplier = multiplier * 0.7
        if index_value < 20:
            multiplier = multiplier * 0.7
            logger.warning("extreme_fear_detected", index=index_value)

        # Index < 40 (Fear) → multiplier = multiplier * 0.9
        elif index_value < 40:
            multiplier = multiplier * 0.9
            logger.info("fear_detected", index=index_value)

        # Index > 80 (Extreme Greed) → multiplier = multiplier * 0.8
        elif index_value > 80:
            multiplier = multiplier * 0.8
            logger.warning("extreme_greed_detected", index=index_value)

        return multiplier

    def get_signal_strength(self, index_value: float) -> float:
        """
        Get signal strength based on Fear & Greed.

        Args:
            index_value: Index value

        Returns:
            Signal strength 0-1
        """
        # Extreme values have higher confidence
        if index_value < 20 or index_value > 80:
            return 0.85
        elif index_value < 40 or index_value > 70:
            return 0.65
        else:
            return 0.4
