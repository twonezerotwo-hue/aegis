"""
Consensus Engine — Final Allocator

Nihai emir kararını ve position allocations'ı belirle.
"""
from typing import Dict, List

import structlog

from .models import (
    ConsensusDecision,
    AggregationResult,
    PortfolioPosition,
)

logger = structlog.get_logger(__name__)


class FinalAllocator:
    """Nihai position allocation ve trade order kararları."""
    
    @staticmethod
    def create_consensus_decision(
        aggregation_result: AggregationResult,
        position_size: float,
        fundamental_multiplier: float,
        kelly_fraction: float,
        stop_loss: float,
        take_profit: float,
        stop_loss_percent: float,
        take_profit_target: float,
        risk_level: str,
    ) -> ConsensusDecision:
        """
        Nihai consensus kararı oluştur.
        
        Args:
            aggregation_result: Aggregation sonucu
            position_size: Hesaplanan position boyutu
            fundamental_multiplier: Fundamental multiplier
            kelly_fraction: Kelly fraction
            stop_loss: Stop loss fiyatı
            take_profit: Take profit fiyatı
            stop_loss_percent: SL %
            take_profit_target: TP hedefi
            risk_level: Risk seviyesi
        
        Returns:
            ConsensusDecision
        """
        decision = ConsensusDecision(
            symbol=aggregation_result.symbol,
            action=aggregation_result.recommended_action,
            confidence=aggregation_result.confidence,
            position_size=position_size,
            touche_signal=aggregation_result.touche_signal,
            fundamental_signal=aggregation_result.fundamental_signal,
            fundamental_multiplier=fundamental_multiplier,
            position_multiplier=position_size,
            kelly_fraction=kelly_fraction,
            alignment_score=aggregation_result.alignment_degree,
            contradiction_score=1.0 - aggregation_result.alignment_degree,
            aggregate_score=aggregation_result.confidence,
            risk_level=risk_level,
            stop_loss_percent=stop_loss_percent,
            take_profit_target=take_profit_target,
            reasoning=FinalAllocator._create_reasoning(
                aggregation_result,
                position_size,
                fundamental_multiplier,
                risk_level,
            ),
            metadata={
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "kelly_fraction": kelly_fraction,
            },
        )
        
        logger.info(
            "consensus_decision_created",
            symbol=decision.symbol,
            action=decision.action,
            position_size=round(position_size, 4),
            confidence=round(decision.confidence, 3),
        )
        
        return decision
    
    @staticmethod
    def _create_reasoning(
        aggregation_result: AggregationResult,
        position_size: float,
        fundamental_multiplier: float,
        risk_level: str,
    ) -> str:
        """Nihai karar açıklaması."""
        parts = [
            f"Touche {aggregation_result.touche_signal.signal}: EQS={aggregation_result.touche_signal.eqs:.0f}",
            f"Fundamental {aggregation_result.fundamental_signal.signal}: Score={aggregation_result.fundamental_signal.score:.0f}",
            f"Uyum: {aggregation_result.alignment_degree:.1%}",
            f"Position: {position_size:.1%}",
            f"Risk: {risk_level}",
            f"Fundamental multiplier: {fundamental_multiplier:.2f}x",
        ]
        
        if aggregation_result.confidence > 0.75:
            parts.append("Status: GUCLÜ SINYAL")
        elif aggregation_result.confidence > 0.55:
            parts.append("Status: ORTA SINYAL")
        else:
            parts.append("Status: ZAYIF SINYAL")
        
        return " | ".join(parts)
    
    @staticmethod
    def allocate_positions(
        consensus_decisions: List[ConsensusDecision],
        total_capital: float,
    ) -> Dict[str, PortfolioPosition]:
        """
        Consensus kararlarından portfolio allocations oluştur.
        
        Args:
            consensus_decisions: Consensus kararları
            total_capital: Toplam sermaye
        
        Returns:
            {symbol: PortfolioPosition}
        """
        positions = {}
        
        for decision in consensus_decisions:
            if decision.action == "BEKLE":
                continue
            
            # Position boyutu hesapla
            allocation_amount = decision.position_size * total_capital
            
            # Entry price = current price (simplified)
            # In real implementation, get current market price
            entry_price = 100.0  # Placeholder
            
            quantity = allocation_amount / entry_price
            
            position = PortfolioPosition(
                symbol=decision.symbol,
                quantity=quantity,
                entry_price=entry_price,
                current_price=entry_price,
                stop_loss=decision.metadata.get("stop_loss", entry_price),
                take_profit=decision.metadata.get("take_profit", entry_price),
                position_size=decision.position_size,
                confidence=decision.confidence,
            )
            
            positions[decision.symbol] = position
            
            logger.info(
                "position_allocated",
                symbol=decision.symbol,
                quantity=round(quantity, 4),
                allocation_amount=round(allocation_amount, 2),
            )
        
        return positions
