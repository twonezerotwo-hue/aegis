"""
Quantum AI Limited — Cross-Exchange Arbitrage

Farklı exchange'ler arasında fiyat farkı tespiti.
"""
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ArbOpportunity:
    """Arbitrage fırsatı."""
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    spread: float  # satış fiyatı - alış fiyatı
    spread_pct: float  # % olarak spread
    timestamp: datetime


class CrossExchangeArbitrage:
    """Cross-exchange arbitrage fırsatlarını tespit et."""

    def __init__(self, min_spread_bps: float = 10.0):
        """
        Args:
            min_spread_bps: Minimum spread (basis points)
        """
        self.min_spread_bps = min_spread_bps

    def detect_opportunity(
        self,
        symbol: str,
        exchange_prices: Dict[str, float],  # {exchange: price}
    ) -> Optional[ArbOpportunity]:
        """
        Arbitrage fırsatı tespit et.

        Args:
            symbol: Trading çifti
            exchange_prices: Her exchange'den fiyat

        Returns:
            ArbOpportunity veya None
        """
        if len(exchange_prices) < 2:
            return None

        # En düşük ve en yüksek fiyat bul
        sorted_prices = sorted(exchange_prices.items(), key=lambda x: x[1])
        buy_exchange, buy_price = sorted_prices[0]
        sell_exchange, sell_price = sorted_prices[-1]

        # Spread hesapla
        spread = sell_price - buy_price
        spread_pct = (spread / buy_price) * 100
        spread_bps = spread_pct * 100

        # Threshold kontrol
        if spread_bps < self.min_spread_bps:
            return None

        opportunity = ArbOpportunity(
            symbol=symbol,
            buy_exchange=buy_exchange,
            sell_exchange=sell_exchange,
            buy_price=buy_price,
            sell_price=sell_price,
            spread=spread,
            spread_pct=spread_pct,
            timestamp=datetime.now(),
        )

        logger.info(
            "arbitrage_opportunity_detected",
            symbol=symbol,
            spread_bps=round(spread_bps, 2),
            buy_exchange=buy_exchange,
            sell_exchange=sell_exchange,
        )

        return opportunity

    def filter_opportunities(
        self,
        opportunities: List[ArbOpportunity],
        max_opportunities: int = 5,
    ) -> List[ArbOpportunity]:
        """
        İmkan listesini filtrele (en büyük spread'ler).

        Args:
            opportunities: Olası arbitrage fırsatları
            max_opportunities: Maksimum fırsat sayısı

        Returns:
            Filtrelenmiş fırsatlar
        """
        # Spread'e göre sırala (büyükten küçüğe)
        sorted_opps = sorted(
            opportunities,
            key=lambda x: x.spread,
            reverse=True,
        )
        return sorted_opps[:max_opportunities]

    def calculate_pnl(
        self,
        opportunity: ArbOpportunity,
        position_size: float,
        fees: Dict[str, float],  # {exchange: fee_pct}
    ) -> float:
        """
        Arbitrage kar-zarar hesapla.

        Args:
            opportunity: Arbitrage fırsatı
            position_size: İşlem büyüklüğü
            fees: Exchange ücretleri

        Returns:
            Beklenen kar (USD)
        """
        buy_fee = fees.get(opportunity.buy_exchange, 0.001)
        sell_fee = fees.get(opportunity.sell_exchange, 0.001)

        effective_spread = opportunity.spread - (
            opportunity.buy_price * buy_fee +
            opportunity.sell_price * sell_fee
        )

        pnl = effective_spread * position_size

        logger.info(
            "arbitrage_pnl_calculated",
            symbol=opportunity.symbol,
            pnl=round(pnl, 2),
            effective_spread_pct=round((effective_spread / opportunity.buy_price) * 100, 4),
        )

        return pnl
