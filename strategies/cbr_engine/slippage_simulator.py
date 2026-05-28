"""
AEGIS CBR Engine - FAZ 6: Slippage Simulator
Realistic fill simulation based on order book depth and market impact
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class OrderBookLevel:
    """Single level in order book"""
    price: float
    volume: float


@dataclass
class ExecutionResult:
    """Order execution result"""
    filled_quantity: float
    average_fill_price: float
    total_cost: float  # filled_qty * avg_fill_price
    slippage_bps: float  # Basis points from mid price
    partial_fill: bool
    execution_time_ms: float = 0.0


class OrderBook:
    """
    Simulated order book for BTC/USD or other instruments.
    """

    def __init__(self, mid_price: float, spread_bps: float = 5, depth: int = 10):
        """
        Args:
            mid_price: Current mid price
            spread_bps: Bid-ask spread in basis points
            depth: Number of levels on each side
        """
        self.mid_price = mid_price
        self.spread_bps = spread_bps
        self.depth = depth

        # Generate realistic order book
        self.bids = self._generate_bids()
        self.asks = self._generate_asks()

        logger.info(f"OrderBook initialized: mid={mid_price:.2f}, spread={spread_bps}bps")

    def _generate_bids(self) -> List[OrderBookLevel]:
        """Generate bid-side order book (buy orders)"""
        bids = []
        bid_price = self.mid_price * (1 - self.spread_bps / 20000)  # Half spread

        for i in range(self.depth):
            # Prices move down, volume increases as price decreases
            price = bid_price * (1 - i * 0.002)  # 20bps per level
            volume = 0.1 + i * 0.05  # Increasing volume

            bids.append(OrderBookLevel(price=price, volume=volume))

        return bids

    def _generate_asks(self) -> List[OrderBookLevel]:
        """Generate ask-side order book (sell orders)"""
        asks = []
        ask_price = self.mid_price * (1 + self.spread_bps / 20000)  # Half spread

        for i in range(self.depth):
            # Prices move up, volume increases as price increases
            price = ask_price * (1 + i * 0.002)  # 20bps per level
            volume = 0.1 + i * 0.05  # Increasing volume

            asks.append(OrderBookLevel(price=price, volume=volume))

        return asks

    def get_vwap(self, side: str, quantity: float) -> Tuple[float, float, bool]:
        """
        Calculate Volume Weighted Average Price for order execution.

        Args:
            side: 'BUY' or 'SELL'
            quantity: Order quantity

        Returns:
            (avg_price, filled_quantity, partial_fill)
        """
        levels = self.asks if side == 'BUY' else self.bids
        filled_qty = 0.0
        total_cost = 0.0
        partial_fill = False

        for level in levels:
            if filled_qty >= quantity:
                break

            take_qty = min(quantity - filled_qty, level.volume)
            filled_qty += take_qty
            total_cost += take_qty * level.price

            if take_qty < level.volume:
                partial_fill = True
                break

        avg_price = total_cost / filled_qty if filled_qty > 0 else 0

        return avg_price, filled_qty, partial_fill

    def apply_market_impact(
        self,
        side: str,
        quantity: float,
        market_volatility: float = 0.02
    ) -> float:
        """
        Estimate market impact (additional slippage from price movement).

        Args:
            side: 'BUY' or 'SELL'
            quantity: Order quantity in BTC
            market_volatility: Daily volatility (affects impact)

        Returns:
            Market impact in basis points
        """
        # Market impact ~ sqrt(quantity / average_volume)
        average_volume = sum(level.volume for level in (self.asks if side == 'BUY' else self.bids)) / self.depth

        if average_volume == 0:
            return 0.0

        # Market impact formula: impact = sqrt(Q/V) * volatility * K
        # K is market impact coefficient (typically 0.01-0.05 for crypto)
        impact_ratio = np.sqrt(quantity / average_volume)
        market_impact = impact_ratio * market_volatility * 100 * 0.03  # 3% coefficient

        # Impact in basis points
        market_impact_bps = market_impact * 100

        return min(market_impact_bps, 500)  # Cap at 500bps


class SlippageSimulator:
    """
    Simulate realistic slippage for paper trading orders.

    Components:
    1. Bid-ask spread
    2. Market impact (order size effect)
    3. Partial fills
    4. Volatility impact
    """

    def __init__(
        self,
        mid_price: float = 45000,
        spread_bps: float = 5,
        commission_bps: float = 10,  # 10bps commission
        market_volatility: float = 0.02,
    ):
        """
        Args:
            mid_price: Current mid price
            spread_bps: Bid-ask spread in basis points
            commission_bps: Trading commission in basis points
            market_volatility: Market volatility (affects impact)
        """
        self.order_book = OrderBook(mid_price, spread_bps)
        self.commission_bps = commission_bps
        self.market_volatility = market_volatility
        self.trade_history = []

        logger.info(
            f"SlippageSimulator initialized: "
            f"spread={spread_bps}bps, commission={commission_bps}bps"
        )

    def execute_order(
        self,
        side: str,  # 'BUY' or 'SELL'
        quantity: float,
        order_type: str = 'MARKET',  # 'MARKET' or 'LIMIT'
        limit_price: Optional[float] = None,
        execution_delay_ms: float = 0.0,
    ) -> ExecutionResult:
        """
        Execute an order with realistic slippage.

        Args:
            side: 'BUY' or 'SELL'
            quantity: Order quantity
            order_type: 'MARKET' or 'LIMIT'
            limit_price: Limit price (for limit orders)
            execution_delay_ms: Simulated network/execution delay

        Returns:
            ExecutionResult with filled price, slippage, etc.
        """
        # Get VWAP and check for partial fill
        vwap_price, filled_qty, partial_fill = self.order_book.get_vwap(side, quantity)

        # Calculate slippage components
        bid_ask_slippage_bps = self.order_book.spread_bps / 2
        market_impact_bps = self.order_book.apply_market_impact(side, filled_qty, self.market_volatility)

        # Total slippage (negative for buys, positive for sells)
        if side == 'BUY':
            # Buying pays asking side
            slippage_bps = bid_ask_slippage_bps + market_impact_bps + self.commission_bps
            fill_price = self.order_book.mid_price * (1 + slippage_bps / 10000)
        else:
            # Selling gets bidding side
            slippage_bps = -(bid_ask_slippage_bps + market_impact_bps + self.commission_bps)
            fill_price = self.order_book.mid_price * (1 + slippage_bps / 10000)

        total_cost = filled_qty * fill_price

        result = ExecutionResult(
            filled_quantity=filled_qty,
            average_fill_price=fill_price,
            total_cost=total_cost,
            slippage_bps=slippage_bps,
            partial_fill=partial_fill,
            execution_time_ms=execution_delay_ms,
        )

        # Log trade
        self.trade_history.append({
            'side': side,
            'requested_qty': quantity,
            'filled_qty': filled_qty,
            'fill_price': fill_price,
            'slippage_bps': slippage_bps,
            'partial': partial_fill,
        })

        logger.info(
            f"Order executed: {side} {filled_qty:.4f} @ {fill_price:.2f} "
            f"(slippage: {slippage_bps:.1f}bps, partial: {partial_fill})"
        )

        return result

    def update_market_state(self, new_mid_price: float, new_spread_bps: Optional[float] = None):
        """Update order book with new market state"""
        self.order_book.mid_price = new_mid_price
        if new_spread_bps is not None:
            self.order_book.spread_bps = new_spread_bps

        # Regenerate order book
        self.order_book.bids = self.order_book._generate_bids()
        self.order_book.asks = self.order_book._generate_asks()

        logger.debug(f"Market state updated: mid={new_mid_price:.2f}")

    def get_statistics(self) -> Dict:
        """Calculate average slippage statistics"""
        if not self.trade_history:
            return {}

        slippages = [t['slippage_bps'] for t in self.trade_history]
        partial_count = sum(1 for t in self.trade_history if t['partial'])

        return {
            'total_trades': len(self.trade_history),
            'avg_slippage_bps': float(np.mean(np.abs(slippages))),
            'max_slippage_bps': float(np.max(np.abs(slippages))),
            'min_slippage_bps': float(np.min(np.abs(slippages))),
            'partial_fill_rate': float(partial_count / len(self.trade_history)),
            'buy_count': sum(1 for t in self.trade_history if t['side'] == 'BUY'),
            'sell_count': sum(1 for t in self.trade_history if t['side'] == 'SELL'),
        }

    def get_trade_history(self) -> List[Dict]:
        """Return all executed trades"""
        return self.trade_history.copy()

    def reset(self):
        """Clear trade history"""
        self.trade_history = []
        logger.info("Slippage simulator reset")
