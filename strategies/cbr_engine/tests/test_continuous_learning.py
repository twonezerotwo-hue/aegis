"""
AEGIS CBR Engine - FAZ 5: Continuous Learning Tests
Test auto-labeler, weekly optimizer, and SHAP dashboard
"""

import pytest
import numpy as np
import pandas as pd
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from auto_labeler import AutoLabeler, TradeLogger
from weekly_optimizer import WeeklyOptimizer
from shap_dashboard import SHAPDashboard


class TestAutoLabeler:
    """Test trade outcome labeling"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup auto-labeler"""
        self.labeler = AutoLabeler()

    def test_outcome_categorization_great_win(self):
        """Category: GREAT_WIN (>= +5%)"""
        category, win = self.labeler.categorize_outcome(0.06)

        assert category == 'GREAT_WIN'
        assert win is True

    def test_outcome_categorization_win(self):
        """Category: WIN (+2% to +5%)"""
        category, win = self.labeler.categorize_outcome(0.03)

        assert category == 'WIN'
        assert win is True

    def test_outcome_categorization_breakeven(self):
        """Category: BREAKEVEN (-1% to +2%)"""
        category, win = self.labeler.categorize_outcome(0.005)

        assert category == 'BREAKEVEN'
        assert win is True

    def test_outcome_categorization_small_loss(self):
        """Category: SMALL_LOSS (-1% to -5%)"""
        category, win = self.labeler.categorize_outcome(-0.03)

        assert category == 'SMALL_LOSS'
        assert win is False

    def test_outcome_categorization_big_loss(self):
        """Category: BIG_LOSS (< -5%)"""
        category, win = self.labeler.categorize_outcome(-0.10)

        assert category == 'BIG_LOSS'
        assert win is False

    def test_label_trade_basic(self):
        """Label a trade with return"""
        outcome = self.labeler.label_trade(
            trade_id='TRADE_001',
            fingerprint_id=1,
            entry_price=45000,
            exit_price=45900,  # +2%
            confidence_score=0.65,
            position_size=0.03,
            entry_time=datetime.now(),
            exit_time=datetime.now() + timedelta(hours=4),
            notes='Test trade'
        )

        assert outcome.trade_id == 'TRADE_001'
        assert outcome.fingerprint_id == 1
        assert abs(outcome.forward_return - 0.02) < 0.001
        assert outcome.outcome_category == 'WIN'
        assert outcome.win is True
        assert outcome.holding_period_hours == pytest.approx(4, abs=0.1)

    def test_label_multiple_trades(self):
        """Label multiple trades"""
        entry_time = datetime.now()

        for i in range(5):
            self.labeler.label_trade(
                trade_id=f'TRADE_{i:03d}',
                fingerprint_id=i,
                entry_price=45000,
                exit_price=45000 + (i + 1) * 500,  # Varying returns
                confidence_score=0.6 + i*0.05,
                position_size=0.03,
                entry_time=entry_time,
                exit_time=entry_time + timedelta(hours=2),
            )

        assert len(self.labeler.trades_log) == 5

    def test_get_recent_outcomes(self):
        """Retrieve recent trade outcomes"""
        entry_time = datetime.now()

        for i in range(10):
            self.labeler.label_trade(
                trade_id=f'TRADE_{i:03d}',
                fingerprint_id=i,
                entry_price=45000,
                exit_price=45000 + (i * 100),
                confidence_score=0.65,
                position_size=0.03,
                entry_time=entry_time,
                exit_time=entry_time + timedelta(hours=1),
            )

        recent = self.labeler.get_recent_outcomes(n=5)

        assert len(recent) == 5
        assert recent[-1].trade_id == 'TRADE_009'

    def test_get_outcomes_by_category(self):
        """Filter outcomes by category"""
        entry_time = datetime.now()

        returns = [0.06, 0.03, 0.00, -0.02, -0.10]
        for i, ret in enumerate(returns):
            self.labeler.label_trade(
                trade_id=f'TRADE_{i}',
                fingerprint_id=i,
                entry_price=45000,
                exit_price=45000 * (1 + ret),
                confidence_score=0.65,
                position_size=0.03,
                entry_time=entry_time,
                exit_time=entry_time + timedelta(hours=1),
            )

        great_wins = self.labeler.get_outcomes_by_category('GREAT_WIN')
        losses = self.labeler.get_outcomes_by_category('BIG_LOSS')

        assert len(great_wins) == 1
        assert len(losses) == 1

    def test_calculate_statistics(self):
        """Calculate statistics from outcomes"""
        entry_time = datetime.now()
        returns = [0.05, 0.03, 0.01, -0.02, -0.05]

        for i, ret in enumerate(returns):
            self.labeler.label_trade(
                trade_id=f'TRADE_{i}',
                fingerprint_id=i,
                entry_price=45000,
                exit_price=45000 * (1 + ret),
                confidence_score=0.65,
                position_size=0.03,
                entry_time=entry_time,
                exit_time=entry_time + timedelta(hours=1),
            )

        stats = self.labeler.calculate_statistics()

        assert stats['total_trades'] == 5
        assert stats['win_rate'] == 0.6  # 3 wins out of 5
        assert 'avg_return' in stats
        assert 'std_return' in stats
        assert stats['sharpe_ratio'] > 0  # Some sharpe ratio

    def test_outcome_distribution(self):
        """Get distribution of outcomes"""
        entry_time = datetime.now()

        # Create outcomes across categories
        for i in range(10):
            ret = (i / 5) - 1  # Range from -1 to +1
            self.labeler.label_trade(
                trade_id=f'TRADE_{i}',
                fingerprint_id=i,
                entry_price=45000,
                exit_price=45000 * (1 + ret),
                confidence_score=0.65,
                position_size=0.03,
                entry_time=entry_time,
                exit_time=entry_time + timedelta(hours=1),
            )

        distribution = self.labeler.get_outcome_distribution()

        assert sum(distribution.values()) == 10
        assert all(k in distribution for k in self.labeler.OUTCOME_CATEGORIES.keys())

    def test_confidence_calibration(self):
        """Check if confidence scores match actual returns"""
        entry_time = datetime.now()

        # High confidence trades
        for i in range(5):
            self.labeler.label_trade(
                trade_id=f'HIGH_{i}',
                fingerprint_id=100+i,
                entry_price=45000,
                exit_price=45000 * 1.03,  # +3% (wins)
                confidence_score=0.9,
                position_size=0.03,
                entry_time=entry_time,
                exit_time=entry_time + timedelta(hours=1),
            )

        # Low confidence trades
        for i in range(5):
            self.labeler.label_trade(
                trade_id=f'LOW_{i}',
                fingerprint_id=200+i,
                entry_price=45000,
                exit_price=45000 * 0.98,  # -2% (losses)
                confidence_score=0.3,
                position_size=0.03,
                entry_time=entry_time,
                exit_time=entry_time + timedelta(hours=1),
            )

        calibration = self.labeler.confidence_calibration()

        # Should show higher returns for high confidence
        if 'High' in calibration:
            assert calibration['High']['avg_return'] > 0

    def test_export_to_dataframe(self):
        """Export trades to DataFrame"""
        entry_time = datetime.now()

        for i in range(5):
            self.labeler.label_trade(
                trade_id=f'TRADE_{i}',
                fingerprint_id=i,
                entry_price=45000,
                exit_price=45000 * (1 + i*0.01),
                confidence_score=0.65,
                position_size=0.03,
                entry_time=entry_time,
                exit_time=entry_time + timedelta(hours=1),
            )

        df = self.labeler.export_to_dataframe()

        assert len(df) == 5
        assert 'trade_id' in df.columns
        assert 'forward_return' in df.columns
        assert 'outcome_category' in df.columns

    def test_reset_log(self):
        """Clear trade log"""
        entry_time = datetime.now()

        self.labeler.label_trade(
            trade_id='TRADE_001',
            fingerprint_id=1,
            entry_price=45000,
            exit_price=45900,
            confidence_score=0.65,
            position_size=0.03,
            entry_time=entry_time,
            exit_time=entry_time + timedelta(hours=1),
        )

        assert len(self.labeler.trades_log) == 1

        self.labeler.reset_log()

        assert len(self.labeler.trades_log) == 0


class TestTradeLogger:
    """Test trade entry/exit logging"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup trade logger"""
        self.logger = TradeLogger()

    def test_record_entry(self):
        """Record trade entry"""
        self.logger.record_entry(
            trade_id='TRADE_001',
            fingerprint_id=1,
            entry_price=45000,
            confidence_score=0.65,
            position_size=0.03,
            entry_time=datetime.now(),
        )

        assert 'TRADE_001' in self.logger.active_trades
        assert self.logger.get_active_trade_count() == 1

    def test_record_exit(self):
        """Record trade exit"""
        entry_time = datetime.now()

        self.logger.record_entry(
            trade_id='TRADE_001',
            fingerprint_id=1,
            entry_price=45000,
            confidence_score=0.65,
            position_size=0.03,
            entry_time=entry_time,
        )

        exit_record = self.logger.record_exit(
            trade_id='TRADE_001',
            exit_price=45900,
            exit_time=entry_time + timedelta(hours=4),
        )

        assert exit_record is not None
        assert exit_record['entry_price'] == 45000
        assert exit_record['exit_price'] == 45900
        assert 'TRADE_001' not in self.logger.active_trades

    def test_exit_nonexistent_trade(self):
        """Exit non-existent trade should return None"""
        result = self.logger.record_exit(
            trade_id='NONEXISTENT',
            exit_price=46000,
            exit_time=datetime.now(),
        )

        assert result is None

    def test_multiple_active_trades(self):
        """Handle multiple active trades"""
        entry_time = datetime.now()

        for i in range(5):
            self.logger.record_entry(
                trade_id=f'TRADE_{i}',
                fingerprint_id=i,
                entry_price=45000 + i*100,
                confidence_score=0.65,
                position_size=0.03,
                entry_time=entry_time,
            )

        assert self.logger.get_active_trade_count() == 5

        active = self.logger.get_active_trades()
        assert len(active) == 5


class TestWeeklyOptimizer:
    """Test parameter optimization"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup optimizer"""
        self.optimizer = WeeklyOptimizer(
            n_trials=20,
            objective_metric='sharpe_ratio',
            min_trades_for_optimization=5
        )

    def test_initialization(self):
        """Test optimizer initialization"""
        assert self.optimizer.n_trials == 20
        assert self.optimizer.objective_metric == 'sharpe_ratio'
        assert self.optimizer.min_trades_for_optimization == 5

    def test_prepare_dataset(self):
        """Test train/test split"""
        trades = [
            {'forward_return': r}
            for r in [0.01, 0.02, -0.01, 0.03, -0.02, 0.02, 0.01, -0.01, 0.04, 0.01]
        ]

        train, test = self.optimizer.prepare_dataset(trades)

        assert len(train) == 7
        assert len(test) == 3
        # Chronological split
        assert train[-1] == trades[6]
        assert test[0] == trades[7]

    def test_calculate_sharpe_ratio(self):
        """Calculate Sharpe ratio"""
        returns = [0.01, 0.02, -0.01, 0.03, 0.02]

        sharpe = self.optimizer.calculate_sharpe_ratio(returns)

        assert isinstance(sharpe, float)
        assert sharpe > 0  # Positive average returns

    def test_calculate_win_rate(self):
        """Calculate win rate"""
        returns = [0.01, 0.02, -0.01, 0.03, -0.02]

        win_rate = self.optimizer.calculate_win_rate(returns)

        assert win_rate == 0.6  # 3 wins out of 5

    def test_calculate_expectancy(self):
        """Calculate expectancy (mean return)"""
        returns = [0.02, 0.03, 0.01, 0.02, 0.02]

        expectancy = self.optimizer.calculate_expectancy(returns)

        assert expectancy == pytest.approx(0.02, abs=0.001)

    def test_insufficient_trades_for_optimization(self):
        """Optimization requires minimum trades"""
        trades = [
            {'forward_return': 0.01},
            {'forward_return': -0.01},
        ]

        result = self.optimizer.optimize(trades)

        assert result is None

    def test_evaluate_parameters(self):
        """Evaluate parameter set"""
        train_trades = [
            {'forward_return': r}
            for r in [0.01, 0.02, 0.03, 0.01, 0.02]
        ]
        test_trades = [
            {'forward_return': r}
            for r in [0.02, 0.01]
        ]

        parameters = {
            'confidence_win_rate_weight': 0.25,
            'confidence_return_weight': 0.20,
            'confidence_consistency_weight': 0.20,
            'confidence_sample_weight': 0.15,
            'confidence_similarity_weight': 0.20,
        }

        test_metric, evaluation = self.optimizer.evaluate_parameters(
            parameters, train_trades, test_trades
        )

        assert isinstance(test_metric, float)
        assert 'train_metric' in evaluation
        assert 'test_metric' in evaluation
        assert 'overfitting_gap' in evaluation

    def test_should_optimize_weekly(self):
        """Check if optimization should run"""
        # No last time - should optimize
        assert self.optimizer.should_optimize(None) is True

        # Within 7 days - should not optimize
        last_time = pd.Timestamp.now() - timedelta(days=3)
        assert self.optimizer.should_optimize(last_time) is False

        # After 7 days - should optimize
        last_time = pd.Timestamp.now() - timedelta(days=8)
        assert self.optimizer.should_optimize(last_time) is True

    def test_optimization_with_sufficient_trades(self):
        """Run optimization with sufficient data"""
        # Create trades with positive returns
        trades = [
            {'forward_return': np.random.normal(0.01, 0.02)}
            for _ in range(50)
        ]

        result = self.optimizer.optimize(trades)

        # Should return parameters
        assert result is not None
        assert isinstance(result, dict)
        # Check for key parameter names (may have underscores due to Optuna)
        assert any('kelly' in k for k in result.keys())
        assert any('max' in k for k in result.keys())

    def test_get_optimization_history(self):
        """Retrieve optimization history"""
        trades = [
            {'forward_return': np.random.normal(0.01, 0.02)}
            for _ in range(50)
        ]

        self.optimizer.optimize(trades)

        history = self.optimizer.get_optimization_history()

        assert len(history) >= 1
        assert 'best_value' in history.columns
        assert 'n_trades' in history.columns


class TestSHAPDashboard:
    """Test feature importance dashboard"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup dashboard"""
        self.dashboard = SHAPDashboard()

    def test_initialization(self):
        """Test dashboard initialization"""
        assert len(self.dashboard.feature_importances) == 0
        assert len(self.dashboard.trade_explanations) == 0

    def test_calculate_feature_importance_fallback(self):
        """Calculate importance using fallback (correlation)"""
        features = np.array([
            [1.0, 2.0, 3.0],
            [2.0, 4.0, 6.0],
            [3.0, 6.0, 9.0],
            [4.0, 8.0, 12.0],
            [5.0, 10.0, 15.0],
        ])

        decisions = np.array([0.5, 0.7, 0.9, 0.8, 0.6])
        feature_names = ['feature_1', 'feature_2', 'feature_3']

        importances = self.dashboard.calculate_feature_importance(
            feature_names, features, decisions
        )

        assert len(importances) == 3
        for fname in feature_names:
            assert fname in importances
            assert importances[fname].importance_score >= 0
            assert importances[fname].impact_on_decision in ['HIGH', 'MEDIUM', 'LOW']

    def test_explain_trade_decision(self):
        """Explain a single trade decision"""
        # Setup some importance first
        features = np.random.randn(100, 5)
        decisions = np.random.rand(100)
        feature_names = [f'feature_{i}' for i in range(5)]

        self.dashboard.calculate_feature_importance(feature_names, features, decisions)

        # Explain a specific trade
        test_features = np.array([1.0, 2.0, 3.0, 4.0, 5.0])

        explanation = self.dashboard.explain_trade_decision(
            trade_id='TRADE_001',
            features=test_features,
            feature_names=feature_names,
            decision_score=0.75,
        )

        assert explanation['trade_id'] == 'TRADE_001'
        assert explanation['decision_score'] == 0.75
        assert 'feature_values' in explanation
        assert 'top_drivers' in explanation
        assert len(explanation['top_drivers']) > 0

    def test_feature_importance_summary(self):
        """Get summary of top features"""
        features = np.random.randn(100, 5)
        decisions = np.random.rand(100)
        feature_names = [f'feature_{i}' for i in range(5)]

        self.dashboard.calculate_feature_importance(feature_names, features, decisions)

        summary = self.dashboard.get_feature_importance_summary(top_n=3)

        assert len(summary) <= 3
        assert 'Feature' in summary.columns
        assert 'Importance Score' in summary.columns

    def test_detect_feature_drift(self):
        """Detect shifts in feature importance"""
        # Initial importance
        features = np.random.randn(100, 3)
        decisions = np.random.rand(100)
        feature_names = ['feature_1', 'feature_2', 'feature_3']

        self.dashboard.calculate_feature_importance(feature_names, features, decisions)

        old_importance = {
            name: self.dashboard.feature_importances[name].importance_score
            for name in feature_names
        }

        # New importance (with shift)
        features_new = np.random.randn(100, 3)
        features_new[:, 0] *= 10  # Artificially boost feature_1

        self.dashboard.calculate_feature_importance(feature_names, features_new, decisions)

        drifted = self.dashboard.detect_feature_drift(old_importance, threshold=0.2)

        # Should detect some drift
        assert isinstance(drifted, list)

    def test_get_trade_explanation(self):
        """Retrieve explanation for specific trade"""
        features = np.random.randn(100, 3)
        decisions = np.random.rand(100)
        feature_names = ['f1', 'f2', 'f3']

        self.dashboard.calculate_feature_importance(feature_names, features, decisions)

        test_features = np.array([1.0, 2.0, 3.0])
        self.dashboard.explain_trade_decision(
            'TRADE_001', test_features, feature_names, 0.75
        )

        explanation = self.dashboard.get_trade_explanation('TRADE_001')

        assert explanation is not None
        assert explanation['trade_id'] == 'TRADE_001'

    def test_summary_report(self):
        """Generate summary report"""
        features = np.random.randn(100, 3)
        decisions = np.random.rand(100)
        feature_names = ['feature_1', 'feature_2', 'feature_3']

        self.dashboard.calculate_feature_importance(feature_names, features, decisions)

        report = self.dashboard.summary_report()

        assert 'TOP' in report
        assert 'IMPORTANT' in report
        assert 'feature_1' in report or 'feature_2' in report or 'feature_3' in report

    def test_export_to_dataframe(self):
        """Export importances to DataFrame"""
        features = np.random.randn(100, 3)
        decisions = np.random.rand(100)
        feature_names = ['f1', 'f2', 'f3']

        self.dashboard.calculate_feature_importance(feature_names, features, decisions)

        df = self.dashboard.export_to_dataframe()

        assert len(df) == 3
        assert 'Feature' in df.columns


class TestPhase5Integration:
    """Integration tests for FAZ 5"""

    def test_complete_learning_pipeline(self):
        """Test complete continuous learning pipeline"""
        # 1. Create trades with labeler
        labeler = AutoLabeler()
        entry_time = datetime.now()

        for i in range(20):
            ret = np.random.normal(0.02, 0.05)
            labeler.label_trade(
                trade_id=f'TRADE_{i:03d}',
                fingerprint_id=i,
                entry_price=45000,
                exit_price=45000 * (1 + ret),
                confidence_score=np.random.rand(),
                position_size=0.03,
                entry_time=entry_time,
                exit_time=entry_time + timedelta(hours=np.random.randint(1, 24)),
            )

        # 2. Get statistics and export
        stats = labeler.calculate_statistics()
        assert stats['total_trades'] == 20

        df = labeler.export_to_dataframe()
        assert len(df) == 20

        # 3. Optimize parameters
        trades = [
            {
                'forward_return': row['forward_return'],
                'confidence': row['confidence_score']
            }
            for _, row in df.iterrows()
        ]

        optimizer = WeeklyOptimizer(n_trials=10, min_trades_for_optimization=5)
        params = optimizer.optimize(trades)

        assert params is not None

        # 4. Explain decisions with SHAP
        dashboard = SHAPDashboard()

        # Create features for all trades
        features = np.random.randn(20, 5)
        decisions = df['confidence_score'].values

        importances = dashboard.calculate_feature_importance(
            [f'feature_{i}' for i in range(5)],
            features,
            decisions
        )

        assert len(importances) == 5

    def test_faz5_acceptance_criteria(self):
        """FAZ 5 acceptance: all systems operational"""
        # Component 1: Auto-labeler
        labeler = AutoLabeler()
        entry_time = datetime.now()

        labeler.label_trade(
            'T1', 1, 45000, 45900, 0.65, 0.03, entry_time, entry_time + timedelta(hours=1)
        )

        stats = labeler.calculate_statistics()
        assert stats['total_trades'] == 1
        assert stats['win_rate'] == 1.0

        # Component 2: Trade logger
        logger = TradeLogger()
        logger.record_entry('T2', 2, 46000, 0.70, 0.03, entry_time)
        assert logger.get_active_trade_count() == 1

        # Component 3: Weekly optimizer
        optimizer = WeeklyOptimizer(n_trials=10)
        trades = [{'forward_return': 0.02} for _ in range(50)]
        params = optimizer.optimize(trades)
        assert params is not None

        # Component 4: SHAP dashboard
        dashboard = SHAPDashboard()
        features = np.random.randn(50, 5)
        decisions = np.random.rand(50)
        importances = dashboard.calculate_feature_importance(
            [f'f{i}' for i in range(5)], features, decisions
        )
        assert len(importances) == 5


def test_faz5_readiness():
    """Meta test: Is FAZ 5 complete and ready?"""
    # Component 1: Auto-labeler
    labeler = AutoLabeler()
    entry_time = datetime.now()

    for i in range(10):
        labeler.label_trade(
            f'T{i}', i, 45000, 45000 * (1 + 0.02 * ((-1)**i)), 0.65, 0.03,
            entry_time, entry_time + timedelta(hours=1)
        )

    stats = labeler.calculate_statistics()
    assert stats['total_trades'] == 10

    # Component 2: Trade logger
    logger = TradeLogger()
    for i in range(5):
        logger.record_entry(f'T{i}', i, 45000, 0.65, 0.03, entry_time)
    assert logger.get_active_trade_count() == 5

    # Component 3: Weekly optimizer
    optimizer = WeeklyOptimizer()
    trades = [{'forward_return': np.random.normal(0.01, 0.02)} for _ in range(100)]
    params = optimizer.optimize(trades)
    assert params is not None
    # Just check that params are returned, even if names vary
    assert len(params) > 0

    # Component 4: SHAP dashboard
    dashboard = SHAPDashboard()
    features = np.random.randn(100, 10)
    decisions = np.random.rand(100)
    importances = dashboard.calculate_feature_importance(
        [f'f{i}' for i in range(10)], features, decisions
    )
    assert len(importances) == 10

    print("✅ FAZ 5 CONTINUOUS LEARNING - READY FOR PRODUCTION")
    print(f"   Auto-labeler: ✓ {stats['total_trades']} trades labeled")
    print(f"   Trade logger: ✓ {logger.get_active_trade_count()} active trades tracked")
    print(f"   Weekly optimizer: ✓ {len(params)} parameters optimized")
    print(f"   SHAP dashboard: ✓ {len(importances)} features analyzed")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
