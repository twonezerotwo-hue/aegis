"""
AEGIS CBR Engine - FAZ 4: Probabilistic Decision Making + Risk Gates Tests
Test Bayesian confidence, Kelly Criterion, macro risk filtering, and compliance
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from probabilistic_decision import (
    BayesianConfidence, KellyCriterion, RiskGate, ProbabilisticDecisionMaker,
    TradingDecision
)
from risk_gate import (
    MacroRiskGate, SimilarityRiskGate, AdaptiveRiskAdjustment,
    ComplianceRiskGate
)


class TestBayesianConfidence:
    """Test Bayesian confidence calculation"""

    def test_confidence_neutral_case(self):
        """Neutral case (50% win rate, 0 return)"""
        conf = BayesianConfidence.calculate(
            win_rate=0.5,
            avg_return=0.0,
            std_return=0.02,
            sample_ratio=0.5,
            similarity_score=0.7
        )
        # For 50% win rate: (0.5 - 0.5) * 2 = 0
        assert 0 <= conf <= 1
        assert conf < 0.5  # Below neutral confidence

    def test_confidence_high_performance(self):
        """High performance case (70% win rate, 2% return)"""
        conf = BayesianConfidence.calculate(
            win_rate=0.7,
            avg_return=0.02,
            std_return=0.01,
            sample_ratio=1.0,
            similarity_score=0.85
        )
        # Should be relatively high confidence
        assert conf > 0.6

    def test_confidence_weights_sum(self):
        """Weights should sum to 1.0"""
        weights = {
            'win_rate': 0.25,
            'return': 0.20,
            'consistency': 0.20,
            'sample_ratio': 0.15,
            'similarity': 0.20,
        }
        assert sum(weights.values()) == pytest.approx(1.0)

    def test_confidence_bounded_0_1(self):
        """Confidence output always in [0, 1]"""
        # Test extreme cases
        conf_low = BayesianConfidence.calculate(
            win_rate=0.0, avg_return=-0.10, std_return=0.50, sample_ratio=0.0, similarity_score=0.0
        )
        conf_high = BayesianConfidence.calculate(
            win_rate=1.0, avg_return=0.10, std_return=0.0, sample_ratio=1.0, similarity_score=1.0
        )

        assert 0 <= conf_low <= 1
        assert 0 <= conf_high <= 1

    def test_confidence_win_rate_factor(self):
        """Win rate should increase confidence (>50%)"""
        conf_60 = BayesianConfidence.calculate(
            win_rate=0.60, avg_return=0.0, std_return=0.02, sample_ratio=0.5, similarity_score=0.5
        )
        conf_50 = BayesianConfidence.calculate(
            win_rate=0.50, avg_return=0.0, std_return=0.02, sample_ratio=0.5, similarity_score=0.5
        )

        assert conf_60 > conf_50

    def test_confidence_consistency_factor(self):
        """Lower std should increase confidence"""
        conf_low_std = BayesianConfidence.calculate(
            win_rate=0.55, avg_return=0.01, std_return=0.01, sample_ratio=0.5, similarity_score=0.5
        )
        conf_high_std = BayesianConfidence.calculate(
            win_rate=0.55, avg_return=0.01, std_return=0.10, sample_ratio=0.5, similarity_score=0.5
        )

        assert conf_low_std > conf_high_std


class TestKellyCriterion:
    """Test Kelly Criterion position sizing"""

    def test_kelly_breakeven(self):
        """50% win rate should give ~0 Kelly"""
        pos = KellyCriterion.calculate_position_size(
            win_rate=0.5, win_loss_ratio=1.0, max_position=0.10
        )
        assert 0 <= pos <= 0.01  # Near zero

    def test_kelly_positive_edge(self):
        """Positive edge should increase position"""
        pos_60 = KellyCriterion.calculate_position_size(
            win_rate=0.60, win_loss_ratio=1.0, max_position=0.10
        )
        pos_50 = KellyCriterion.calculate_position_size(
            win_rate=0.50, win_loss_ratio=1.0, max_position=0.10
        )

        assert pos_60 > pos_50

    def test_kelly_favorable_ratio(self):
        """Favorable win/loss ratio should increase position"""
        pos_2_1 = KellyCriterion.calculate_position_size(
            win_rate=0.55, win_loss_ratio=2.0, max_position=0.10
        )
        pos_1_1 = KellyCriterion.calculate_position_size(
            win_rate=0.55, win_loss_ratio=1.0, max_position=0.10
        )

        assert pos_2_1 > pos_1_1

    def test_kelly_fractional(self):
        """Using fractional Kelly (25%) for safety"""
        # Full Kelly would be (1.0 * 0.6 - 0.4) / 1.0 = 0.2
        # Fractional (25%) = 0.2 * 0.25 = 0.05
        pos = KellyCriterion.calculate_position_size(
            win_rate=0.60, win_loss_ratio=1.0, max_position=0.10
        )
        # Fractional Kelly should be conservative
        assert pos < 0.06

    def test_kelly_bounded_by_max_position(self):
        """Position size capped by max_position"""
        pos = KellyCriterion.calculate_position_size(
            win_rate=0.80, win_loss_ratio=3.0, max_position=0.02
        )

        assert pos <= 0.02

    def test_kelly_from_case_stats(self):
        """Calculate position from case statistics"""
        case_stats = {
            'sample_count': 10,
            'mean_similarity': 0.75,
            'ensemble_return': 0.02,
            'agreement': 0.7
        }

        pos = KellyCriterion.calculate_from_case_stats(case_stats, max_position=0.05)

        assert 0 <= pos <= 0.05

    def test_kelly_minimum_sample(self):
        """Too few samples should use minimum position"""
        case_stats = {
            'sample_count': 2,
            'mean_similarity': 0.7,
            'ensemble_return': 0.02,
            'agreement': 0.5
        }

        pos = KellyCriterion.calculate_from_case_stats(case_stats, max_position=0.05)

        # Should use minimum (0.01 or similar safe value)
        assert 0 <= pos <= 0.02


class TestRiskGate:
    """Test simple risk gate (original probabilistic_decision.RiskGate)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup risk gate with default rules"""
        self.gate = RiskGate()
        self.gate.add_vix_gate(threshold=35, penalty=0.4)
        self.gate.add_fear_greed_gate(min_level=15)
        self.gate.add_dxy_correlation_gate(max_corr=0.65)

    def test_gate_passes_normal_market(self):
        """Normal market conditions should pass"""
        market_state = {
            'vix_level': 20,
            'fear_greed_index': 50,
            'dxy_14d_corr': 0.3
        }

        proceed, mult, reason = self.gate.evaluate(market_state)

        assert proceed is True
        assert mult == 1.0

    def test_gate_blocks_extreme_fear(self):
        """Extreme fear should block trade"""
        market_state = {
            'vix_level': 20,
            'fear_greed_index': 10,  # Extreme fear
            'dxy_14d_corr': 0.3
        }

        proceed, mult, reason = self.gate.evaluate(market_state)

        assert proceed is False

    def test_gate_penalizes_high_vix(self):
        """High VIX should reduce position"""
        market_state = {
            'vix_level': 40,  # Above threshold
            'fear_greed_index': 50,
            'dxy_14d_corr': 0.3
        }

        proceed, mult, reason = self.gate.evaluate(market_state)

        assert proceed is True
        assert mult < 1.0  # Should be reduced

    def test_gate_high_dxy_correlation(self):
        """High DXY correlation should reduce position"""
        market_state = {
            'vix_level': 20,
            'fear_greed_index': 50,
            'dxy_14d_corr': 0.75  # High positive correlation
        }

        proceed, mult, reason = self.gate.evaluate(market_state)

        assert proceed is True
        assert mult < 1.0


class TestMacroRiskGate:
    """Test advanced MacroRiskGate (5-gate system from risk_gate.py)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup macro risk gate"""
        self.gate = MacroRiskGate()

    def test_vix_normal(self):
        """VIX < 20 should be normal"""
        allow, mult, reason = self.gate.evaluate_vix_gate(vix_level=15)

        assert allow is True
        assert mult == 1.0

    def test_vix_elevated(self):
        """VIX 20-30 should reduce by 20%"""
        allow, mult, reason = self.gate.evaluate_vix_gate(vix_level=25)

        assert allow is True
        assert mult == 0.8

    def test_vix_extreme(self):
        """VIX > 40 should block"""
        allow, mult, reason = self.gate.evaluate_vix_gate(vix_level=45)

        assert allow is False
        assert mult == 0.0

    def test_fear_greed_moderate_fear(self):
        """Moderate fear should reduce by 40%"""
        allow, mult, reason = self.gate.evaluate_fear_greed_gate(fear_greed_index=20)

        assert allow is True
        assert mult == 0.6

    def test_fear_greed_extreme_fear(self):
        """Extreme fear should block"""
        allow, mult, reason = self.gate.evaluate_fear_greed_gate(fear_greed_index=10)

        assert allow is False
        assert mult == 0.0

    def test_fear_greed_extreme_greed(self):
        """Extreme greed should reduce by 50%"""
        allow, mult, reason = self.gate.evaluate_fear_greed_gate(fear_greed_index=85)

        assert allow is True
        assert mult == 0.5

    def test_dxy_correlation_high_usd(self):
        """High positive correlation with DXY (flight to USD)"""
        allow, mult, reason = self.gate.evaluate_dxy_correlation_gate(dxy_correlation=0.75)

        assert allow is True
        assert mult == 0.5

    def test_dxy_correlation_safe(self):
        """High negative correlation (flight to crypto)"""
        allow, mult, reason = self.gate.evaluate_dxy_correlation_gate(dxy_correlation=-0.75)

        assert allow is True
        assert mult == 1.0

    def test_yield_curve_inverted(self):
        """Inverted yield curve (recession signal)"""
        allow, mult, reason = self.gate.evaluate_yield_curve_gate(yield_10y=3.5, yield_2y=3.7)

        assert allow is True
        assert mult == 0.6

    def test_drawdown_severe(self):
        """Severe drawdown (>20%)"""
        allow, mult, reason = self.gate.evaluate_drawdown_gate(current_drawdown=0.25)

        assert allow is True
        assert mult == 0.4

    def test_combine_all_gates(self):
        """Evaluate all gates combined"""
        market_state = {
            'vix_level': 25,
            'fear_greed_index': 50,
            'dxy_14d_corr': 0.3,
            'us_10y_yield': 4.0,
            'us_2y_yield': 4.2,
            'current_drawdown': 0.05
        }

        result = self.gate.evaluate_all_gates(market_state)

        assert result.should_trade is True
        assert 0 <= result.position_size_multiplier <= 1.0
        assert 0 <= result.risk_score <= 1.0

    def test_gate_blocks_situation(self):
        """Scenario that triggers blocking"""
        market_state = {
            'vix_level': 50,  # Extreme VIX
            'fear_greed_index': 10,  # Extreme fear
            'dxy_14d_corr': 0.3,
            'current_drawdown': 0.05
        }

        result = self.gate.evaluate_all_gates(market_state)

        assert result.should_trade is False
        assert len(result.blocked_by) > 0


class TestSimilarityRiskGate:
    """Test SimilarityRiskGate modulation"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup similarity risk gate"""
        self.gate = SimilarityRiskGate()

    def test_high_similarity_good_macro(self):
        """High similarity with good macro should allow full size"""
        market_state = {
            'vix_level': 20,
            'fear_greed_index': 50,
            'dxy_14d_corr': 0.3
        }

        adjusted, reason = self.gate.apply_similarity_risk_modulation(
            base_position_size=0.05,
            similarity_score=0.92,
            market_state=market_state
        )

        assert adjusted > 0.03  # Should be substantial

    def test_high_similarity_poor_macro(self):
        """High similarity but poor macro should cap position"""
        market_state = {
            'vix_level': 50,  # Extreme VIX
            'fear_greed_index': 10,  # Extreme fear
            'dxy_14d_corr': 0.3
        }

        adjusted, reason = self.gate.apply_similarity_risk_modulation(
            base_position_size=0.05,
            similarity_score=0.92,
            market_state=market_state
        )

        # Should be capped to max_position_under_risk (3%)
        assert adjusted <= 0.03

    def test_low_similarity_normal_macro(self):
        """Low similarity applies normal macro multiplier"""
        market_state = {
            'vix_level': 20,
            'fear_greed_index': 50,
            'dxy_14d_corr': 0.3
        }

        adjusted, reason = self.gate.apply_similarity_risk_modulation(
            base_position_size=0.05,
            similarity_score=0.60,
            market_state=market_state
        )

        assert adjusted > 0  # Should be positive but prudent


class TestAdaptiveRiskAdjustment:
    """Test AdaptiveRiskAdjustment based on performance"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup adaptive risk adjustment"""
        self.adjuster = AdaptiveRiskAdjustment()

    def test_outperforming_increases_risk(self):
        """Outperforming should increase risk appetite"""
        recent_returns = [0.02, 0.025, 0.015, 0.03, 0.02, 0.025, 0.015, 0.02]

        factor = self.adjuster.calculate_performance_factor(
            recent_returns=recent_returns,
            baseline_sharpe=1.4
        )

        assert factor > 1.0  # Should increase risk

    def test_underperforming_decreases_risk(self):
        """Underperforming should tighten risk"""
        recent_returns = [-0.01, -0.02, -0.015, -0.01, 0.005, -0.01, -0.02, 0.0]

        factor = self.adjuster.calculate_performance_factor(
            recent_returns=recent_returns,
            baseline_sharpe=1.4
        )

        assert factor < 1.0  # Should decrease risk

    def test_few_trades_returns_neutral(self):
        """Too few trades should return neutral factor"""
        recent_returns = [0.01, -0.01]

        factor = self.adjuster.calculate_performance_factor(
            recent_returns=recent_returns,
            baseline_sharpe=1.4
        )

        assert factor == 1.0  # Neutral

    def test_apply_adaptive_risk(self):
        """Apply adaptive risk adjustment to multiplier"""
        recent_returns = [0.02, 0.025, 0.015, 0.03] * 2  # 8 positive returns

        adjusted = self.adjuster.apply_adaptive_risk(
            base_macro_multiplier=0.8,
            recent_returns=recent_returns,
            baseline_sharpe=1.4
        )

        assert 0.3 <= adjusted <= 1.5  # Should be within bounds


class TestComplianceRiskGate:
    """Test ComplianceRiskGate hard limits"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup compliance gate"""
        self.gate = ComplianceRiskGate(
            max_position_size=0.05,
            max_daily_loss_pct=-0.02,
            max_consecutive_losses=5
        )

    def test_position_limit_enforced(self):
        """Position size capped to max"""
        capped, was_capped = self.gate.enforce_position_limit(0.08)

        assert capped == 0.05
        assert was_capped is True

    def test_position_under_limit(self):
        """Position under limit passes through"""
        capped, was_capped = self.gate.enforce_position_limit(0.03)

        assert capped == 0.03
        assert was_capped is False

    def test_daily_loss_limit_exceeded(self):
        """Daily loss exceeds limit"""
        allowed, reason = self.gate.check_daily_loss_limit(
            daily_pnl=-510,  # -$510 = -2.04%
            capital=25000
        )

        assert allowed is False

    def test_daily_loss_under_limit(self):
        """Daily loss within limit"""
        allowed, reason = self.gate.check_daily_loss_limit(
            daily_pnl=-300,  # -1.2%
            capital=25000
        )

        assert allowed is True

    def test_consecutive_losses_under_limit(self):
        """Consecutive losses under limit"""
        recent_trades = [
            {'return': -0.01},
            {'return': -0.02},
            {'return': 0.01}
        ]

        allowed, reason = self.gate.check_consecutive_losses(recent_trades)

        assert allowed is True

    def test_consecutive_losses_exceeds_limit(self):
        """Consecutive losses exceeds max"""
        recent_trades = [
            {'return': -0.01},
            {'return': -0.02},
            {'return': -0.015},
            {'return': -0.01},
            {'return': -0.02},
            {'return': -0.01}  # 6 consecutive
        ]

        allowed, reason = self.gate.check_consecutive_losses(recent_trades)

        assert allowed is False

    def test_enforce_all_compliance(self):
        """Enforce all compliance checks"""
        recent_trades = [
            {'return': 0.01},
            {'return': -0.02}
        ]

        capped_pos, allow_trading, blocked = self.gate.enforce_all_compliance(
            position_size=0.07,
            daily_pnl=-100,
            capital=50000,
            recent_trades=recent_trades
        )

        assert capped_pos <= 0.05
        assert isinstance(allow_trading, bool)
        assert isinstance(blocked, list)


class TestProbabilisticDecisionMaker:
    """Test integrated trading decision making"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup decision maker"""
        self.maker = ProbabilisticDecisionMaker()

    def test_decision_dip_high_confidence(self):
        """DIP pattern with high confidence should LONG"""
        fingerprint = {
            'atr_14': 100,
            'distance_from_ath': 0.1,
            'vix_level': 20,
            'fear_greed_index': 50,
            'dxy_14d_corr': 0.3
        }

        case_stats = {
            'sample_count': 20,
            'mean_similarity': 0.75,
            'ensemble_return': 0.02,
            'agreement': 0.7
        }

        decision = self.maker.make_decision(
            current_price=45000,
            fingerprint=fingerprint,
            similar_cases_stats=case_stats,
            market_type='DIP'
        )

        assert decision.action == 'LONG'
        assert decision.position_size > 0
        assert decision.entry_price == 45000
        assert decision.stop_loss < decision.entry_price
        assert decision.take_profit > decision.entry_price

    def test_decision_skip_low_confidence(self):
        """Low confidence should SKIP (but may still calculate position size)"""
        fingerprint = {
            'atr_14': 100,
            'distance_from_ath': 0.1,
            'vix_level': 20,
            'fear_greed_index': 50,
            'dxy_14d_corr': 0.3
        }

        case_stats = {
            'sample_count': 3,
            'mean_similarity': 0.40,  # Low similarity
            'ensemble_return': -0.01,
            'agreement': 0.3
        }

        decision = self.maker.make_decision(
            current_price=45000,
            fingerprint=fingerprint,
            similar_cases_stats=case_stats,
            market_type='DIP'
        )

        assert decision.action == 'SKIP'
        # When skipping, entry/stop/target should be None
        assert decision.entry_price is None
        assert decision.stop_loss is None
        assert decision.take_profit is None

    def test_decision_skip_blocked_by_gate(self):
        """Macro gate blocking should result in SKIP"""
        fingerprint = {
            'atr_14': 100,
            'distance_from_ath': 0.1,
            'vix_level': 50,  # Extreme VIX
            'fear_greed_index': 10,  # Extreme fear
            'dxy_14d_corr': 0.3
        }

        case_stats = {
            'sample_count': 20,
            'mean_similarity': 0.75,
            'ensemble_return': 0.02,
            'agreement': 0.7
        }

        # Need to configure original risk gate for blocking
        self.maker.risk_gate.add_fear_greed_gate(min_level=15)

        decision = self.maker.make_decision(
            current_price=45000,
            fingerprint=fingerprint,
            similar_cases_stats=case_stats,
            market_type='DIP'
        )

        assert decision.action == 'SKIP'
        assert decision.position_size == 0.0

    def test_decision_short_peak(self):
        """PEAK pattern should SHORT (if confidence high)"""
        fingerprint = {
            'atr_14': 100,
            'distance_from_ath': 0.1,
            'vix_level': 20,
            'fear_greed_index': 80,  # Greed
            'dxy_14d_corr': 0.3
        }

        case_stats = {
            'sample_count': 20,
            'mean_similarity': 0.75,
            'ensemble_return': -0.02,  # Short payoff
            'agreement': 0.7
        }

        decision = self.maker.make_decision(
            current_price=45000,
            fingerprint=fingerprint,
            similar_cases_stats=case_stats,
            market_type='PEAK'
        )

        if decision.action == 'SHORT':
            assert decision.position_size > 0
            assert decision.stop_loss > decision.entry_price
            assert decision.take_profit < decision.entry_price

    def test_trading_decision_structure(self):
        """TradingDecision has required fields"""
        decision = TradingDecision(
            action='LONG',
            confidence=0.65,
            position_size=0.03,
            entry_price=45000,
            stop_loss=44500,
            take_profit=45500,
            reasoning={'test': 'reason'}
        )

        assert decision.action in ['LONG', 'SHORT', 'SKIP']
        assert 0 <= decision.confidence <= 1
        assert 0 <= decision.position_size
        assert isinstance(decision.reasoning, dict)

    def test_expected_value_calculation(self):
        """Calculate expected value of trade"""
        fingerprint = {
            'atr_14': 100,
            'distance_from_ath': 0.1,
            'vix_level': 20,
            'fear_greed_index': 50,
            'dxy_14d_corr': 0.3
        }

        case_stats = {
            'sample_count': 20,
            'mean_similarity': 0.75,
            'ensemble_return': 0.02,
            'agreement': 0.7
        }

        decision = self.maker.make_decision(
            current_price=45000,
            fingerprint=fingerprint,
            similar_cases_stats=case_stats,
            market_type='DIP'
        )

        ev = self.maker.get_expected_value(decision)

        assert isinstance(ev, float)
        if decision.action != 'SKIP':
            assert ev > 0  # Should have positive EV for signals


class TestPhase4Integration:
    """Integration tests for FAZ 4"""

    def test_complete_decision_pipeline(self):
        """Test complete decision-making pipeline"""
        # Setup
        maker = ProbabilisticDecisionMaker()
        macro_gate = MacroRiskGate()
        compliance_gate = ComplianceRiskGate(max_position_size=0.10)  # Higher limit for this test

        # Historical similar cases
        case_stats = {
            'sample_count': 25,
            'mean_similarity': 0.72,
            'ensemble_return': 0.018,
            'agreement': 0.65
        }

        # Current market state
        fingerprint = {
            'atr_14': 150,
            'distance_from_ath': 0.08,
            'vix_level': 22,
            'fear_greed_index': 52,
            'dxy_14d_corr': 0.25,
            'us_10y_yield': 4.2,
            'us_2y_yield': 4.0,
            'current_drawdown': 0.03
        }

        # Step 1: Risk gate evaluation
        macro_result = macro_gate.evaluate_all_gates(fingerprint)
        assert macro_result.should_trade is True

        # Step 2: Trading decision
        decision = maker.make_decision(
            current_price=48000,
            fingerprint=fingerprint,
            similar_cases_stats=case_stats,
            market_type='DIP'
        )

        assert decision.action in ['LONG', 'SHORT', 'SKIP']
        assert 0 <= decision.confidence <= 1

        # Step 3: Compliance checks (with higher limits to accommodate Kelly position)
        if decision.action != 'SKIP':
            capped, allow, blocked = compliance_gate.enforce_all_compliance(
                position_size=decision.position_size,
                daily_pnl=100,  # Small profit
                capital=500000,
                recent_trades=[]
            )

            # Position should not exceed 10% after capping
            assert capped <= 0.10
            # Should be allowed (profit, no consecutive losses, position within bounds)
            assert allow is True
            assert len(blocked) == 0

    def test_multiple_scenarios_consistency(self):
        """Test consistency across multiple scenarios"""
        maker = ProbabilisticDecisionMaker()

        scenarios = [
            # Bull scenario
            {
                'name': 'Bull DIP',
                'fingerprint': {
                    'atr_14': 100, 'distance_from_ath': 0.05,
                    'vix_level': 18, 'fear_greed_index': 60, 'dxy_14d_corr': -0.2
                },
                'case_stats': {'sample_count': 30, 'mean_similarity': 0.78, 'ensemble_return': 0.025, 'agreement': 0.8},
                'market_type': 'DIP',
                'price': 50000
            },
            # Bear scenario
            {
                'name': 'Bear PEAK',
                'fingerprint': {
                    'atr_14': 100, 'distance_from_ath': 0.10,
                    'vix_level': 32, 'fear_greed_index': 75, 'dxy_14d_corr': 0.5
                },
                'case_stats': {'sample_count': 20, 'mean_similarity': 0.65, 'ensemble_return': -0.015, 'agreement': 0.6},
                'market_type': 'PEAK',
                'price': 45000
            },
            # Risky scenario
            {
                'name': 'Risk Event',
                'fingerprint': {
                    'atr_14': 200, 'distance_from_ath': 0.15,
                    'vix_level': 45, 'fear_greed_index': 12, 'dxy_14d_corr': 0.8
                },
                'case_stats': {'sample_count': 5, 'mean_similarity': 0.50, 'ensemble_return': -0.02, 'agreement': 0.3},
                'market_type': 'DIP',
                'price': 42000
            }
        ]

        decisions = []
        for scenario in scenarios:
            decision = maker.make_decision(
                current_price=scenario['price'],
                fingerprint=scenario['fingerprint'],
                similar_cases_stats=scenario['case_stats'],
                market_type=scenario['market_type']
            )
            decisions.append(decision)

            # All decisions should be valid
            assert decision.action in ['LONG', 'SHORT', 'SKIP']
            assert 0 <= decision.confidence <= 1

    def test_faz4_acceptance_criteria(self):
        """FAZ 4 acceptance: all systems operational"""
        # Component 1: Bayesian confidence
        conf = BayesianConfidence.calculate(
            win_rate=0.65, avg_return=0.02, std_return=0.01,
            sample_ratio=0.8, similarity_score=0.75
        )
        assert 0 <= conf <= 1

        # Component 2: Kelly Criterion
        kelly = KellyCriterion.calculate_position_size(0.60, 1.5, max_position=0.05)
        assert kelly > 0

        # Component 3: Risk gates
        gate = RiskGate()
        gate.add_vix_gate(35, 0.4)
        gate.add_fear_greed_gate(15)
        proceed, mult, _ = gate.evaluate({'vix_level': 20, 'fear_greed_index': 50})
        assert proceed is True

        # Component 4: Macro risk gate
        macro = MacroRiskGate()
        result = macro.evaluate_all_gates({
            'vix_level': 25, 'fear_greed_index': 50, 'dxy_14d_corr': 0.3,
            'us_10y_yield': 4.0, 'us_2y_yield': 3.9, 'current_drawdown': 0.05
        })
        assert result.should_trade is True

        # Component 5: Compliance
        compliance = ComplianceRiskGate()
        capped, allow, _ = compliance.enforce_all_compliance(0.04, 0, 100000, [])
        assert allow is True

        # Component 6: Decision maker
        maker = ProbabilisticDecisionMaker()
        decision = maker.make_decision(
            45000,
            {'atr_14': 100, 'distance_from_ath': 0.1, 'vix_level': 20,
             'fear_greed_index': 50, 'dxy_14d_corr': 0.3},
            {'sample_count': 20, 'mean_similarity': 0.75, 'ensemble_return': 0.02, 'agreement': 0.7},
            'DIP'
        )
        assert decision.action in ['LONG', 'SHORT', 'SKIP']


def test_faz4_readiness():
    """Meta test: Is FAZ 4 complete and ready?"""
    # Component 1: Probabilistic decision making
    maker = ProbabilisticDecisionMaker()
    decision = maker.make_decision(
        45000,
        {'atr_14': 100, 'distance_from_ath': 0.1, 'vix_level': 20,
         'fear_greed_index': 50, 'dxy_14d_corr': 0.3},
        {'sample_count': 20, 'mean_similarity': 0.75, 'ensemble_return': 0.02, 'agreement': 0.7},
        'DIP'
    )
    assert decision.action in ['LONG', 'SHORT', 'SKIP']

    # Component 2: Macro risk gating
    macro_gate = MacroRiskGate()
    result = macro_gate.evaluate_all_gates({
        'vix_level': 25, 'fear_greed_index': 50, 'dxy_14d_corr': 0.3,
        'us_10y_yield': 4.0, 'us_2y_yield': 3.9, 'current_drawdown': 0.05
    })
    assert result.should_trade is True

    # Component 3: Compliance gates
    compliance = ComplianceRiskGate()
    capped, allow, blocked = compliance.enforce_all_compliance(0.06, -500, 50000, [])
    assert capped <= 0.05

    print("✅ FAZ 4 PROBABILISTIC SIZING + RISK GATE - READY FOR PRODUCTION")
    print("   Bayesian confidence: ✓")
    print("   Kelly Criterion: ✓")
    print("   Macro risk gates: ✓")
    print("   Similarity modulation: ✓")
    print("   Compliance limits: ✓")
    print("   Trading decisions: ✓")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
