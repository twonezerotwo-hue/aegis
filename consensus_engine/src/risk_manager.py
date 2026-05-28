"""
Consensus Engine — Risk Manager

Global risk kontrolü ve portfolio-level kısıtlamalar.
"""
from typing import Dict, List, Optional, Tuple

import structlog

from .models import (
    RiskMetrics,
    ConsensusDecision,
    PortfolioPosition,
    ConsensusConfig,
)

logger = structlog.get_logger(__name__)


class RiskManager:
    """Portfolio-level risk management."""
    
    def __init__(self, config: ConsensusConfig):
        """
        Args:
            config: Consensus konfigürasyonu
        """
        self.config = config
    
    def validate_position(
        self,
        decision: Optional[ConsensusDecision],
        current_positions: Dict[str, PortfolioPosition],
        risk_metrics: RiskMetrics,
        risk_limits: Dict[str, float],
    ) -> Tuple[bool, str]:
        """
        Yeni pozisyonun global risk limitlerine uygunluğunu kontrol et.

        Args:
            decision: Consensus kararı (None olabilir)
            current_positions: Mevcut pozisyonlar
            risk_metrics: Risk metrikleri
            risk_limits: Risk limitleri

        Returns:
            (is_valid, reason)
        """
        # Handle None decision
        if decision is None:
            return True, "No decision to validate"

        symbol = decision.symbol
        proposed_size = decision.position_size
        
        # Check 1: Single position max size
        if proposed_size > risk_limits.get("max_single_position", 0.15):
            return False, f"Position size {proposed_size:.2%} exceeds max {risk_limits.get('max_single_position', 0.15):.2%}"
        
        # Check 2: Leverage testi
        new_exposure = risk_metrics.total_exposure + (proposed_size * risk_metrics.portfolio_value)
        new_leverage = new_exposure / risk_metrics.portfolio_value
        
        if new_leverage > risk_limits.get("max_leverage", 2.0):
            return False, f"New leverage {new_leverage:.2f}x exceeds max {risk_limits.get('max_leverage', 2.0):.2f}x"
        
        # Check 3: Total concentration
        if proposed_size > risk_limits.get("max_concentration", 0.20):
            return False, "Total concentration would exceed limit"
        
        # Check 4: Correlation check (basit)
        existing_bullish = sum(
            p.position_size for s, p in current_positions.items() 
            if s != symbol
        )
        
        if decision.action == "AL" and existing_bullish + proposed_size > risk_limits.get("max_concentration", 0.20):
            return False, "Too many bullish positions"
        
        return True, "OK"

    def apply_sentinel_risk_gate(
        self,
        decision: Optional[ConsensusDecision],
        vix: float,
        dxy: float,
        fear_greed: float,
        multiplier_engine,  # Sentinel AI's MultiplierEngine
    ) -> Tuple[Optional[ConsensusDecision], Dict]:
        """
        COMPONENT 4: Apply Sentinel AI risk gatekeeper filters to consensus decision.

        Sentinel filters are POST-SIGNAL only:
        - Calculate risk multiplier from macro indicators
        - Apply filters to position_size only
        - Return modified decision

        Args:
            decision: Consensus decision with initial position_size (can be None)
            vix, dxy, fear_greed: Macro indicators
            multiplier_engine: Sentinel AI's multiplier_engine instance

        Returns:
            (filtered_decision, filter_details)
        """
        if decision is None:
            return None, {}

        # Apply gatekeeper filters to position size
        original_size = decision.position_size
        filtered_size, filters = multiplier_engine.apply_risk_gatekeeper_filters(
            position_size=original_size,
            vix=vix,
            dxy=dxy,
            fear_greed=fear_greed,
        )

        # Create modified decision
        metadata = decision.metadata.copy() if hasattr(decision, 'metadata') and decision.metadata else {}
        metadata.update({
            "sentinel_filters_applied": True,
            "original_position_size": original_size,
            "filter_breakdown": filters,
        })

        filtered_decision = decision.copy(
            update={"position_size": filtered_size, "metadata": metadata}
        ) if hasattr(decision, 'copy') else decision

        logger.info(
            "sentinel_risk_gate_applied",
            original_size=round(original_size, 4),
            filtered_size=round(filtered_size, 4),
            reduction_pct=round((1.0 - filtered_size/original_size)*100, 1) if original_size > 0 else 0.0,
        )

        return filtered_decision, filters

    def calculate_portfolio_metrics(
        self,
        positions: Dict[str, PortfolioPosition],
        portfolio_value: float,
        cash_reserve: float,
    ) -> RiskMetrics:
        """
        Portfolio risk metrikleri hesapla.
        
        Args:
            positions: Mevcut pozisyonlar
            portfolio_value: Portfolio toplam değeri
            cash_reserve: Nakit rezerv
        
        Returns:
            RiskMetrics
        """
        total_exposure = sum(p.position_size * portfolio_value for p in positions.values())
        max_single = max([p.position_size for p in positions.values()], default=0.0)
        
        # Simple volatility estimate
        unrealized_pnls = [p.unrealized_pnl_percent for p in positions.values()]
        volatility = self._calculate_volatility(unrealized_pnls)
        
        # Drawdown hesapla (basit)
        if unrealized_pnls:
            max_drawdown = min(unrealized_pnls) if unrealized_pnls else 0.0
        else:
            max_drawdown = 0.0
        
        # Sharpe ratio (simplified)
        if volatility > 0:
            sharpe = (0.02 - volatility) / volatility  # Assuming 2% risk-free rate
        else:
            sharpe = 0.0
        
        metrics = RiskMetrics(
            portfolio_value=portfolio_value,
            cash_reserve=cash_reserve,
            total_exposure=total_exposure,
            max_single_position=max_single,
            portfolio_volatility=volatility,
            sharpe_ratio=sharpe,
            max_drawdown=max_drawdown,
            correlation_with_benchmark=0.0,  # TODO: Implement
        )
        
        logger.info(
            "portfolio_metrics_calculated",
            leverage=round(metrics.leverage, 2),
            volatility=round(volatility, 4),
            max_drawdown=round(max_drawdown, 4),
        )
        
        return metrics
    
    def should_rebalance(
        self,
        risk_metrics: RiskMetrics,
        rebalance_thresholds: Dict[str, float],
    ) -> bool:
        """Portfolio rebalance gerekli mi?"""
        # High drawdown → rebalance
        if abs(risk_metrics.max_drawdown) > rebalance_thresholds.get("drawdown_threshold", 0.10):
            return True
        
        # High leverage → rebalance
        if risk_metrics.leverage > rebalance_thresholds.get("leverage_threshold", 1.8):
            return True
        
        # High volatility → rebalance
        if risk_metrics.portfolio_volatility > rebalance_thresholds.get("volatility_threshold", 0.05):
            return True
        
        return False
    
    def _calculate_volatility(self, returns: List[float]) -> float:
        """Basit volatilite hesapla."""
        if not returns or len(returns) < 2:
            return 0.0
        
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        
        return variance ** 0.5
