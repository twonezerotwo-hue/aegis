"""
Sentinel AI — VIX Monitor

Korku Endeksi (VIX) izleme modülü.
"""
from typing import Optional
from datetime import datetime, timezone

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import VIXIndicator

logger = structlog.get_logger(__name__)


class VIXMonitor:
    """VIX İndicator monitoring."""

    def __init__(self, api_endpoint: str = "https://api.example.com/vix"):
        """
        Args:
            api_endpoint: VIX API endpoint
        """
        self.api_endpoint = api_endpoint
        self.current_vix = 20.0  # Default
        self.previous_vix = 20.0

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_vix(self) -> Optional[VIXIndicator]:
        """
        Fetch VIX data from API.

        Returns:
            VIXIndicator or None
        """
        try:
            # Mock implementation - in production use aiohttp
            self.previous_vix = self.current_vix
            # Simulated VIX value
            self.current_vix = 20.0  # Would get from API

            change_pct = ((self.current_vix - self.previous_vix) / self.previous_vix * 100) if self.previous_vix > 0 else 0

            # Determine regime
            if self.current_vix > 35:
                regime = "EXTREME_FEAR"
            elif self.current_vix > 25:
                regime = "FEAR"
            elif self.current_vix < 15:
                regime = "COMPLACENT"
            else:
                regime = "NORMAL"

            indicator = VIXIndicator(
                value=self.current_vix,
                change_pct=change_pct,
                regime=regime,
                timestamp=datetime.now(timezone.utc),
            )

            logger.info(
                "vix_fetched",
                vix=round(self.current_vix, 2),
                regime=regime,
            )

            return indicator

        except Exception as e:
            logger.error("vix_fetch_error", error=str(e))
            return None

    def calculate_multiplier_adjustment(self, vix_value: float) -> float:
        """
        VIX değerine göre multiplier adjustment hesapla.

        Args:
            vix_value: VIX index value

        Returns:
            Multiplier adjustment factor
        """
        multiplier = 1.0

        # VIX > 35 → multiplier = min(multiplier, 0.4)
        if vix_value > 35:
            multiplier = min(multiplier, 0.4)
            logger.warning("vix_extreme_fear", vix=vix_value)

        # VIX > 25 → multiplier = min(multiplier, 0.7)
        elif vix_value > 25:
            multiplier = min(multiplier, 0.7)
            logger.warning("vix_fear", vix=vix_value)

        # VIX < 15 → multiplier = multiplier * 1.1 (max 1.0)
        elif vix_value < 15:
            multiplier = min(multiplier * 1.1, 1.0)
            logger.info("vix_complacency", vix=vix_value)

        return multiplier

    def get_signal_strength(self, vix_value: float) -> float:
        """
        Get signal strength (confidence) based on VIX.

        Args:
            vix_value: VIX value

        Returns:
            Signal strength 0-1
        """
        # Extreme values have higher confidence
        if vix_value > 35 or vix_value < 12:
            return 0.9
        elif vix_value > 30 or vix_value < 15:
            return 0.7
        else:
            return 0.5
