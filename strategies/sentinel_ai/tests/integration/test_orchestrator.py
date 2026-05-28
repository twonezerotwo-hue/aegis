"""
Integration Tests: Sentinel AI Orchestrator
"""
import pytest

from strategies.sentinel_ai.orchestrator import SentinelAIOrchestrator


class TestSentinelAIOrchestrator:
    """Sentinel AI Orchestrator integration tests."""

    def test_orchestrator_initialization(self, sample_config):
        """Orchestrator başlatılabilmeli."""
        orchestrator = SentinelAIOrchestrator(sample_config)
        assert orchestrator is not None
        assert orchestrator.last_multiplier == 1.0

    @pytest.mark.asyncio
    async def test_analyze_normal_market(self, sample_config, normal_market_data):
        """Normal market analysis."""
        orchestrator = SentinelAIOrchestrator(sample_config)

        decision = await orchestrator.analyze_market_sentiment(
            vix=normal_market_data["vix"],
            dxy=normal_market_data["dxy"],
            fear_greed=normal_market_data["fear_greed"],
            fed_rates=normal_market_data["fed_rates"],
            oil_prices=normal_market_data["oil_prices"],
        )

        assert decision is not None
        assert decision.risk_multiplier.value > 0
        assert decision.recommendation in ["REDUCE_SIZE", "MAINTAIN", "INCREASE_SIZE"]
        assert 0.8 <= decision.risk_multiplier.value <= 1.0

    @pytest.mark.asyncio
    async def test_analyze_risk_off(self, sample_config, risk_off_market_data):
        """Risk-off market analysis."""
        orchestrator = SentinelAIOrchestrator(sample_config)

        decision = await orchestrator.analyze_market_sentiment(
            vix=risk_off_market_data["vix"],
            dxy=risk_off_market_data["dxy"],
            fear_greed=risk_off_market_data["fear_greed"],
            fed_rates=risk_off_market_data["fed_rates"],
            oil_prices=risk_off_market_data["oil_prices"],
        )

        assert decision.recommendation == "REDUCE_SIZE"
        assert decision.risk_multiplier.value < 0.7

    @pytest.mark.asyncio
    async def test_analyze_risk_on(self, sample_config, risk_on_market_data):
        """Risk-on market analysis."""
        orchestrator = SentinelAIOrchestrator(sample_config)

        decision = await orchestrator.analyze_market_sentiment(
            vix=risk_on_market_data["vix"],
            dxy=risk_on_market_data["dxy"],
            fear_greed=risk_on_market_data["fear_greed"],
            fed_rates=risk_on_market_data["fed_rates"],
            oil_prices=risk_on_market_data["oil_prices"],
        )

        # Risk-on should have reasonable multiplier (may not be >0.9 due to greed penalty)
        assert decision.risk_multiplier.value >= 0.7

    @pytest.mark.asyncio
    async def test_analyze_panic(self, sample_config, panic_market_data):
        """Panic market analysis."""
        orchestrator = SentinelAIOrchestrator(sample_config)

        decision = await orchestrator.analyze_market_sentiment(
            vix=panic_market_data["vix"],
            dxy=panic_market_data["dxy"],
            fear_greed=panic_market_data["fear_greed"],
            fed_rates=panic_market_data["fed_rates"],
            oil_prices=panic_market_data["oil_prices"],
        )

        assert decision.market_regime.value == "PANIC"
        assert decision.risk_multiplier.value <= 0.4
        assert len(decision.alerts) > 0

    @pytest.mark.asyncio
    async def test_get_current_multiplier(self, sample_config, normal_market_data):
        """Get current multiplier."""
        orchestrator = SentinelAIOrchestrator(sample_config)

        multiplier = await orchestrator.get_current_multiplier()

        assert isinstance(multiplier, float)
        assert 0.1 <= multiplier <= 1.0

    def test_get_multiplier_statistics(self, sample_config):
        """Get multiplier statistics."""
        orchestrator = SentinelAIOrchestrator(sample_config)

        # Add some history
        orchestrator.multiplier_history = [0.8, 0.85, 0.9, 0.75, 0.8]

        stats = orchestrator.get_multiplier_statistics()

        assert stats["current"] == 0.8
        assert stats["min"] == 0.75
        assert stats["max"] == 0.9
        assert "average" in stats
        assert "std_dev" in stats

    @pytest.mark.asyncio
    async def test_analyze_with_defaults(self, sample_config):
        """Analysis with API defaults (None values)."""
        orchestrator = SentinelAIOrchestrator(sample_config)

        # Pass None to use defaults
        decision = await orchestrator.analyze_market_sentiment()

        assert decision is not None
        assert decision.risk_multiplier.value > 0

    @pytest.mark.asyncio
    async def test_multiplier_history_tracking(self, sample_config, normal_market_data):
        """Multiplier history should be tracked."""
        orchestrator = SentinelAIOrchestrator(sample_config)

        for _ in range(5):
            await orchestrator.analyze_market_sentiment(
                vix=normal_market_data["vix"],
                dxy=normal_market_data["dxy"],
                fear_greed=normal_market_data["fear_greed"],
            )

        assert len(orchestrator.multiplier_history) == 5

    @pytest.mark.asyncio
    async def test_alert_generation(self, sample_config):
        """Alerts should be generated for critical conditions."""
        orchestrator = SentinelAIOrchestrator(sample_config)

        decision = await orchestrator.analyze_market_sentiment(
            vix=50.0,  # Extreme
            dxy=110.0,
            fear_greed=10.0,
        )

        assert len(decision.alerts) > 0
        assert any("CRITICAL" in alert for alert in decision.alerts)
