"""
Unit Tests: VIX Monitor
"""
import pytest

from strategies.sentinel_ai.src.macro_indicators.vix_monitor import VIXMonitor


class TestVIXMonitor:
    """VIX Monitor tests."""

    def test_initialization(self):
        """VIX Monitor başlatılabilmeli."""
        monitor = VIXMonitor()
        assert monitor is not None
        assert monitor.current_vix == 20.0

    @pytest.mark.asyncio
    async def test_fetch_vix(self):
        """VIX verisini al."""
        monitor = VIXMonitor()
        indicator = await monitor.fetch_vix()

        assert indicator is not None
        assert indicator.value > 0
        assert indicator.regime in ["NORMAL", "FEAR", "EXTREME_FEAR", "COMPLACENT"]

    def test_multiplier_extreme_fear(self):
        """VIX > 35 → multiplier = 0.4."""
        monitor = VIXMonitor()
        mult = monitor.calculate_multiplier_adjustment(40.0)
        assert mult == 0.4

    def test_multiplier_fear(self):
        """VIX > 25 → multiplier = 0.7."""
        monitor = VIXMonitor()
        mult = monitor.calculate_multiplier_adjustment(30.0)
        assert mult == 0.7

    def test_multiplier_complacency(self):
        """VIX < 15 → multiplier = 1.1 (capped at 1.0)."""
        monitor = VIXMonitor()
        mult = monitor.calculate_multiplier_adjustment(12.0)
        assert mult <= 1.0
        assert mult >= 1.0

    def test_multiplier_neutral(self):
        """VIX 15-25 → multiplier = 1.0."""
        monitor = VIXMonitor()
        mult = monitor.calculate_multiplier_adjustment(20.0)
        assert mult == 1.0

    def test_signal_strength_extreme(self):
        """Extreme values → high confidence."""
        monitor = VIXMonitor()
        strength_high = monitor.get_signal_strength(40.0)
        strength_low = monitor.get_signal_strength(10.0)
        assert strength_high > 0.8
        assert strength_low > 0.8

    def test_signal_strength_moderate(self):
        """Moderate values → lower confidence."""
        monitor = VIXMonitor()
        strength = monitor.get_signal_strength(20.0)
        assert strength < 0.6


@pytest.mark.asyncio
async def test_vix_monitor_normal(normal_market_data):
    """Normal market VIX processing."""
    monitor = VIXMonitor()
    monitor.current_vix = normal_market_data["vix"]

    indicator = await monitor.fetch_vix()
    assert indicator.regime == "NORMAL"


@pytest.mark.asyncio
async def test_vix_monitor_multiplier_logic(risk_off_market_data):
    """Test multiplier calculation logic for different VIX values."""
    monitor = VIXMonitor()

    # Test multiplier adjustments for different VIX values
    extreme_fear_mult = monitor.calculate_multiplier_adjustment(40.0)  # > 35
    normal_mult = monitor.calculate_multiplier_adjustment(20.0)

    # Extreme fear should reduce more
    assert extreme_fear_mult < normal_mult
    assert extreme_fear_mult == 0.4
