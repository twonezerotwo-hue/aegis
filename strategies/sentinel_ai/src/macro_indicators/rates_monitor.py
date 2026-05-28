"""
Sentinel AI — Rates Monitor

Federal Reserve Faiz Oranları izleme modülü.
"""
from typing import Optional
from datetime import datetime, timezone

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import FedRatesIndicator

logger = structlog.get_logger(__name__)


class RatesMonitor:
    """Federal Reserve rates monitoring."""

    def __init__(self, api_endpoint: str = "https://api.example.com/fed-rates"):
        """
        Args:
            api_endpoint: Fed rates API endpoint
        """
        self.api_endpoint = api_endpoint
        self.current_rate = 4.5  # Default

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_rates(self) -> Optional[FedRatesIndicator]:
        """
        Fetch Federal Reserve rates.

        Returns:
            FedRatesIndicator or None
        """
        try:
            # Mock implementation - in production use aiohttp
            # Simulated FFR
            self.current_rate = 4.5  # Would get from API

            # Determine trend (would compare to previous)
            if self.current_rate > 5.0:
                trend = "HIGH"
            elif self.current_rate > 4.0:
                trend = "ELEVATED"
            else:
                trend = "MODERATE"

            indicator = FedRatesIndicator(
                current_rate=self.current_rate,
                trend=trend,
                timestamp=datetime.now(timezone.utc),
            )

            logger.info(
                "rates_fetched",
                ffr=round(self.current_rate, 3),
                trend=trend,
            )

            return indicator

        except Exception as e:
            logger.error("rates_fetch_error", error=str(e))
            return None

    def calculate_multiplier_adjustment(self, rate_value: float) -> float:
        """
        Fed faiz oranına göre multiplier adjustment.

        Args:
            rate_value: Federal Funds Rate (%)

        Returns:
            Multiplier adjustment factor
        """
        multiplier = 1.0

        # Faiz > 5.0 → multiplier = multiplier * 0.9
        if rate_value > 5.0:
            multiplier = multiplier * 0.9
            logger.warning("fed_rates_high", rate=rate_value)

        return multiplier

    def get_signal_strength(self, rate_value: float) -> float:
        """
        Get signal strength based on rates.

        Args:
            rate_value: Current FFR

        Returns:
            Signal strength 0-1
        """
        # Extreme rates have stronger signal
        if rate_value > 5.5 or rate_value < 0.5:
            return 0.7
        elif rate_value > 4.5:
            return 0.5
        else:
            return 0.3
