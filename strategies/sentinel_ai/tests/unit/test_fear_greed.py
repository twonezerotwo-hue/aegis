"""
Unit Tests: Fear & Greed Monitor
"""
import pytest

from strategies.sentinel_ai.src.macro_indicators.fear_greed import FearGreedMonitor


class TestFearGreedMonitor:
    """Fear & Greed Monitor tests."""

    def test_initialization(self):
        """Fear & Greed Monitor başlatılabilmeli."""
        monitor = FearGreedMonitor()
        assert monitor is not None
        assert monitor.current_index == 50.0

    @pytest.mark.asyncio
    async def test_fetch_fear_greed(self):
        """Fear & Greed verisini al."""
        monitor = FearGreedMonitor()
        indicator = await monitor.fetch_fear_greed()

        assert indicator is not None
        assert 0 <= indicator.value <= 100
        assert indicator.classification in [
            "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"
        ]

    def test_multiplier_extreme_fear(self):
        """Index < 20 → multiplier = multiplier * 0.7."""
        monitor = FearGreedMonitor()
        mult = monitor.calculate_multiplier_adjustment(15.0)
        assert mult == 0.7

    def test_multiplier_fear(self):
        """Index < 40 → multiplier = multiplier * 0.9."""
        monitor = FearGreedMonitor()
        mult = monitor.calculate_multiplier_adjustment(35.0)
        assert mult == 0.9

    def test_multiplier_extreme_greed(self):
        """Index > 80 → multiplier = multiplier * 0.8."""
        monitor = FearGreedMonitor()
        mult = monitor.calculate_multiplier_adjustment(85.0)
        assert mult == 0.8

    def test_multiplier_neutral(self):
        """Index 40-80 → multiplier = 1.0."""
        monitor = FearGreedMonitor()
        mult = monitor.calculate_multiplier_adjustment(60.0)
        assert mult == 1.0

    def test_signal_strength_extreme(self):
        """Extreme values → high confidence."""
        monitor = FearGreedMonitor()
        strength_low = monitor.get_signal_strength(10.0)
        strength_high = monitor.get_signal_strength(90.0)
        assert strength_low > 0.8
        assert strength_high > 0.8

    def test_signal_strength_moderate(self):
        """Moderate values → lower confidence."""
        monitor = FearGreedMonitor()
        strength = monitor.get_signal_strength(50.0)
        assert strength < 0.5


@pytest.mark.asyncio
async def test_fear_greed_monitor_logic(risk_off_market_data, risk_on_market_data):
    """Test fear/greed logic for different conditions."""
    monitor = FearGreedMonitor()

    # Test multiplier calculations directly
    mult_fear = monitor.calculate_multiplier_adjustment(risk_off_market_data["fear_greed"])
    mult_greed = monitor.calculate_multiplier_adjustment(risk_on_market_data["fear_greed"])

    # Both should reduce multiplier
    assert mult_fear <= 1.0
    assert mult_greed <= 1.0
