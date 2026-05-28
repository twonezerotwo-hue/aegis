"""
Consensus Engine — Position Optimizer

Kelly Criterion ve Black-Litterman modeli kullanarak
optimal pozisyon boyutu hesapla.
"""
from typing import Dict, Tuple

import structlog

from .models import ConsensusConfig, AggregationResult

logger = structlog.get_logger(__name__)


class PositionOptimizer:
    """Optimal pozisyon boyutu ve risk parametreleri hesapla."""
    
    def __init__(self, config: ConsensusConfig):
        """
        Args:
            config: Consensus konfigürasyonu
        """
        self.config = config
    
    def calculate_position_size(
        self,
        aggregation_result: AggregationResult,
        fundamental_score: float = 50.0,
        win_rate: float = 0.55,
        profit_loss_ratio: float = 1.5,
    ) -> Tuple[float, float, float]:
        """
        Kelly Criterion kullanarak optimal position boyutu hesapla.
        
        F* = (P*B - Q) / B
        
        P = Win probability
        Q = Loss probability (1-P)
        B = Profit/Loss ratio
        F* = Kesir (0.25 = 25% of capital)
        
        Args:
            aggregation_result: Aggregation sonucu
            win_rate: Tarihsel kazanç oranı
            profit_loss_ratio: Kazanç/Zarar oranı
            fundamental_score: Fundamental AI skoru (0-100)
        
        Returns:
            (kelly_fraction, position_multiplier, position_size)
        """
        # Win/Loss probabilities
        p_win = win_rate / 100.0 if win_rate > 1 else win_rate
        p_loss = 1.0 - p_win
        b = profit_loss_ratio
        
        # Kelly Criterion: F = (P*B - Q) / B
        kelly_f = ((p_win * b) - p_loss) / b if b > 0 else 0.0
        kelly_f = max(0.0, min(kelly_f, 1.0))  # Clip to [0, 1]
        
        # Safety margin: Use fraction of Kelly
        safe_kelly = kelly_f * self.config.kelly_safety_margin
        
        # Fundamental multiplier hesapla
        fundamental_multiplier = self._calculate_fundamental_multiplier(fundamental_score)
        
        # Confidence from aggregation
        confidence = aggregation_result.confidence
        
        # Position size = Kelly fraction * fundamental multiplier * confidence * action strength
        # Bullish signal için +, Bearish için -
        action_strength = self._get_action_strength(aggregation_result.recommended_action)
        
        position_size = safe_kelly * fundamental_multiplier * confidence * action_strength
        position_size = max(0.0, min(position_size, self.config.max_position_size))
        
        logger.info(
            "position_size_calculated",
            symbol=aggregation_result.symbol,
            kelly_fraction=round(kelly_f, 4),
            fundamental_multiplier=round(fundamental_multiplier, 4),
            position_size=round(position_size, 4),
        )
        
        return kelly_f, fundamental_multiplier, position_size
    
    def _calculate_fundamental_multiplier(self, fundamental_score: float) -> float:
        """
        Fundamental skora göre position multiplier hesapla.
        
        Düşük (<30): 0.3x (konservatif)
        Normal (30-70): 1.0x
        Yüksek (>70): 1.2x (agresif)
        """
        if fundamental_score < self.config.fundamental_conservative:
            # Linear interpolation: 50 -> 0.3
            return 0.3 + ((fundamental_score / self.config.fundamental_conservative) * (1.0 - 0.3))
        elif fundamental_score > self.config.fundamental_bullish:
            # Linear interpolation: 70-100 -> 1.0-1.2
            ratio = (fundamental_score - self.config.fundamental_bullish) / (100.0 - self.config.fundamental_bullish)
            return 1.0 + (ratio * (self.config.fundamental_bullish_mult - 1.0))
        else:
            return 1.0
    
    def _get_action_strength(self, action: str) -> float:
        """Action tipine göre strength."""
        if action == "AL":
            return 1.0
        elif action == "SAT":
            return -1.0
        else:
            return 0.0
    
    def calculate_risk_levels(
        self,
        aggregation_result: AggregationResult,
        current_price: float,
        atr: float,
    ) -> Dict[str, float]:
        """
        Sinyal confidence'ine göre risk parametreleri hesapla.
        
        Args:
            aggregation_result: Aggregation sonucu
            current_price: Mevcut fiyat
            atr: Average True Range
        
        Returns:
            {stop_loss, take_profit, risk_level, ...}
        """
        confidence = aggregation_result.confidence
        action = aggregation_result.recommended_action
        
        # Confidence bazlı risk level
        if confidence > 0.75:
            risk_level = "HIGH"
            sl_multiplier = 2.0  # 2 ATR
            tp_multiplier = 3.0  # 3x risk/reward
        elif confidence > 0.55:
            risk_level = "MEDIUM"
            sl_multiplier = 1.5
            tp_multiplier = 2.0
        else:
            risk_level = "LOW"
            sl_multiplier = 1.0
            tp_multiplier = 1.0
        
        # Stop Loss ve Take Profit
        if action == "AL":
            stop_loss = current_price - (atr * sl_multiplier)
            take_profit = current_price + (atr * sl_multiplier * tp_multiplier)
            stop_loss_percent = ((current_price - stop_loss) / current_price) * 100.0
            take_profit_percent = ((take_profit - current_price) / current_price) * 100.0
        elif action == "SAT":
            stop_loss = current_price + (atr * sl_multiplier)
            take_profit = current_price - (atr * sl_multiplier * tp_multiplier)
            stop_loss_percent = ((stop_loss - current_price) / current_price) * 100.0
            take_profit_percent = ((current_price - take_profit) / current_price) * 100.0
        else:
            # BEKLE - risk parametreleri yok
            return {
                "stop_loss": None,
                "take_profit": None,
                "stop_loss_percent": None,
                "take_profit_target": None,
                "risk_level": "NEUTRAL",
            }
        
        return {
            "stop_loss": round(stop_loss, 2),
            "take_profit": round(take_profit, 2),
            "stop_loss_percent": round(stop_loss_percent, 2),
            "take_profit_target": round(take_profit_percent, 2),
            "risk_level": risk_level,
        }
