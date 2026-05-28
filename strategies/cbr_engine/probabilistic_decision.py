"""
AEGIS CBR Engine - Probabilistic Decision Making & Risk Gates
Position sizing with Bayesian confidence and macro risk filtering
"""

import numpy as np
from typing import Dict, Tuple, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class TradingDecision:
    """Generated trading decision"""
    action: str  # LONG, SHORT, SKIP
    confidence: float  # 0.0-1.0
    position_size: float  # Kelly-optimized
    entry_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    reasoning: Dict


class BayesianConfidence:
    """Calculate Bayesian confidence from similar case statistics"""

    @staticmethod
    def calculate(
        win_rate: float,
        avg_return: float,
        std_return: float,
        sample_ratio: float,
        similarity_score: float
    ) -> float:
        """
        Bayesian confidence = weighted combination of factors

        Args:
            win_rate: % of similar cases that won (0-1)
            avg_return: Average return of similar cases
            std_return: Std deviation of returns
            sample_ratio: How many similar cases found (0-1)
            similarity_score: Avg similarity of cases (0-1)

        Returns:
            Confidence score (0-1)
        """
        factors = {
            'win_rate': (win_rate - 0.5) * 2 if win_rate > 0.5 else 0,  # Normalize around 50%
            'return': np.clip(avg_return / 0.02, 0, 1),  # 2% return = max confidence
            'consistency': 1 - np.clip(std_return / 0.05, 0, 1),  # Low std = good
            'sample_ratio': np.clip(sample_ratio, 0, 1),
            'similarity': similarity_score,
        }

        # Weighted combination
        weights = {
            'win_rate': 0.25,
            'return': 0.20,
            'consistency': 0.20,
            'sample_ratio': 0.15,
            'similarity': 0.20,
        }

        confidence = sum(factors[k] * weights[k] for k in factors)
        return np.clip(confidence, 0, 1)


class RiskGate:
    """
    Macro risk filtering - blocks trades when macro conditions are unfavorable.

    Example gating rules:
    - If VIX > 40: reduce position size by 50%
    - If fear_greed < 20: skip trade
    - If correlation to DXY > 0.7: skip (hedge-seeking market)
    """

    def __init__(self):
        """Initialize risk gate with default rules"""
        self.rules = {}

    def add_vix_gate(self, threshold: float = 40, penalty: float = 0.5):
        """Gate based on VIX level"""
        self.rules['vix'] = {'threshold': threshold, 'penalty': penalty}

    def add_fear_greed_gate(self, min_level: float = 20):
        """Skip trade if fear_greed below threshold"""
        self.rules['fear_greed'] = {'min_level': min_level}

    def add_dxy_correlation_gate(self, max_corr: float = 0.6):
        """Skip trade if too correlated with DXY (hedge-seeking)"""
        self.rules['dxy_corr'] = {'max_corr': max_corr}

    def evaluate(self, market_state: Dict) -> Tuple[bool, float, str]:
        """
        Evaluate if trade should proceed.

        Args:
            market_state: Dict with macro indicators (vix_level, fear_greed, dxy_14d_corr, etc.)

        Returns:
            (should_proceed, position_size_multiplier, reason)
        """
        multiplier = 1.0
        reasons = []

        # VIX gate
        if 'vix' in self.rules and 'vix_level' in market_state:
            vix = market_state['vix_level']
            threshold = self.rules['vix']['threshold']
            penalty = self.rules['vix']['penalty']

            if vix > threshold:
                multiplier *= (1 - penalty)
                reasons.append(f"High VIX ({vix:.1f} > {threshold}): size *= {1-penalty:.2f}")

        # Fear/Greed gate
        if 'fear_greed' in self.rules and 'fear_greed_index' in market_state:
            fg = market_state['fear_greed_index']
            min_level = self.rules['fear_greed']['min_level']

            if fg < min_level:
                return (False, 0.0, f"Extreme fear ({fg:.0f} < {min_level}): SKIP")

        # DXY correlation gate- if BTC too correlated with DXY, market is in "safe mode"
        if 'dxy_corr' in self.rules and 'dxy_14d_corr' in market_state:
            corr = market_state['dxy_14d_corr']
            max_corr = self.rules['dxy_corr']['max_corr']

            if corr < -max_corr or corr > max_corr:  # High correlation magnitude
                multiplier *= 0.6
                reasons.append(f"High DXY correlation ({corr:.2f}): size *= 0.6")

        reason = " | ".join(reasons) if reasons else "All risk gates passed"

        return (True, multiplier, reason)


class KellyCriterion:
    """
    Kelly Criterion for position sizing.

    f* = (bp - q) / b

    Where:
    - b: win/loss ratio (avg_win / avg_loss)
    - p: win probability
    - q: loss probability (1 - p)
    """

    @staticmethod
    def calculate_position_size(
        win_rate: float,
        win_loss_ratio: float,
        max_position: float = 0.05
    ) -> float:
        """
        Calculate Kelly-optimized position size.

        Args:
            win_rate: Probability of win (0-1)
            win_loss_ratio: Average win / average loss
            max_position: Maximum position size (default 5% of capital)

        Returns:
            Position size as fraction of capital (0-1)
        """
        if win_rate == 0 or win_rate == 1:
            return 0.0

        # Kelly formula
        p = win_rate
        q = 1 - win_rate
        b = win_loss_ratio

        if b <= 0:
            return 0.0

        kelly = (b * p - q) / b

        # Fractional Kelly (use 25% of Kelly for safety)
        fractional_kelly = kelly * 0.25

        # Clamp to reasonable range
        position_size = np.clip(fractional_kelly, 0, max_position)

        return float(position_size)

    @staticmethod
    def calculate_from_case_stats(
        similar_cases_stats: Dict,
        max_position: float = 0.05
    ) -> float:
        """
        Calculate position size from case statistics.

        Args:
            similar_cases_stats: Dict from SimilarityEngine.ensemble_similar_cases()
            max_position: Max allowed position

        Returns:
            Recommended position size
        """
        sample_count = similar_cases_stats.get('sample_count', 0)
        if sample_count < 3:
            return 0.01  # Minimum size if too few samples

        # Estimate win_rate from mean similarity
        win_rate = np.clip(similar_cases_stats.get('mean_similarity', 0.5), 0.4, 0.8)

        # Estimate win/loss ratio from returns
        ensemble_return = similar_cases_stats.get('ensemble_return', 0.0)
        agreement = similar_cases_stats.get('agreement', 0.5)

        win_loss_ratio = max(1.5, 1 + abs(ensemble_return) / 0.01)  # Dynamic ratio

        position = KellyCriterion.calculate_position_size(
            win_rate, win_loss_ratio, max_position
        )

        return position


class ProbabilisticDecisionMaker:
    """
    End-to-end trading decision making.

    Takes:
    1. Current fingerprint
    2. Similar historical cases
    3. Macro risk indicators

    Outputs:
    - Trade signal (LONG/SHORT/SKIP)
    - Position size (Kelly-optimized)
    - Risk management (stops/targets)
    """

    def __init__(self):
        """Initialize decision maker"""
        self.confidence_calculator = BayesianConfidence()
        self.risk_gate = RiskGate()

        # Configure default risk gates
        self.risk_gate.add_vix_gate(threshold=35, penalty=0.4)
        self.risk_gate.add_fear_greed_gate(min_level=15)
        self.risk_gate.add_dxy_correlation_gate(max_corr=0.65)

    def make_decision(
        self,
        current_price: float,
        fingerprint: Dict,
        similar_cases_stats: Dict,
        market_type: str = 'DIP'  # DIP, PEAK, BREAKOUT, REJECTION
    ) -> TradingDecision:
        """
        Generate complete trading decision.

        Args:
            current_price: Current BTC price
            fingerprint: Current market fingerprint
            similar_cases_stats: Statistics from similar cases
            market_type: Detected market pattern

        Returns:
            TradingDecision with position size and risk management
        """
        # Step 1: Bayesian confidence
        confidence = self.confidence_calculator.calculate(
            win_rate=np.clip(similar_cases_stats.get('mean_similarity', 0.5), 0.3, 0.8),
            avg_return=similar_cases_stats.get('ensemble_return', 0.0),
            std_return=0.01,  # Placeholder
            sample_ratio=np.clip(similar_cases_stats.get('sample_count', 0) / 20, 0, 1),
            similarity_score=similar_cases_stats.get('mean_similarity', 0.5)
        )

        # Step 2: Risk gates
        gate_ok, size_multiplier, gate_reason = self.risk_gate.evaluate(fingerprint)

        if not gate_ok:
            return TradingDecision(
                action='SKIP',
                confidence=0.0,
                position_size=0.0,
                entry_price=None,
                stop_loss=None,
                take_profit=None,
                reasoning={
                    'reason': gate_reason,
                    'macro_gate_failed': True
                }
            )

        # Step 3: Position sizing
        if market_type == 'DIP' and confidence > 0.55:
            action = 'LONG'
            base_position = 0.05  # 5% base
        elif market_type == 'PEAK' and confidence > 0.55:
            action = 'SHORT'
            base_position = 0.03  # 3% base (more conservative)
        else:
            action = 'SKIP'
            base_position = 0.0

        # Apply Kelly criterion
        kelly_position = KellyCriterion.calculate_from_case_stats(
            similar_cases_stats, max_position=0.1
        )

        # Final position = Kelly * base * macro risk multiplier
        position_size = kelly_position * size_multiplier

        # Step 4: Risk management (stops & targets)
        atr = fingerprint.get('atr_14', 100)
        vol = fingerprint.get('distance_from_ath', 0.1) * current_price

        if action == 'LONG':
            entry_price = current_price
            stop_loss = entry_price - (atr * 2)  # 2x ATR below
            take_profit = entry_price + (atr * 4)  # 4x ATR above (1:2 RR)
        elif action == 'SHORT':
            entry_price = current_price
            stop_loss = entry_price + (atr * 2)
            take_profit = entry_price - (atr * 4)
        else:
            entry_price = None
            stop_loss = None
            take_profit = None

        reasoning = {
            'market_type': market_type,
            'confidence_score': float(confidence),
            'macro_risk_multiplier': float(size_multiplier),
            'gate_reason': gate_reason,
            'kelly_position': float(kelly_position),
            'sample_count': similar_cases_stats.get('sample_count', 0),
            'mean_similarity': float(similar_cases_stats.get('mean_similarity', 0.0)),
        }

        return TradingDecision(
            action=action,
            confidence=confidence * size_multiplier,  # Adjust confidence by macro risk
            position_size=position_size,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reasoning=reasoning
        )

    def get_expected_value(self, decision: TradingDecision) -> float:
        """Calculate expected value of trade"""
        if decision.action == 'SKIP':
            return 0.0

        avg_return = decision.reasoning.get('mean_similarity', 0.5) * 0.02  # Assume 2% per unit
        ev = avg_return * decision.position_size * decision.confidence

        return float(ev)
