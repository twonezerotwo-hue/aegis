"""
Spread Optimizer — Dinamik spread ayarı volatilite bazlı
"""

import structlog

logger = structlog.get_logger(__name__)


class SpreadOptimizer:
    """Volatilite ve market koşullarına göre spread optimize et."""
    
    def __init__(self, base_spread_bps: float = 1.0, vol_multiplier: float = 2.0):
        self.base_spread_bps = base_spread_bps
        self.vol_multiplier = vol_multiplier
    
    def calculate_spread(self, volatility: float, fill_rate: float = 0.15) -> float:
        """
        Volatiliteye göre spread hesapla.
        
        spread = base_spread + (vol - base_vol) * multiplier - fill_rate_adjustment
        """
        # Volatilite artışı spread'i genişletir
        vol_adjustment = max(0, (volatility - 0.02)) * self.vol_multiplier * 100
        
        # Fill rate yüksekse spread'i dar tut (daha rekabetçi)
        fill_adjustment = (fill_rate - 0.15) * 10.0
        
        spread = self.base_spread_bps + vol_adjustment - fill_adjustment
        spread = max(0.5, min(spread, 10.0))  # 0.5-10 bps arasında
        
        logger.info(
            "spread_calculated",
            spreadt=round(spread, 2),
            volatility=round(volatility, 4),
            fill_rate=round(fill_rate, 3),
        )
        
        return spread
    
    def adjust_for_market_conditions(self, spread: float, condition: str) -> float:
        """Market durumuna göre spread'i ayarla."""
        adjustments = {
            "high_vol": 1.5,           # Spread'i %50 genişlet
            "low_liquidity": 2.0,      # Spread'i 2x genişlet
            "normal": 1.0,
            "high_activity": 0.8,      # Spread'i dar tut
        }
        
        multiplier = adjustments.get(condition, 1.0)
        adjusted = spread * multiplier
        
        return max(0.5, min(adjusted, 10.0))
