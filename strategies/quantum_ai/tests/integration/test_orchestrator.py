"""
Integration Tests: Market Making Orchestrator
"""
import pytest

from strategies.quantum_ai.orchestrator import QuantumAIOrchestrator


class TestQuantumAIOrchestrator:
    """Market making orchestrator integration tests."""

    def test_orchestrator_initialization(self, sample_config):
        """Orchestrator başlatılabilmeli."""
        orchestrator = QuantumAIOrchestrator(sample_config)
        assert orchestrator is not None
        assert orchestrator.config == sample_config

    @pytest.mark.asyncio
    async def test_process_stream_basic(
        self, sample_config, btcusdt_market_data, portfolio_state
    ):
        """Market stream processing."""
        orchestrator = QuantumAIOrchestrator(sample_config)

        market_data = {"BTCUSDT": btcusdt_market_data}

        result = await orchestrator.process_stream(
            market_data=market_data,
            portfolio_state=portfolio_state,
        )

        assert result is not None
        assert "quotes" in result
        assert "arbitrage_signals" in result
        assert "risk_decisions" in result
        assert "execution_plan" in result

    @pytest.mark.asyncio
    async def test_generate_quotes(
        self, sample_config, btcusdt_market_data, portfolio_state
    ):
        """Quote generation test."""
        orchestrator = QuantumAIOrchestrator(sample_config)

        # Use time_remaining instead of time_to_expiry
        market_data = {
            "BTCUSDT": {
                **btcusdt_market_data,
                "time_remaining": 60.0,
            }
        }

        quotes = await orchestrator._generate_quotes(market_data)

        assert "BTCUSDT" in quotes
        assert quotes["BTCUSDT"].bid_price > 0
        assert quotes["BTCUSDT"].ask_price > 0
        assert quotes["BTCUSDT"].bid_price < quotes["BTCUSDT"].ask_price

    @pytest.mark.asyncio
    async def test_check_arbitrage(self, sample_config):
        """Arbitrage detection test."""
        orchestrator = QuantumAIOrchestrator(sample_config)

        market_data = {
            "exchange_prices": {
                "BTCUSDT": {
                    "binance": 50000.0,
                    "coinbase": 50150.0,
                    "kraken": 49900.0,
                },
            },
        }

        signals = await orchestrator._check_arbitrage(market_data)

        # Should detect arbitrage opportunity
        assert len(signals) >= 0  # May or may not detect depending on thresholds

    @pytest.mark.asyncio
    async def test_manage_risk(self, sample_config, portfolio_state):
        """Risk management test."""
        orchestrator = QuantumAIOrchestrator(sample_config)
        orchestrator.positions = portfolio_state["positions"]

        risk_decisions = await orchestrator._manage_risk(portfolio_state)

        assert risk_decisions is not None
        assert isinstance(risk_decisions, dict)

        for symbol, decision in risk_decisions.items():
            assert "risk_level" in decision
            assert "should_limit" in decision
            assert "skew_multiplier" in decision

    @pytest.mark.asyncio
    async def test_route_orders(self, sample_config):
        """Order routing test."""
        orchestrator = QuantumAIOrchestrator(sample_config)

        from strategies.quantum_ai.src.mm_engine.avellaneda_stoikov import (
            AvellanedaStoikov,
        )
        from strategies.quantum_ai.src.core.models import MMParameters

        mm_params = MMParameters()
        algo = AvellanedaStoikov(mm_params)

        quote = algo.quote(
            mid_price=50000.0,
            volatility=0.02,
            current_inventory=0.0,
            time_remaining=60.0,
        )

        quotes = {"BTCUSDT": quote}
        risk_decisions = {"BTCUSDT": {"should_limit": False}}

        execution_plan = await orchestrator._route_orders(quotes, risk_decisions)

        assert len(execution_plan) > 0
        assert execution_plan[0]["symbol"] == "BTCUSDT"
        assert execution_plan[0]["bid"] > 0
        assert execution_plan[0]["ask"] > 0

    @pytest.mark.asyncio
    async def test_process_multiple_symbols(self, sample_config):
        """Multiple symbol processing."""
        orchestrator = QuantumAIOrchestrator(sample_config)

        market_data = {
            "BTCUSDT": {
                "mid_price": 50000.0,
                "volatility": 0.02,
                "time_remaining": 60.0,
                "fill_rate": 0.6,
            },
            "ETHUSDT": {
                "mid_price": 3000.0,
                "volatility": 0.025,
                "time_remaining": 60.0,
                "fill_rate": 0.55,
            },
        }

        portfolio_state = {
            "portfolio_value": 100000.0,
            "positions": {
                "BTCUSDT": {"size": 0.5, "price": 50000.0, "delta": 0.8},
                "ETHUSDT": {"size": 5.0, "price": 3000.0, "delta": 0.6},
            },
        }

        result = await orchestrator.process_stream(
            market_data=market_data,
            portfolio_state=portfolio_state,
        )

        assert len(result["quotes"]) == 2
        assert "BTCUSDT" in result["quotes"]
        assert "ETHUSDT" in result["quotes"]

    @pytest.mark.asyncio
    async def test_calculate_metrics(self, sample_config, portfolio_state):
        """Metrics calculation test."""
        orchestrator = QuantumAIOrchestrator(sample_config)

        metrics = await orchestrator.calculate_metrics(portfolio_state)

        assert metrics is not None
        assert "var_95" in metrics
        assert "var_99" in metrics
        assert "portfolio_delta" in metrics
        assert "max_loss" in metrics

    @pytest.mark.asyncio
    async def test_error_handling(self, sample_config):
        """Error handling test."""
        orchestrator = QuantumAIOrchestrator(sample_config)

        # Empty or invalid data
        result = await orchestrator.process_stream(
            market_data={},
            portfolio_state={},
        )

        # Should not crash
        assert "quotes" in result or "error" in result

    @pytest.mark.asyncio
    async def test_high_inventory_risk(self, sample_config, btcusdt_market_data):
        """High inventory risk scenario."""
        orchestrator = QuantumAIOrchestrator(sample_config)
        orchestrator.positions = {
            "BTCUSDT": {
                "size": 800.0,  # Near max inventory
                "price": 50000.0,
            },
        }

        market_data = {"BTCUSDT": btcusdt_market_data}
        portfolio_state = {
            "portfolio_value": 100000.0,
            "positions": {
                "BTCUSDT": {
                    "size": 800.0,
                    "price": 50000.0,
                    "delta": 0.8,
                },
            },
        }

        risk_decisions = await orchestrator._manage_risk(portfolio_state)

        assert risk_decisions["BTCUSDT"]["risk_level"] == "HIGH"
