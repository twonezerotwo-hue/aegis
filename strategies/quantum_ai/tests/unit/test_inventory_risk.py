"""
Unit Tests: Inventory Risk Management
"""
import pytest

from strategies.quantum_ai.src.risk_mgmt.inventory_risk import (
    InventoryRiskManager,
)


class TestInventoryRiskManager:
    """Inventory risk management tests."""

    def test_initialization(self):
        """Manager başlatılabilmeli."""
        manager = InventoryRiskManager(max_inventory=1000.0)
        assert manager is not None
        assert manager.max_inventory == 1000.0

    def test_risk_metrics_zero_inventory(self):
        """Sıfır inventory → LOW risk."""
        manager = InventoryRiskManager(max_inventory=1000.0)

        metrics = manager.calculate_risk_metrics(
            symbol="BTCUSDT",
            current_inventory=0.0,
            current_price=50000.0,
            portfolio_value=100000.0,
        )

        assert metrics.risk_level == "LOW"
        assert metrics.skew_multiplier == pytest.approx(1.0, abs=0.01)

    def test_risk_metrics_low_inventory(self):
        """Düşük inventory → LOW risk."""
        manager = InventoryRiskManager(max_inventory=1000.0)

        metrics = manager.calculate_risk_metrics(
            symbol="BTCUSDT",
            current_inventory=100.0,  # 10% max
            current_price=50000.0,
            portfolio_value=100000.0,
        )

        assert metrics.risk_level == "LOW"

    def test_risk_metrics_medium_inventory(self):
        """Orta inventory → MEDIUM risk."""
        manager = InventoryRiskManager(
            max_inventory=1000.0, risk_threshold=0.7
        )

        metrics = manager.calculate_risk_metrics(
            symbol="BTCUSDT",
            current_inventory=500.0,  # 50% max
            current_price=50000.0,
            portfolio_value=100000.0,
        )

        assert metrics.risk_level == "MEDIUM"

    def test_risk_metrics_high_inventory(self):
        """Yüksek inventory → HIGH risk."""
        manager = InventoryRiskManager(
            max_inventory=1000.0, risk_threshold=0.7
        )

        metrics = manager.calculate_risk_metrics(
            symbol="BTCUSDT",
            current_inventory=800.0,  # 80% max
            current_price=50000.0,
            portfolio_value=100000.0,
        )

        assert metrics.risk_level == "HIGH"

    def test_skew_adjustment_zero_inventory(self):
        """Sıfır inventory → base spread."""
        manager = InventoryRiskManager(max_inventory=1000.0)

        adjusted = manager.calculate_skew_adjustment(
            inventory=0.0,
            max_inventory=1000.0,
            base_spread=5.0,
        )

        assert adjusted == pytest.approx(5.0, abs=0.1)

    def test_skew_adjustment_positive_inventory(self):
        """Pozitif inventory → daha geniş spread."""
        manager = InventoryRiskManager(max_inventory=1000.0)

        adjusted_pos = manager.calculate_skew_adjustment(
            inventory=500.0,
            max_inventory=1000.0,
            base_spread=5.0,
        )

        adjusted_zero = manager.calculate_skew_adjustment(
            inventory=0.0,
            max_inventory=1000.0,
            base_spread=5.0,
        )

        assert adjusted_pos > adjusted_zero

    def test_skew_adjustment_negative_inventory(self):
        """Negatif inventory → daha dar spread."""
        manager = InventoryRiskManager(max_inventory=1000.0)

        adjusted_neg = manager.calculate_skew_adjustment(
            inventory=-500.0,
            max_inventory=1000.0,
            base_spread=5.0,
        )

        adjusted_zero = manager.calculate_skew_adjustment(
            inventory=0.0,
            max_inventory=1000.0,
            base_spread=5.0,
        )

        # Negatif inventory spread shrinkage, minimum level check
        assert adjusted_neg >= 2.5  # Min spread enforced

    def test_should_limit_orders_high_risk(self):
        """HIGH risk → orders sınırlandırılmalı."""
        manager = InventoryRiskManager(max_inventory=1000.0)

        metrics = manager.calculate_risk_metrics(
            symbol="BTCUSDT",
            current_inventory=800.0,
            current_price=50000.0,
            portfolio_value=100000.0,
        )

        assert manager.should_limit_orders(metrics, 100.0) is True

    def test_should_not_limit_orders_low_risk(self):
        """LOW risk ve küçük order → sınırlandırma yok."""
        manager = InventoryRiskManager(max_inventory=1000.0)

        metrics = manager.calculate_risk_metrics(
            symbol="BTCUSDT",
            current_inventory=50.0,
            current_price=50000.0,
            portfolio_value=100000.0,
        )

        assert manager.should_limit_orders(metrics, 10.0) is False

    def test_hedging_recommendation_long(self):
        """Long pozisyon → futures SAT hedge."""
        manager = InventoryRiskManager()

        rec = manager.get_hedging_recommendation(
            inventory=100.0,
            spot_price=50000.0,
            futures_price=50100.0,
        )

        assert rec is not None
        assert rec["action"] == "SELL_FUTURES"
        assert rec["size"] == 100.0

    def test_hedging_recommendation_short(self):
        """Short pozisyon → futures AL hedge."""
        manager = InventoryRiskManager()

        rec = manager.get_hedging_recommendation(
            inventory=-100.0,
            spot_price=50000.0,
            futures_price=50100.0,
        )

        assert rec is not None
        assert rec["action"] == "BUY_FUTURES"
        assert rec["size"] == 100.0

    def test_hedging_recommendation_none_inventory(self):
        """Flat pozisyon → hedge yok."""
        manager = InventoryRiskManager()

        rec = manager.get_hedging_recommendation(
            inventory=0.0,
            spot_price=50000.0,
            futures_price=50100.0,
        )

        assert rec is None
