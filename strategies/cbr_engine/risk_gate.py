"""
AEGIS CBR Engine - FAZ 4: Risk Gate System
Macro-level risk filtering to block or reduce position sizes
"""

import numpy as np
from typing import Dict, Tuple, List
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class RiskGateResult:
    """Risk gate evaluation result"""
    should_trade: bool
    position_size_multiplier: float
    risk_score: float  # 0-1, 1=maximum risk
    blocked_by: List[str]  # Which gates blocked/reduced
    details: Dict


class MacroRiskGate:
    """
    Macro-level risk filtering system.

    Principle: Block or reduce positions when macro conditions are unfavorable,
    regardless of signal strength or similarity score.

    Gates:
    1. VIX Level - High volatility reduces position
    2. Fear/Greed - Extreme fear blocks trades
    3. DXY Correlation - Flight to dollar reduces crypto size
    4. Yield Curve - Inversion signals caution
    5. Market Drawdown - System-wide losses reduce exposure
    """

    def __init__(self):
        """Initialize risk gates with default thresholds"""
        # VIX gate
        self.vix_normal_level = 20
        self.vix_elevated_level = 30
        self.vix_extreme_level = 40

        # Fear/Greed gate
        self.fear_extreme_threshold = 15
        self.fear_moderate_threshold = 25
        self.greed_extreme_threshold = 80

        # DXY correlation gate
        self.dxy_correlation_threshold = 0.65  # Strong correlation = caution

        # Yield curve gate
        self.yield_inversion_threshold = -0.02  # 10Y - 2Y < -0.2% = inversion

        # Market drawdown gate
        self.drawdown_caution_level = 0.10  # 10% DD
        self.drawdown_severe_level = 0.20  # 20% DD

        logger.info("MacroRiskGate initialized with default thresholds")

    def evaluate_vix_gate(self, vix_level: float) -> Tuple[bool, float, str]:
        """
        Evaluate VIX level risk.

        Args:
            vix_level: Current VIX level

        Returns:
            (allow_trade, position_multiplier, reason)
        """
        if vix_level < self.vix_normal_level:
            return True, 1.0, "VIX normal"
        elif vix_level < self.vix_elevated_level:
            return True, 0.8, f"VIX elevated ({vix_level:.1f}): reduce by 20%"
        elif vix_level < self.vix_extreme_level:
            return True, 0.5, f"VIX high ({vix_level:.1f}): reduce by 50%"
        else:
            return False, 0.0, f"VIX extreme ({vix_level:.1f}): BLOCK"

    def evaluate_fear_greed_gate(self, fear_greed_index: float) -> Tuple[bool, float, str]:
        """
        Evaluate Fear/Greed index.

        Args:
            fear_greed_index: FGI level (0-100)

        Returns:
            (allow_trade, position_multiplier, reason)
        """
        if self.fear_moderate_threshold <= fear_greed_index <= (100 - self.fear_moderate_threshold):
            return True, 1.0, "FGI neutral/balanced"

        if fear_greed_index < self.fear_extreme_threshold:
            return False, 0.0, f"Extreme fear ({fear_greed_index:.0f}): BLOCK all"
        elif fear_greed_index < self.fear_moderate_threshold:
            return True, 0.6, f"Moderate fear ({fear_greed_index:.0f}): reduce by 40%"

        if fear_greed_index > self.greed_extreme_threshold:
            return True, 0.5, f"Extreme greed ({fear_greed_index:.0f}): reduce by 50%"

        return True, 1.0, "FGI normal"

    def evaluate_dxy_correlation_gate(self, dxy_correlation: float) -> Tuple[bool, float, str]:
        """
        Evaluate BTC-DXY correlation risk.

        High negative correlation = flight to crypto (low risk)
        High positive correlation = flight to dollar (high risk for crypto)

        Args:
            dxy_correlation: 14-day correlation coefficient (-1 to 1)

        Returns:
            (allow_trade, position_multiplier, reason)
        """
        # High positive correlation = bad for crypto
        if dxy_correlation > self.dxy_correlation_threshold:
            return True, 0.5, f"High DXY corr ({dxy_correlation:.2f}): flight to USD mode"

        # High negative correlation = safe
        if dxy_correlation < -self.dxy_correlation_threshold:
            return True, 1.0, f"DXY neg-corr ({dxy_correlation:.2f}): flight to crypto"

        # Neutral range
        return True, 0.85, f"DXY neutral ({dxy_correlation:.2f})"

    def evaluate_yield_curve_gate(self, yield_10y: float, yield_2y: float) -> Tuple[bool, float, str]:
        """
        Evaluate US yield curve slope.

        Inversion (10Y < 2Y) signals recession, should reduce risk.

        Args:
            yield_10y: 10-year yield
            yield_2y: 2-year yield

        Returns:
            (allow_trade, position_multiplier, reason)
        """
        slope = yield_10y - yield_2y

        if slope < 0:  # Inverted
            return True, 0.6, f"Yield curve inverted ({slope:.3f}): recession signals"
        elif slope < 0.5:  # Flat
            return True, 0.8, f"Yield curve flat ({slope:.3f}): caution"
        else:  # Normal
            return True, 1.0, f"Yield curve normal ({slope:.3f})"

    def evaluate_drawdown_gate(self, current_drawdown: float) -> Tuple[bool, float, str]:
        """
        Evaluate system-wide drawdown.

        Args:
            current_drawdown: Current system drawdown (0-1)

        Returns:
            (allow_trade, position_multiplier, reason)
        """
        if current_drawdown < self.drawdown_caution_level:
            return True, 1.0, f"Drawdown minimal ({current_drawdown:.1%})"
        elif current_drawdown < self.drawdown_severe_level:
            return True, 0.7, f"Drawdown caution ({current_drawdown:.1%}): reduce by 30%"
        else:
            return True, 0.4, f"Drawdown severe ({current_drawdown:.1%}): reduce by 60%"

    def evaluate_all_gates(self, market_state: Dict) -> RiskGateResult:
        """
        Evaluate all risk gates simultaneously.

        Args:
            market_state: Dict with macro indicators
            {
                'vix_level': float,
                'fear_greed_index': float,
                'dxy_14d_corr': float,
                'us_10y_yield': float,
                'us_2y_yield': float,
                'current_drawdown': float,
            }

        Returns:
            RiskGateResult with combined evaluation
        """
        results = {}
        multipliers = []
        blocked = []

        # VIX Gate
        allow, mult, reason = self.evaluate_vix_gate(market_state.get('vix_level', 20))
        results['vix'] = {'multiplier': mult, 'reason': reason}
        multipliers.append(mult)
        if not allow:
            blocked.append(f"VIX: {reason}")

        # Fear/Greed Gate
        allow, mult, reason = self.evaluate_fear_greed_gate(
            market_state.get('fear_greed_index', 50)
        )
        results['fear_greed'] = {'multiplier': mult, 'reason': reason}
        multipliers.append(mult)
        if not allow:
            blocked.append(f"FGI: {reason}")

        # DXY Correlation Gate
        allow, mult, reason = self.evaluate_dxy_correlation_gate(
            market_state.get('dxy_14d_corr', 0)
        )
        results['dxy_corr'] = {'multiplier': mult, 'reason': reason}
        multipliers.append(mult)

        # Yield Curve Gate (optional)
        if 'us_10y_yield' in market_state and 'us_2y_yield' in market_state:
            allow, mult, reason = self.evaluate_yield_curve_gate(
                market_state['us_10y_yield'],
                market_state['us_2y_yield']
            )
            results['yield_curve'] = {'multiplier': mult, 'reason': reason}
            multipliers.append(mult)

        # Drawdown Gate (optional)
        if 'current_drawdown' in market_state:
            allow, mult, reason = self.evaluate_drawdown_gate(
                market_state['current_drawdown']
            )
            results['drawdown'] = {'multiplier': mult, 'reason': reason}
            multipliers.append(mult)

        # Combined decision
        combined_multiplier = np.prod(multipliers) if multipliers else 1.0
        should_trade = len(blocked) == 0

        # Calculate risk score
        risk_score = 1.0 - combined_multiplier

        logger.info(
            f"Risk gate evaluation: trade={should_trade}, "
            f"multiplier={combined_multiplier:.2f}, risk={risk_score:.2f}"
        )

        return RiskGateResult(
            should_trade=should_trade,
            position_size_multiplier=combined_multiplier,
            risk_score=risk_score,
            blocked_by=blocked,
            details=results
        )


class SimilarityRiskGate:
    """
    Similarity-based risk modulation.

    Even with high similarity (>0.9), if macro conditions deteriorate,
    reduce position size accordingly.
    """

    def __init__(self):
        """Initialize"""
        self.macro_gate = MacroRiskGate()
        self.high_similarity_threshold = 0.85
        self.max_position_under_risk = 0.03  # 3% max when high risk

    def apply_similarity_risk_modulation(
        self,
        base_position_size: float,
        similarity_score: float,
        market_state: Dict
    ) -> Tuple[float, str]:
        """
        Apply macro risk modulation to position size based on similarity.

        Args:
            base_position_size: Position size before risk adjustment
            similarity_score: Similarity of matched cases (0-1)
            market_state: Current macro market state

        Returns:
            (adjusted_position_size, reason)
        """
        # Get macro risk evaluation
        risk_result = self.macro_gate.evaluate_all_gates(market_state)

        # If high similarity and good macro, allow full size
        if similarity_score > self.high_similarity_threshold and risk_result.should_trade:
            adjusted = base_position_size * risk_result.position_size_multiplier
            reason = f"High sim ({similarity_score:.2f}), macro ok: {adjusted:.4f}"
            return adjusted, reason

        # If high similarity but poor macro, cap position
        if similarity_score > self.high_similarity_threshold and not risk_result.should_trade:
            adjusted = min(base_position_size, self.max_position_under_risk)
            adjusted *= risk_result.position_size_multiplier
            reason = f"High sim but blocked: {adjusted:.4f}"
            return adjusted, reason

        # Normal case: apply macro multiplier
        adjusted = base_position_size * risk_result.position_size_multiplier
        reason = f"Sim {similarity_score:.2f}, macro mult {risk_result.position_size_multiplier:.2f}: {adjusted:.4f}"

        return adjusted, reason


class AdaptiveRiskAdjustment:
    """
    Dynamically adjust risk parameters based on recent performance.

    If strategy is underperforming, tighten risk gates.
    If strategy is outperforming, gradually loosen constraints.
    """

    def __init__(self):
        """Initialize"""
        self.window_trades = 20
        self.performance_threshold = 1.2  # Expectancy > 1.2x baseline

    def calculate_performance_factor(
        self,
        recent_returns: List[float],
        baseline_sharpe: float
    ) -> float:
        """
        Calculate performance factor for risk adjustment.

        Args:
            recent_returns: Recent trade returns
            baseline_sharpe: Expected Sharpe ratio

        Returns:
            Risk adjustment factor (0.5-1.5)
        """
        if not recent_returns or len(recent_returns) < 5:
            return 1.0

        # Calculate recent metrics
        recent_sharpe = np.mean(recent_returns) / (np.std(recent_returns) + 1e-8) * np.sqrt(252)
        win_rate = np.mean(np.array(recent_returns) > 0)

        # Compare to baseline
        if recent_sharpe > baseline_sharpe * self.performance_threshold and win_rate > 0.55:
            # Outperforming: gradually increase risk appetite
            return 1.2
        elif recent_sharpe < baseline_sharpe * 0.7 or win_rate < 0.40:
            # Underperforming: tighten risk
            return 0.6
        else:
            # Normal: keep as-is
            return 1.0

    def apply_adaptive_risk(
        self,
        base_macro_multiplier: float,
        recent_returns: List[float],
        baseline_sharpe: float = 1.4
    ) -> float:
        """
        Apply adaptive risk adjustment.

        Args:
            base_macro_multiplier: Macro gate multiplier
            recent_returns: List of recent trade returns
            baseline_sharpe: Expected Sharpe

        Returns:
            Adjusted multiplier
        """
        perf_factor = self.calculate_performance_factor(recent_returns, baseline_sharpe)
        adjusted = base_macro_multiplier * perf_factor

        return np.clip(adjusted, 0.3, 1.5)


class ComplianceRiskGate:
    """
    Hard limits for regulatory/operational compliance.

    Regardless of signals or macro conditions, enforce these hard limits:
    - Max position size
    - Max daily loss
    - Max consecutive losses
    """

    def __init__(
        self,
        max_position_size: float = 0.05,
        max_daily_loss_pct: float = -0.02,
        max_consecutive_losses: int = 5,
        daily_loss_reset_hour: int = 0  # UTC
    ):
        """
        Args:
            max_position_size: Absolute max position (0-1)
            max_daily_loss_pct: Max daily loss (-0.02 = -2%)
            max_consecutive_losses: Max consecutive losing trades
            daily_loss_reset_hour: Hour to reset daily loss tracking
        """
        self.max_position_size = max_position_size
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_consecutive_losses = max_consecutive_losses
        self.daily_loss_reset_hour = daily_loss_reset_hour

    def enforce_position_limit(self, requested_size: float) -> Tuple[float, bool]:
        """
        Enforce max position size hard limit.

        Args:
            requested_size: Requested position size

        Returns:
            (capped_size, was_capped)
        """
        if requested_size > self.max_position_size:
            return self.max_position_size, True
        return requested_size, False

    def check_daily_loss_limit(
        self,
        daily_pnl: float,
        capital: float
    ) -> Tuple[bool, str]:
        """
        Check if daily loss limit exceeded.

        Args:
            daily_pnl: Daily P&L
            capital: Total capital

        Returns:
            (allow_trading, reason)
        """
        daily_loss_pct = daily_pnl / capital

        if daily_loss_pct < self.max_daily_loss_pct:
            return False, f"Daily loss limit hit: {daily_loss_pct:.2%} < {self.max_daily_loss_pct:.2%}"

        return True, "Daily loss limit OK"

    def check_consecutive_losses(
        self,
        recent_trades: List[Dict]
    ) -> Tuple[bool, str]:
        """
        Check consecutive loss streak.

        Args:
            recent_trades: Recent trade results

        Returns:
            (allow_trading, reason)
        """
        if not recent_trades:
            return True, "No recent trades"

        # Count consecutive losses
        consecutive_losses = 0
        for trade in reversed(recent_trades):
            if trade.get('return', 0) < 0:
                consecutive_losses += 1
            else:
                break

        if consecutive_losses >= self.max_consecutive_losses:
            return False, f"Consecutive loss limit ({consecutive_losses}) reached"

        return True, f"Consecutive losses: {consecutive_losses} / {self.max_consecutive_losses}"

    def enforce_all_compliance(
        self,
        position_size: float,
        daily_pnl: float,
        capital: float,
        recent_trades: List[Dict]
    ) -> Tuple[float, bool, List[str]]:
        """
        Enforce all compliance checks.

        Args:
            position_size: Requested position size
            daily_pnl: Daily P&L
            capital: Total capital
            recent_trades: Recent trade results

        Returns:
            (capped_position, allow_trading, blocked_reasons)
        """
        blocked = []

        # Check 1: Position size
        capped_pos, was_capped = self.enforce_position_limit(position_size)
        if was_capped:
            blocked.append(f"Position capped to {capped_pos:.4f}")

        # Check 2: Daily loss
        allow_daily, daily_msg = self.check_daily_loss_limit(daily_pnl, capital)
        if not allow_daily:
            blocked.append(daily_msg)

        # Check 3: Consecutive losses
        allow_streak, streak_msg = self.check_consecutive_losses(recent_trades)
        if not allow_streak:
            blocked.append(streak_msg)

        allow_trading = len(blocked) == 0

        return capped_pos, allow_trading, blocked
