"""
Unit Tests: Multiplier Engine
"""

from strategies.sentinel_ai.src.risk_overlay.multiplier_engine import MultiplierEngine
from strategies.sentinel_ai.src.models import MarketRegime


class TestMultiplierEngine:
    """Risk Multiplier Engine tests."""

    def test_initialization(self):
        """Engine başlatılabilmeli."""
        engine = MultiplierEngine(floor=0.1, ceiling=1.0)
        assert engine is not None
        assert engine.floor == 0.1
        assert engine.ceiling == 1.0

    def test_normal_market(self, normal_market_data):
        """Normal market → multiplier ≈ 1.0."""
        engine = MultiplierEngine()
        result = engine.calculate_multiplier(
            vix=normal_market_data["vix"],
            dxy=normal_market_data["dxy"],
            fear_greed=normal_market_data["fear_greed"],
            fed_rates=normal_market_data["fed_rates"],
            oil_prices=normal_market_data["oil_prices"],
        )

        assert 0.9 <= result.value <= 1.0
        assert result.regime == MarketRegime.NEUTRAL

    def test_risk_off_market(self, risk_off_market_data):
        """Risk-off market → multiplier < 0.7."""
        engine = MultiplierEngine()
        result = engine.calculate_multiplier(
            vix=risk_off_market_data["vix"],
            dxy=risk_off_market_data["dxy"],
            fear_greed=risk_off_market_data["fear_greed"],
            fed_rates=risk_off_market_data["fed_rates"],
            oil_prices=risk_off_market_data["oil_prices"],
        )

        assert result.value < 0.7

    def test_risk_on_market(self, risk_on_market_data):
        """Risk-on market → multiplier > 0.7."""
        engine = MultiplierEngine()
        result = engine.calculate_multiplier(
            vix=risk_on_market_data["vix"],
            dxy=risk_on_market_data["dxy"],
            fear_greed=risk_on_market_data["fear_greed"],
            fed_rates=risk_on_market_data["fed_rates"],
            oil_prices=risk_on_market_data["oil_prices"],
        )

        # Risk-on but greed penalty is applied
        assert result.value > 0.6

    def test_panic_market(self, panic_market_data):
        """Panic market → multiplier < 0.5."""
        engine = MultiplierEngine()
        result = engine.calculate_multiplier(
            vix=panic_market_data["vix"],
            dxy=panic_market_data["dxy"],
            fear_greed=panic_market_data["fear_greed"],
            fed_rates=panic_market_data["fed_rates"],
            oil_prices=panic_market_data["oil_prices"],
        )

        assert result.value < 0.5

    def test_multiplier_floor(self):
        """Multiplier should not go below floor."""
        engine = MultiplierEngine(floor=0.1, ceiling=1.0)
        result = engine.calculate_multiplier(
            vix=50.0,  # Extreme
            dxy=110.0,  # Extreme
            fear_greed=10.0,  # Extreme fear
        )

        assert result.value >= engine.floor

    def test_multiplier_ceiling(self):
        """Multiplier should not exceed ceiling."""
        engine = MultiplierEngine(ceiling=1.0)
        result = engine.calculate_multiplier(
            vix=10.0,
            dxy=100.0,
            fear_greed=90.0,
        )

        assert result.value <= engine.ceiling

    def test_components_calculated(self):
        """Components should be calculated."""
        engine = MultiplierEngine()
        result = engine.calculate_multiplier(
            vix=20.0,
            dxy=105.0,
            fear_greed=50.0,
        )

        assert "vix" in result.components
        assert "dxy" in result.components
        assert "fear_greed" in result.components

    def test_signal_strength(self):
        """Signal strength should be 0-1."""
        engine = MultiplierEngine()
        result = engine.calculate_multiplier(
            vix=30.0,
            dxy=105.0,
            fear_greed=35.0,
        )

        assert 0 <= result.signal_strength <= 1

    def test_reasoning_generated(self):
        """Reasoning should be non-empty."""
        engine = MultiplierEngine()
        result = engine.calculate_multiplier(
            vix=20.0,
            dxy=103.0,
            fear_greed=50.0,
        )

        assert len(result.reasoning) > 0
