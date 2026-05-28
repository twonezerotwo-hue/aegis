"""
Sentinel AI — Oil Monitor

WTI Petrol Fiyatı izleme modülü.
"""
from typing import Optional
from datetime import datetime, timezone

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import OilPricesIndicator

logger = structlog.get_logger(__name__)


class OilMonitor:
    """WTI Oil prices monitoring."""

    def __init__(self, api_endpoint: str = "https://api.example.com/oil-wti"):
        """
        Args:
            api_endpoint: Oil prices API endpoint
        """
        self.api_endpoint = api_endpoint
        self.current_price = 80.0  # Default
        self.previous_price = 80.0

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_oil_prices(self) -> Optional[OilPricesIndicator]:
        """
        Fetch WTI oil prices.

        Returns:
            OilPricesIndicator or None
        """
        try:
            # Mock implementation - in production use aiohttp
            self.previous_price = self.current_price
            # Simulated WTI price
            self.current_price = 80.0  # Would get from API

            change_pct = ((self.current_price - self.previous_price) / self.previous_price * 100) if self.previous_price > 0 else 0

            # Determine trend
            if change_pct > 2:
                trend = "UP"
            elif change_pct < -2:
                trend = "DOWN"
            else:
                trend = "NEUTRAL"

            indicator = OilPricesIndicator(
                price_usd=self.current_price,
                change_pct=change_pct,
                trend=trend,
                timestamp=datetime.now(timezone.utc),
            )

            logger.info(
                "oil_prices_fetched",
                wti=round(self.current_price, 2),
                change_pct=round(change_pct, 2),
            )

            return indicator

        except Exception as e:
            logger.error("oil_fetch_error", error=str(e))
            return None

    def calculate_multiplier_adjustment(self, oil_price: float) -> float:
        """
        Petrol fiyatına göre multiplier adjustment.

        Args:
            oil_price: WTI price (USD/barrel)

        Returns:
            Multiplier adjustment factor
        """
        multiplier = 1.0

        # WTI > $100 → multiplier = multiplier * 0.85
        if oil_price > 100:
            multiplier = multiplier * 0.85
            logger.warning("oil_high_price", wti=oil_price)

        return multiplier

    def get_signal_strength(self, oil_price: float) -> float:
        """
        Get signal strength based on oil prices.

        Args:
            oil_price: WTI price

        Returns:
            Signal strength 0-1
        """
        # Extreme prices have higher confidence
        if oil_price > 120 or oil_price < 40:
            return 0.75
        elif oil_price > 100 or oil_price < 60:
            return 0.55
        else:
            return 0.3
