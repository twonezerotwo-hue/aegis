"""
Quantum AI Limited — Avellaneda-Stoikov Market Making Algorithm

Two-sided market making with inventory control and dynamic spreads.

bid_price = mid_price - spread/2 - skew * inventory
ask_price = mid_price + spread/2 - skew * inventory

spread = gamma * sigma^2 * t + (2/gamma) * ln(1 + gamma/kappa)
"""
import math
from datetime import datetime, timezone

import structlog

from ..core.models import TwoSidedQuote, MMParameters

logger = structlog.get_logger(__name__)


class AvellanedaStoikov:
    """Avellaneda-Stoikov market making algorithm."""
    
    def __init__(self, params: MMParameters):
        """
        Initialize the algorithm.
        
        Args:
            params: Market making parameters
        """
        self.params = params
    
    def calculate_spread(
        self,
        volatility: float,
        time_remaining: float,
        order_arrival_lambda: float,
    ) -> float:
        """
        Calculate optimal spread using Avellaneda-Stoikov formula.
        
        spread = gamma * sigma^2 * t + (2/gamma) * ln(1 + gamma/kappa)
        
        Args:
            volatility: Annualized volatility (decimal, e.g., 0.5 for 50%)
            time_remaining: Time remaining until end of horizon (seconds)
            order_arrival_lambda: Expected order arrival rate per second
        
        Returns:
            Optimal spread (in base units, not bps)
        """
        gamma = self.params.gamma
        kappa = order_arrival_lambda if order_arrival_lambda > 0 else 1.0
        
        # Convert time from seconds to fraction of year
        t = time_remaining / (365 * 24 * 3600)
        
        # First term: risk cost
        risk_term = gamma * (volatility ** 2) * t
        
        # Second term: order flow term
        # ln(1 + gamma/kappa) ≈ gamma/kappa for small gamma/kappa
        if gamma / kappa < 1:
            order_term = (2 / gamma) * (gamma / kappa)
        else:
            order_term = (2 / gamma) * math.log(1 + gamma / kappa)
        
        spread = risk_term + order_term
        
        return max(spread, self.params.min_spread_bps / 10000.0)
    
    def calculate_inventory_skew(
        self,
        current_inventory: float,
        inventory_target: float,
        inventory_decay: float = 0.001,
    ) -> float:
        """
        Calculate inventory skew adjustment.
        
        Moves bid/ask spreads based on current inventory level.
        Positive inventory → move ask up, bid down (sell pressure)
        Negative inventory → move bid down, ask up (buy pressure)
        
        Args:
            current_inventory: Current inventory level (quantity)
            inventory_target: Target inventory level
            inventory_decay: Decay factor for inventory impact
        
        Returns:
            Skew adjustment (float, not bps)
        """
        inventory_diff = current_inventory - inventory_target
        skew = inventory_decay * inventory_diff
        
        return skew
    
    def quote(
        self,
        mid_price: float,
        volatility: float,
        current_inventory: float,
        time_remaining: float,
        inventory_target: float = 0.0,
    ) -> TwoSidedQuote:
        """
        Generate two-sided quote using Avellaneda-Stoikov.
        
        Args:
            mid_price: Current mid price
            volatility: Current market volatility
            current_inventory: Current inventory level
            time_remaining: Time remaining in horizon
            inventory_target: Target inventory level
        
        Returns:
            TwoSidedQuote with bid/ask prices and quantities
        """
        # Calculate spread
        spread = self.calculate_spread(
            volatility=volatility,
            time_remaining=time_remaining,
            order_arrival_lambda=self.params.order_arrival_lambda,
        )
        
        # Apply constraints
        spread_bps = spread * 10000.0
        spread_bps = max(self.params.min_spread_bps, min(spread_bps, self.params.max_spread_bps))
        spread = spread_bps / 10000.0
        
        # Calculate inventory skew
        skew = self.calculate_inventory_skew(
            current_inventory=current_inventory,
            inventory_target=inventory_target,
        )
        
        # Calculate bid and ask prices
        bid_price = mid_price - spread / 2.0 - skew * mid_price
        ask_price = mid_price + spread / 2.0 - skew * mid_price
        
        quote = TwoSidedQuote(
            symbol="",
            bid_price=bid_price,
            ask_price=ask_price,
            bid_qty=self.params.order_arrival_lambda * time_remaining,
            ask_qty=self.params.order_arrival_lambda * time_remaining,
            mid_price=mid_price,
            spread_bps=spread_bps,
            timestamp=datetime.now(timezone.utc),
        )
        
        logger.info(
            "avellaneda_stoikov_quote",
            mid_price=round(mid_price, 2),
            bid=round(bid_price, 2),
            ask=round(ask_price, 2),
            spread_bps=round(spread_bps, 2),
            inventory=current_inventory,
        )
        
        return quote
