"""
Unit Tests: DXY Monitor
"""
import pytest

from strategies.sentinel_ai.src.macro_indicators.dxy_monitor import DXYMonitor


class TestDXYMonitor:
    """DXY Monitor tests."""

    def test_initialization(self):
        """DXY Monitor başlatılabilmeli."""
        monitor = DXYMonitor()
        assert monitor is not None
        assert monitor.current_dxy == 103.0

    @pytest.mark.asyncio
    async def test_fetch_dxy(self):
        """DXY verisini al."""
        monitor = DXYMonitor()
        indicator = await monitor.fetch_dxy()

        assert indicator is not None
        assert indicator.value > 0
        assert indicator.strength in ["WEAK", "NEUTRAL", "STRONG", "VERY_STRONG"]

    def test_multiplier_very_strong(self):
        """DXY > 108.0 → multiplier = multiplier * 0.6."""
        monitor = DXYMonitor()
        mult = monitor.calculate_multiplier_adjustment(109.0)
        assert mult == 0.6

    def test_multiplier_strong(self):
        """DXY > 105.5 → multiplier = multiplier * 0.8."""
        monitor = DXYMonitor()
        mult = monitor.calculate_multiplier_adjustment(106.0)
        assert mult == 0.8

    def test_multiplier_neutral(self):
        """DXY 100-105.5 → multiplier = 1.0."""
        monitor = DXYMonitor()
        mult = monitor.calculate_multiplier_adjustment(102.0)
        assert mult == 1.0

    def test_signal_strength_extreme(self):
        """Extreme values → high confidence."""
        monitor = DXYMonitor()
        # Very extreme values
        strength_high = monitor.get_signal_strength(112.0)  # Very high
        strength_low = monitor.get_signal_strength(95.0)  # Very low
        assert strength_high >= 0.7
        assert strength_low >= 0.7

    def test_signal_strength_normal(self):
        """Normal values → lower confidence."""
        monitor = DXYMonitor()
        strength = monitor.get_signal_strength(103.0)
        assert strength < 0.5


@pytest.mark.asyncio
async def test_dxy_monitor_logic(risk_off_market_data, risk_on_market_data):
    """Test multiplier logic for strong/weak dollar values."""
    monitor = DXYMonitor()

    # Test direct calculation
    mult_strong = monitor.calculate_multiplier_adjustment(risk_off_market_data["dxy"])
    mult_weak = monitor.calculate_multiplier_adjustment(risk_on_market_data["dxy"])

    # Strong DXY should reduce more than weak
    assert mult_strong <= mult_weak
