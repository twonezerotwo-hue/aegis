"""
Order Manager — Emir yönetimi ve izleme
"""
from typing import Dict, List, Tuple
from datetime import datetime, timezone
import requests

import structlog

from ..core.models import Order, OrderStatus, OrderSide

logger = structlog.get_logger(__name__)


class OrderManager:
    """Active emirleri yönet, izle ve kapat."""

    def __init__(self, max_order_age_seconds: float = 30.0):
        self.orders: Dict[str, Order] = {}
        self.max_order_age_seconds = max_order_age_seconds

    def get_quantum_liquidity(self) -> float:
        """Get liquidity score from Quantum AI (0-1)"""
        try:
            quantum_urls = [
                "http://aegis-quantum:8003",  # Docker network
                "http://quantum-api:8003",    # Docker compose
                "http://localhost:8003"       # Fallback
            ]

            for url in quantum_urls:
                try:
                    response = requests.get(
                        f"{url}/liquidity",
                        timeout=2
                    )

                    if response.status_code == 200:
                        data = response.json()
                        liquidity = float(data.get('liquidity_score', 0.6))
                        logger.info("liquidity_fetched", score=round(liquidity, 2))
                        return liquidity
                except:
                    continue
        except:
            pass

        logger.warning("liquidity_fetch_failed", using_default=0.6)
        return 0.6

    def apply_signal_quality_filters(
        self,
        entry_signal: float,
        liquidity: float,
        order_book_skewness: float = 0.0,
    ) -> Tuple[float, Dict[str, float]]:
        """
        COMPONENT 4: Quantum AI signal quality filters.
        Reduce confidence based on market conditions.

        Args:
            entry_signal: Original entry signal strength (0-1)
            liquidity: Liquidity score from get_quantum_liquidity() (0-1)
            order_book_skewness: Bid/Ask imbalance (-1 to 1, 0 = balanced)

        Returns:
            (adjusted_confidence, filter_breakdown)
        """
        adjusted_confidence = entry_signal
        filters = {}

        # Liquidity filter: liquidity < 0.4 → reduce confidence by 30%
        if liquidity < 0.4:
            liquidity_reduction = 0.30
            adjusted_confidence *= (1.0 - liquidity_reduction)
            filters["liquidity"] = 1.0 - liquidity_reduction
            logger.info("signal_filter_low_liquidity", liquidity=liquidity, reduction=liquidity_reduction)
        else:
            filters["liquidity"] = 1.0

        # Order book skewness filter: |skewness| > 0.6 → reduce by 20%
        if abs(order_book_skewness) > 0.6:
            skewness_reduction = 0.20
            adjusted_confidence *= (1.0 - skewness_reduction)
            filters["order_book_skewness"] = 1.0 - skewness_reduction
            logger.info(
                "signal_filter_skewed_orderbook",
                skewness=order_book_skewness,
                reduction=skewness_reduction
            )
        else:
            filters["order_book_skewness"] = 1.0

        return adjusted_confidence, filters

    def should_fragment_orders(self, liquidity: float) -> bool:
        """
        COMPONENT 4: Determine if orders should be fragmented into smaller chunks.
        Fragment ONLY if liquidity < 0.3 (keep existing threshold).

        Args:
            liquidity: Liquidity score from get_quantum_liquidity()

        Returns:
            True if should fragment, False otherwise
        """
        return liquidity < 0.3

    def add_order(self, order: Order) -> None:
        """Emiri ekle."""
        self.orders[order.order_id] = order
        logger.info("order_added", order_id=order.order_id, symbol=order.symbol)

    def update_order(self, order: Order) -> None:
        """Emiri güncelle."""
        if order.order_id in self.orders:
            self.orders[order.order_id] = order

    def get_active_orders(self, symbol: str = None) -> List[Order]:
        """Active emirleri getir."""
        active = [
            o for o in self.orders.values()
            if o.status in [OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIAL]
        ]

        if symbol:
            active = [o for o in active if o.symbol == symbol]

        return active

    def cancel_old_orders(self) -> List[str]:
        """Çok eski emirleri iptal et."""
        now = datetime.now(timezone.utc)
        canceled_ids = []

        for order_id, order in self.orders.items():
            age = (now - order.created_at).total_seconds()

            if age > self.max_order_age_seconds and order.status in [
                OrderStatus.PENDING,
                OrderStatus.SUBMITTED,
            ]:
                order.status = OrderStatus.CANCELED
                canceled_ids.append(order_id)

                logger.info(
                    "order_canceled_timeout",
                    order_id=order_id,
                    age_seconds=round(age, 2),
                )

        return canceled_ids

    def get_net_position(self, symbol: str) -> float:
        """Sembol için net pozisyonu hesapla."""
        net = 0.0

        for order in self.get_active_orders(symbol):
            if order.side == OrderSide.BUY:
                net += order.filled_qty
            else:
                net -= order.filled_qty

        return net

    def get_inventory_risk(self) -> Dict[str, float]:
        """Tüm semboller için envanter riskini hesapla."""
        risk = {}

        for symbol in set(o.symbol for o in self.orders.values()):
            risk[symbol] = self.get_net_position(symbol)

        return risk

    def split_order_for_liquidity(self, order: Order, num_chunks: int = 10) -> List[Order]:
        """KURAL 2: Likidite düşükse emirleri parçala (TWAP)"""
        if num_chunks <= 1:
            return [order]

        # Emir boyutunu küçük parçalara böl
        chunk_qty = order.quantity / num_chunks
        chunks = []

        for i in range(num_chunks):
            chunk_order = Order(
                symbol=order.symbol,
                side=order.side,
                quantity=chunk_qty,
                order_type=order.order_type,
                price=order.price if hasattr(order, 'price') else None
            )
            chunks.append(chunk_order)

        logger.warning(
            "order_split_for_liquidity",
            original_qty=order.quantity,
            chunk_qty=chunk_qty,
            num_chunks=num_chunks
        )

        return chunks

    def process_order_with_liquidity_check(self, order: Order) -> Tuple[bool, List[Order]]:
        """
        Likidite durumuna göre emri işle:
        - Likidite > 0.3: Normal emir
        - Likidite < 0.3: 10 parçaya böl (TWAP)
        """
        liquidity = self.get_quantum_liquidity()

        if liquidity < 0.3:
            logger.warning(f"⚠️  LİKİDİTE DÜŞÜK ({liquidity:.2f}) → Emir 10 parçaya bölünüyor (TWAP)")
            chunks = self.split_order_for_liquidity(order, num_chunks=10)
            return False, chunks

        logger.info(f"✅ Likidite yeterli ({liquidity:.2f}), normal emir")
        return True, [order]
