"""
Integration Tests: Consensus Pipeline
"""
import pytest

from consensus_engine.orchestrator import ConsensusOrchestrator


class TestConsensusOrchestrator:
    """Consensus pipeline testleri."""
    
    def test_orchestrator_initialization(self, default_config):
        """Orchestrator başlatılabilmeli."""
        orchestrator = ConsensusOrchestrator(default_config)
        assert orchestrator is not None
        assert orchestrator.config == default_config
    
    @pytest.mark.asyncio
    async def test_bullish_scenario(self, default_config):
        """Bullish sinyaller AL döndürmeli."""
        orchestrator = ConsensusOrchestrator(default_config)
        
        touche_result = {
            "eqs": 80.0,
            "recommendation": "BUY",
            "reasoning": "Strong bullish",
            "phase_results": {"phase1": 80, "phase3": 75},
        }
        
        fundamental_result = {
            "signal": "BULLISH",
            "score": 85.0,
            "reasoning": "Strong fundamentals",
            "factors": {"pe_ratio": 15.0, "growth": 25.0},
        }
        
        decision = await orchestrator.process(
            symbol="BTCUSDT",
            touche_result=touche_result,
            fundamental_result=fundamental_result,
            portfolio_value=100000.0,
            current_price=50000.0,
            atr=1000.0,
        )
        
        assert decision.action == "AL"
        assert decision.confidence > 0.6
        assert decision.position_size > 0
        assert decision.risk_level in ("LOW", "MEDIUM", "HIGH")
    
    @pytest.mark.asyncio
    async def test_bearish_scenario(self, default_config):
        """Bearish sinyaller SAT döndürmeli."""
        orchestrator = ConsensusOrchestrator(default_config)

        touche_result = {
            "eqs": 65.0,
            "recommendation": "SELL",
            "reasoning": "Strong market downtrend",
            "phase_results": {"phase1": 70, "phase3": 60},
        }

        fundamental_result = {
            "signal": "BEARISH",
            "score": 75.0,
            "reasoning": "Strong bearish fundamentals",
            "factors": {"pe_ratio": 35.0, "growth": -25.0},
        }

        decision = await orchestrator.process(
            symbol="BTCUSDT",
            touche_result=touche_result,
            fundamental_result=fundamental_result,
        )

        assert decision.action == "SAT"
        assert decision.confidence > 0.5
    
    @pytest.mark.asyncio
    async def test_neutral_scenario(self, default_config):
        """Neutral sinyaller BEKLE döndürmeli."""
        orchestrator = ConsensusOrchestrator(default_config)
        
        touche_result = {
            "eqs": 50.0,
            "recommendation": "HOLD",
            "reasoning": "Undecided",
            "phase_results": {},
        }
        
        fundamental_result = {
            "signal": "NEUTRAL",
            "score": 50.0,
            "reasoning": "Mixed signals",
            "factors": {},
        }
        
        decision = await orchestrator.process(
            symbol="BTCUSDT",
            touche_result=touche_result,
            fundamental_result=fundamental_result,
        )
        
        assert decision.action == "BEKLE"
        assert decision.position_size == 0
    
    @pytest.mark.asyncio
    async def test_contradictory_signals(self, default_config):
        """Çelişkili sinyaller BEKLE döndürmeli."""
        orchestrator = ConsensusOrchestrator(default_config)
        
        touche_result = {
            "eqs": 75.0,
            "recommendation": "BUY",
            "reasoning": "Bullish",
            "phase_results": {},
        }
        
        fundamental_result = {
            "signal": "BEARISH",
            "score": 25.0,
            "reasoning": "Bearish",
            "factors": {},
        }
        
        decision = await orchestrator.process(
            symbol="BTCUSDT",
            touche_result=touche_result,
            fundamental_result=fundamental_result,
        )
        
        # Çelişkili sinyallar BEKLE veya düşük confidence
        assert decision.confidence < 0.6 or decision.action == "BEKLE"
    
    @pytest.mark.asyncio
    async def test_error_handling(self, default_config):
        """Hata durumunda neutral karar döndürmeli."""
        orchestrator = ConsensusOrchestrator(default_config)
        
        # Invalid input
        touche_result = None
        fundamental_result = None
        
        # Should not raise exception
        try:
            decision = await orchestrator.process(
                symbol="BTCUSDT",
                touche_result=touche_result or {},
                fundamental_result=fundamental_result or {},
            )
            assert decision.action is not None
        except Exception:
            pytest.fail("Orchestrator should handle errors gracefully")


class TestDecisionFields:
    """Karar alanlarının kontrolü."""
    
    @pytest.mark.asyncio
    async def test_decision_completeness(self, default_config):
        """Tüm gerekli alanlar doldurulmalı."""
        orchestrator = ConsensusOrchestrator(default_config)
        
        decision = await orchestrator.process(
            symbol="BTCUSDT",
            touche_result={"eqs": 70.0, "recommendation": "BUY"},
            fundamental_result={"signal": "BULLISH", "score": 75.0},
        )
        
        # Check all required fields
        assert decision.symbol == "BTCUSDT"
        assert decision.action in ("AL", "SAT", "BEKLE")
        assert 0 <= decision.confidence <= 1
        assert 0 <= decision.position_size <= 1
        assert decision.touche_signal is not None
        assert decision.fundamental_signal is not None
        assert decision.risk_level is not None
        assert decision.reasoning is not None
