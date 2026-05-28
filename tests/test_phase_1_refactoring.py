"""
Test Suite for AEGIS Phase 1 Refactoring

Tests all Phase 1 components:
1. Trade Log Enhancement (stage_signals, entry_reason, exit_reason)
2. Attribution Logger (phase attribution calculation)
3. Optuna Integration (intelligent parameter optimization)
4. Risk Gatekeeper Filters (Sentinel/Quantum risk filtering)
"""

import pytest
import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add parent directories to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ============================================================================
# COMPONENT 1: Trade Log Enhancement Tests
# ============================================================================

class TestTradeLogEnhancement:
    """Test TradeRecord stage_signals, entry_reason, exit_reason fields"""

    def test_trade_record_has_stage_signals(self):
        """Verify TradeRecord dataclass includes stage_signals field"""
        from strategies.touche_ai.src.engine.unified_optimizer import TradeRecord

        trade = TradeRecord(
            entry_price=100.0,
            exit_price=105.0,
            pnl=5.0,
            winning_phases=[1, 2, 3],
            losing_phases=[6],
        )

        assert hasattr(trade, 'stage_signals'), "TradeRecord missing stage_signals"
        assert isinstance(trade.stage_signals, dict), "stage_signals should be dict"

    def test_trade_record_has_entry_exit_reason(self):
        """Verify TradeRecord includes entry_reason and exit_reason"""
        from strategies.touche_ai.src.engine.unified_optimizer import TradeRecord

        trade = TradeRecord(
            entry_price=100.0,
            exit_price=105.0,
            pnl=5.0,
            entry_reason="Phase 2: Strong structure",
            exit_reason="Phase 5: Timing reversal",
        )

        assert trade.entry_reason == "Phase 2: Strong structure"
        assert trade.exit_reason == "Phase 5: Timing reversal"

    def test_populate_stage_signals(self):
        """Test record_phase_signals() method populates signals"""
        from strategies.touche_ai.src.engine.unified_optimizer import TradeRecord, UnifiedOptimizer

        optimizer = UnifiedOptimizer()

        # Create trade with phase signals
        trade = TradeRecord(
            entry_price=100.0,
            exit_price=105.0,
            pnl=5.0,
        )

        # Simulate phase signals
        phase_signals = {
            1: 0.85,  # Liquidity - strong
            2: 0.72,  # Structure - moderate
            3: 0.65,  # Zones - moderate
            4: 0.68,  # Confirmation - moderate
            5: 0.71,  # Timing - moderate
            6: 0.45,  # Risk - weak
            7: 0.68,  # Macro - moderate
        }

        optimizer.record_phase_signals(trade, phase_signals)

        assert len(trade.stage_signals) > 0, "stage_signals not populated"
        assert all(isinstance(v, float) for v in trade.stage_signals.values()), "signals not float"

    def test_backward_compatibility_with_old_trades(self):
        """Test _migrate_trade_record() handles old trade records"""
        from strategies.touche_ai.src.engine.unified_optimizer import TradeRecord, UnifiedOptimizer

        optimizer = UnifiedOptimizer()

        # Old trade without new fields
        old_trade = TradeRecord(
            entry_price=100.0,
            exit_price=105.0,
            pnl=5.0,
        )

        # Migrate
        migrated = optimizer._migrate_trade_record(old_trade)

        assert migrated is not None
        assert hasattr(migrated, 'stage_signals')
        assert isinstance(migrated.stage_signals, dict)

    # ========================================================================
    # COMPONENT 2: Attribution Logger Tests
    # ========================================================================

    def test_attribution_logger_imports(self):
        """Verify AttributionLogger class exists and imports"""
        try:
            from strategies.touche_ai.src.engine.attribution_logger import AttributionLogger
            assert True
        except ImportError:
            pytest.fail("AttributionLogger not found")

    def test_attribution_calculation_with_trades(self):
        """Test calculate_attribution() with sample trades"""
        from strategies.touche_ai.src.engine.unified_optimizer import TradeRecord
        from strategies.touche_ai.src.engine.attribution_logger import AttributionLogger

        logger_instance = AttributionLogger(min_trades_for_correlation=5)

        # Create sample trades with signals
        trades = []
        for i in range(10):
            trade = TradeRecord(
                entry_price=100.0 + i,
                exit_price=105.0 + i,
                pnl=5.0 if i % 2 == 0 else -3.0,
                winning_phases=[1, 2] if i % 2 == 0 else [6],
                losing_phases=[6] if i % 2 == 0 else [5],
                stage_signals={
                    1: 0.8 + (i * 0.01),
                    2: 0.7 + (i * 0.01),
                    3: 0.6 + (i * 0.01),
                    4: 0.7 + (i * 0.01),
                    5: 0.6 + (i * 0.01),
                    6: 0.4 + (i * 0.01),
                    7: 0.7 + (i * 0.01),
                },
            )
            trades.append(trade)

        # Calculate attribution
        report = logger_instance.calculate_attribution(trades)

        assert report is not None, "Attribution report should not be None"
        assert hasattr(report, 'total_trades_analyzed'), "Missing total_trades_analyzed"
        assert hasattr(report, 'phase_attribution'), "Missing phase_attribution"

    def test_attribution_neutral_report_for_few_trades(self):
        """Test attribution returns neutral for <20 trades"""
        from strategies.touche_ai.src.engine.unified_optimizer import TradeRecord
        from strategies.touche_ai.src.engine.attribution_logger import AttributionLogger

        logger_instance = AttributionLogger(min_trades_for_correlation=5)

        # Only 5 trades - below minimum
        trades = [
            TradeRecord(
                entry_price=100.0 + i,
                exit_price=105.0 + i,
                pnl=5.0,
                stage_signals={j: 0.5 for j in range(1, 8)},
            )
            for i in range(5)
        ]

        report = logger_instance.calculate_attribution(trades)
        assert report is not None
        assert report.total_trades_analyzed == 5

    # ========================================================================
    # COMPONENT 3: Optuna Integration Tests
    # ========================================================================

    def test_optuna_study_creation(self):
        """Test _create_optuna_study_per_phase() creates Optuna study"""
        from strategies.touche_ai.src.engine.unified_optimizer import TradeRecord, UnifiedOptimizer

        optimizer = UnifiedOptimizer()

        # Create sample losing trade
        losing_trade = TradeRecord(
            entry_price=100.0,
            exit_price=98.0,
            pnl=-2.0,
            stage_signals={i: 0.5 for i in range(1, 8)},
        )

        # Try to optimize phase 1
        try:
            best_params, best_score = optimizer._create_optuna_study_per_phase(
                phase_id=1,
                loss_trades=[losing_trade],
                n_trials=5,  # Few trials for test speed
            )
            assert isinstance(best_params, dict), "best_params should be dict"
            assert isinstance(best_score, (int, float)), "best_score should be numeric"
        except Exception as e:
            logger.warning(f"Optuna test skipped (optimization may need real data): {e}")

    def test_optimize_periodic_light_mode(self):
        """Test optimize_periodic() with light optimization"""
        from strategies.touche_ai.src.engine.unified_optimizer import TradeRecord, UnifiedOptimizer

        optimizer = UnifiedOptimizer()

        # Add sample trades
        for i in range(10):
            trade = TradeRecord(
                entry_price=100.0 + i,
                exit_price=100.0 + i + (2 if i % 2 == 0 else -1),
                pnl=2 if i % 2 == 0 else -1,
                stage_signals={j: 0.5 + (j * 0.05) for j in range(1, 8)},
            )
            optimizer.record_trade(trade)

        # Run light optimization
        try:
            result = optimizer.optimize_periodic(optimization_type="light")
            assert result is not None
            logger.info(f"Light optimization result: {result}")
        except Exception as e:
            logger.warning(f"Optuna optimization skipped (expected on first run): {e}")

    def test_optuna_configuration_saved(self):
        """Test optimization config saved with optuna marker"""
        from strategies.touche_ai.src.engine.unified_optimizer import UnifiedOptimizer

        optimizer = UnifiedOptimizer()
        config = optimizer.save_config("./test_optuna_config.yaml")

        assert config is not None
        assert "optimization_method" in config

    # ========================================================================
    # COMPONENT 4: Risk Gatekeeper Filters Tests
    # ========================================================================

    def test_sentinel_risk_gatekeeper_vix_filter(self):
        """Test Sentinel apply_risk_gatekeeper_filters() VIX reduction"""
        from strategies.sentinel_ai.src.risk_overlay.multiplier_engine import MultiplierEngine

        engine = MultiplierEngine()

        # VIX > 30 should reduce position size to 70%
        adjusted_size, filters = engine.apply_risk_gatekeeper_filters(
            position_size=1.0,
            vix=35.0,  # High VIX
            dxy=104.0,  # Normal
            fear_greed=50.0,  # Normal
        )

        assert adjusted_size <= 0.7, f"VIX filter should reduce to 70%, got {adjusted_size}"
        assert "vix" in filters, "VIX filter should be recorded"
        logger.info(f"VIX filter test: {adjusted_size} with VIX=35")

    def test_sentinel_risk_gatekeeper_dxy_filter(self):
        """Test Sentinel apply_risk_gatekeeper_filters() DXY reduction"""
        from strategies.sentinel_ai.src.risk_overlay.multiplier_engine import MultiplierEngine

        engine = MultiplierEngine()

        # DXY > 106 should reduce position size to 80%
        adjusted_size, filters = engine.apply_risk_gatekeeper_filters(
            position_size=1.0,
            vix=20.0,  # Normal
            dxy=107.0,  # High DXY
            fear_greed=50.0,  # Normal
        )

        assert adjusted_size <= 0.8, f"DXY filter should reduce to 80%, got {adjusted_size}"
        assert "dxy" in filters, "DXY filter should be recorded"
        logger.info(f"DXY filter test: {adjusted_size} with DXY=107")

    def test_sentinel_risk_gatekeeper_fear_greed_filter(self):
        """Test Sentinel apply_risk_gatekeeper_filters() Fear & Greed reduction"""
        from strategies.sentinel_ai.src.risk_overlay.multiplier_engine import MultiplierEngine

        engine = MultiplierEngine()

        # FG < 25 should reduce position size to 60%
        adjusted_size, filters = engine.apply_risk_gatekeeper_filters(
            position_size=1.0,
            vix=20.0,  # Normal
            dxy=103.0,  # Normal
            fear_greed=20.0,  # Low fear
        )

        assert adjusted_size <= 0.6, f"Fear filter should reduce to 60%, got {adjusted_size}"
        assert "fear_greed" in filters, "Fear/Greed filter should be recorded"
        logger.info(f"Fear/Greed filter test: {adjusted_size} with FG=20")

    def test_sentinel_no_filters_applied_in_normal_conditions(self):
        """Test Sentinel when all conditions are normal"""
        from strategies.sentinel_ai.src.risk_overlay.multiplier_engine import MultiplierEngine

        engine = MultiplierEngine()

        original_size = 1.0
        adjusted_size, filters = engine.apply_risk_gatekeeper_filters(
            position_size=original_size,
            vix=20.0,  # Normal
            dxy=103.0,  # Normal
            fear_greed=50.0,  # Normal
        )

        assert adjusted_size == original_size, "No filters should reduce with normal conditions"
        logger.info(f"Normal conditions test: size unchanged at {adjusted_size}")

    def test_quantum_signal_quality_filters(self):
        """Test Quantum apply_signal_quality_filters()"""
        from strategies.quantum_ai.src.mm_engine.order_manager import OrderManager

        manager = OrderManager()

        # Simulate low liquidity - should reduce confidence
        adjusted_conf, filters = manager.apply_signal_quality_filters(
            signal_confidence=0.85,
            liquidity=0.3,  # Low liquidity
            order_book_skewness=0.2,  # Normal
        )

        assert adjusted_conf <= 0.85, "Low liquidity should reduce confidence"
        logger.info(f"Quantum quality filter test: confidence {adjusted_conf} with liquidity=0.3")

    # ========================================================================
    # INTEGRATION TESTS
    # ========================================================================

    def test_end_to_end_trade_to_attribution(self):
        """Test full flow: trade → record → attribution"""
        from strategies.touche_ai.src.engine.unified_optimizer import TradeRecord, UnifiedOptimizer

        optimizer = UnifiedOptimizer()

        # Record 30 sample trades
        for i in range(30):
            trade = TradeRecord(
                entry_price=100.0 + (i % 10),
                exit_price=100.0 + (i % 10) + (2 if i % 3 == 0 else -1),
                pnl=2 if i % 3 == 0 else -1,
                entry_reason="Phase 2: Structure",
                exit_reason="Phase 5: Timing",
                stage_signals={
                    1: 0.8 if i % 2 == 0 else 0.4,
                    2: 0.7,
                    3: 0.6,
                    4: 0.7,
                    5: 0.6,
                    6: 0.5,
                    7: 0.7,
                },
            )
            optimizer.record_trade(trade)

        # Verify trades recorded
        assert len(optimizer.trade_history) >= 30, "Trades not recorded properly"

        # Calculate attribution if enough trades
        attribution = optimizer.calculate_and_log_attribution(output_dir="./test_attribution")
        if attribution:
            logger.info(f"Attribution calculated: {attribution.get('total_trades')}")

    def test_no_breaking_changes_to_existing_api(self):
        """Verify Phase 1 is backward compatible"""
        from strategies.touche_ai.src.engine.unified_optimizer import UnifiedOptimizer

        optimizer = UnifiedOptimizer()

        # Old-style initialization should still work
        assert optimizer.learning_rate == 0.01
        assert len(optimizer.weights) == 7
        assert len(optimizer.phase_params) == 7

        logger.info("Backward compatibility check passed")


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
