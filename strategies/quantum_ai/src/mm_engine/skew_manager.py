"""
Skew Manager — Envanter bazlı fiyat ayarlaması
"""
import structlog

logger = structlog.get_logger(__name__)


class SkewManager:
    """Envantera göre bid/ask'ı skew et (asimetrik fiyatlandırma)."""
    
    def __init__(self, skew_factor: float = 0.001, max_inventory: float = 1000.0):
        self.skew_factor = skew_factor
        self.max_inventory = max_inventory
    
    def calculate_skew(self, inventory: float, target_inventory: float = 0.0) -> float:
        """
        Envanter skew'ini hesapla.
        
        Inventory fazlası → ask'ı yukarı taşı (sat baskısı)
        Inventory hafif → bid'i yukarı taşı (al baskısı)
        """
        diff = inventory - target_inventory
        max_skew = min(abs(diff) / self.max_inventory, 1.0)
        skew = (diff / self.max_inventory) * 0.01  # Maximum 1% skew per 1000 inventory
        
        return skew
    
    def apply_skew_to_quote(self, mid_price: float, bid: float, ask: float, skew: float) -> tuple:
        """
        Bid/Ask'a skew uygula.
        
        Positive skew: ask'ı yukarı (satmaya istekli değil)
        Negative skew: bid'i aşağı (almaya istekli değil)
        """
        skew_amount = mid_price * skew
        
        adjusted_bid = bid - skew_amount
        adjusted_ask = ask - skew_amount
        
        logger.debug(
            "skew_applied",
            original_bid=round(bid, 2),
            original_ask=round(ask, 2),
            adjusted_bid=round(adjusted_bid, 2),
            adjusted_ask=round(adjusted_ask, 2),
            skew_pct=round(skew * 100, 3),
        )
        
        return adjusted_bid, adjusted_ask
