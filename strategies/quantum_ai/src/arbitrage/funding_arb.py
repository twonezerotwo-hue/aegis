"""
Quantum AI Limited — Funding Rate Arbitrage

Perpetual ve spot arasındaki funding rate farkından kâr elde et.
"""
from typing import Dict, Optional
from dataclasses import dataclass
from datetime import datetime

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class FundingRateData:
    """Funding rate bilgisi."""
    symbol: str
    perpetual_rate: float  # 0.0001 = 0.01%
    spot_price: float
    perpetual_price: float
    funding_interval: int  # Secondes
    timestamp: datetime


@dataclass
class FundingArbOpportunity:
    """Funding arbitrage fırsatı."""
    symbol: str
    funding_rate: float
    annualized_return: float
    spot_price: float
    perpetual_price: float
    funding_timestamps: list  # Next 3 funding times
    timestamp: datetime


class FundingRateArbitrage:
    """Perpetual funding rate arbitrage."""

    def __init__(self, min_apy: float = 0.05):
        """
        Args:
            min_apy: Minimum annual percentage yield
        """
        self.min_apy = min_apy

    def detect_opportunity(
        self,
        funding_data: FundingRateData,
    ) -> Optional[FundingArbOpportunity]:
        """
        Funding rate arbitrage fırsatı tespit et.

        Args:
            funding_data: Funding rate bilgisi

        Returns:
            FundingArbOpportunity veya None
        """
        # Annualized return hesapla
        # APY = funding_rate * 365 * 24 * 60 * 60 / interval
        intervals_per_year = 365 * 24 * 60 * 60 / funding_data.funding_interval
        apy = funding_data.perpetual_rate * intervals_per_year

        if apy < self.min_apy:
            logger.debug(
                "funding_rate_below_threshold",
                symbol=funding_data.symbol,
                apy=round(apy, 4),
            )
            return None

        # Funding timestamps
        funding_timestamps = self._calculate_next_funding_times(
            funding_data.funding_interval, 3
        )

        opportunity = FundingArbOpportunity(
            symbol=funding_data.symbol,
            funding_rate=funding_data.perpetual_rate,
            annualized_return=apy,
            spot_price=funding_data.spot_price,
            perpetual_price=funding_data.perpetual_price,
            funding_timestamps=funding_timestamps,
            timestamp=datetime.now(),
        )

        logger.info(
            "funding_arbitrage_detected",
            symbol=funding_data.symbol,
            apy=round(apy, 4),
            funding_rate=funding_data.perpetual_rate,
        )

        return opportunity

    def calculate_pnl(
        self,
        opportunity: FundingArbOpportunity,
        position_size: float,
        holding_periods: int = 3,  # Number of funding payments
    ) -> float:
        """
        Funding arbitrage kar-zarar hesapla.

        Args:
            opportunity: Funding arbitrage fırsatı
            position_size: İşlem büyüklüğü
            holding_periods: Kaç funding periyodu tutulacak

        Returns:
            Beklenen kar (USD)
        """
        # Total return = funding_rate * holding_periods
        total_funding = opportunity.funding_rate * holding_periods
        pnl = total_funding * opportunity.spot_price * position_size

        logger.info(
            "funding_arbitrage_pnl",
            symbol=opportunity.symbol,
            pnl=round(pnl, 2),
            total_funding_pct=round(total_funding * 100, 4),
        )

        return pnl

    def calculate_carry_return(
        self,
        funding_rates: Dict[str, float],  # {symbol: rate}
        position_sizes: Dict[str, float],  # {symbol: size}
        spot_prices: Dict[str, float],  # {symbol: price}
        holding_days: float = 30,
    ) -> Dict[str, float]:
        """
        Portfolio funding carry return hesapla.

        Args:
            funding_rates: Her sembol için funding rate
            position_sizes: Her sembol için pozisyon
            spot_prices: Her sembol için spot fiyat
            holding_days: Elinde tutma periodu

        Returns:
            {symbol: carry_return} mapping
        """
        carry_returns = {}

        funding_interval_seconds = 8 * 60 * 60  # 8 hours (typical)
        periods_per_day = 24 * 60 * 60 / funding_interval_seconds

        for symbol in funding_rates:
            rate = funding_rates.get(symbol, 0.0)
            size = position_sizes.get(symbol, 0.0)
            price = spot_prices.get(symbol, 0.0)

            if size == 0 or price == 0:
                continue

            daily_return = rate * periods_per_day * price * size
            carry_returns[symbol] = daily_return * holding_days

        return carry_returns

    @staticmethod
    def _calculate_next_funding_times(
        interval_seconds: int,
        num_times: int,
    ) -> list:
        """Calculate next N funding times."""
        times = []
        now = datetime.now()

        for i in range(1, num_times + 1):
            next_time = datetime.fromtimestamp(
                now.timestamp() + (i * interval_seconds)
            )
            times.append(next_time)

        return times
