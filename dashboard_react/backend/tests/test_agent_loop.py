import sys
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.agent_loop import AgentDecision, AgentOrchestrator
from services.agent_guard import CANONICAL_DECISION_PERMISSION, guard_agent_response


def _build_agent(consensus_payload: dict, *, min_confidence: float = 0.55, min_edge: float = 0.04) -> AgentOrchestrator:
    agent = AgentOrchestrator()
    agent.journal = []
    agent.config.watch_symbols = ["BTC/USDT"]
    agent.config.timeframe = "5m"
    agent.config.candidate_timeframes = ["5m"]
    agent.config.horizon = "medium"
    agent.config.min_confidence = min_confidence
    agent.config.min_score_edge = min_edge
    agent.config.max_signals_per_day = 20
    agent.config.execution_mode = "DRY_RUN"

    async def consensus_fn(symbol: str, timeframe: str, horizon: str) -> dict:
        assert symbol == "BTC/USDT"
        assert timeframe == "5m"
        assert horizon == "medium"
        return consensus_payload

    agent.wire(
        consensus_fn=consensus_fn,
        enqueue_fn=lambda sig: None,
        kill_switch_fn=lambda: (False, ""),
        price_check_fn=None,
    )
    return agent


@pytest.mark.asyncio
async def test_agent_thresholds_can_derive_signal_from_dashboard_hold_band():
    agent = _build_agent(
        {
            "action": "HOLD",
            "weighted_score": 0.5694,
            "confidence": 0.5,
        }
    )

    result = await agent.run_once()
    decision = result["new_decisions"][0]

    assert decision["decision"] == "would_signal"
    assert decision["score"] == pytest.approx(0.5694)
    assert decision["confidence"] == pytest.approx(0.5694)
    assert "agent esiginden turetildi" in decision["reason"]


@pytest.mark.asyncio
async def test_run_once_returns_new_decision_when_journal_ring_is_full():
    agent = _build_agent(
        {
            "action": "HOLD",
            "weighted_score": 0.5694,
            "confidence": 0.5,
        }
    )
    agent.journal = [
        AgentDecision(
            ts=f"2026-01-01T00:00:{idx % 60:02d}+00:00",
            symbol="BTC/USDT",
            timeframe="5m",
            action="HOLD",
            score=0.5,
            confidence=0.5,
            decision="no_action",
            reason="seed",
            mode="DRY_RUN",
        )
        for idx in range(250)
    ]

    result = await agent.run_once()

    assert len(agent.journal) == 250
    assert len(result["new_decisions"]) == 1
    assert result["new_decisions"][0]["decision"] == "would_signal"


@pytest.mark.asyncio
async def test_agent_still_blocks_hold_when_score_edge_is_too_small():
    agent = _build_agent(
        {
            "action": "HOLD",
            "weighted_score": 0.53,
            "confidence": 0.5,
        }
    )

    result = await agent.run_once()
    decision = result["new_decisions"][0]

    assert decision["decision"] == "no_action"
    assert decision["confidence"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_agent_selects_best_candidate_across_timeframes():
    agent = AgentOrchestrator()
    agent.journal = []
    agent.config.watch_symbols = ["BTC/USDT"]
    agent.config.timeframe = "5m"
    agent.config.candidate_timeframes = ["5m", "15m", "1h"]
    agent.config.horizon = "medium"
    agent.config.min_confidence = 0.55
    agent.config.min_score_edge = 0.04
    agent.config.max_signals_per_day = 20
    agent.config.execution_mode = "DRY_RUN"

    payloads = {
        "5m": {"action": "HOLD", "weighted_score": 0.53, "confidence": 0.5},
        "15m": {"action": "HOLD", "weighted_score": 0.5694, "confidence": 0.5},
        "1h": {"action": "HOLD", "weighted_score": 0.61, "confidence": 0.5},
    }

    async def consensus_fn(symbol: str, timeframe: str, horizon: str) -> dict:
        assert symbol == "BTC/USDT"
        assert horizon == "medium"
        return payloads[timeframe]

    agent.wire(
        consensus_fn=consensus_fn,
        enqueue_fn=lambda sig: None,
        kill_switch_fn=lambda: (False, ""),
        price_check_fn=None,
    )

    result = await agent.run_once()
    decision = result["new_decisions"][0]

    assert decision["decision"] == "would_signal"
    assert decision["timeframe"] == "1h"
    assert decision["score"] == pytest.approx(0.61)
    assert decision["confidence"] == pytest.approx(0.61)
    assert "5m=0.530" in decision["reason"]
    assert "1h=0.610" in decision["reason"]
    assert len(decision["evaluations"]) == 3
    assert decision["evaluations"][-1]["passes"] is True


def test_agent_guard_marks_response_signal_only():
    response = guard_agent_response(
        {"status": "ok", "final_decision": True, "summary": "execute this trade"},
        source="test",
    )

    assert response["decision_permission"] == CANONICAL_DECISION_PERMISSION
    assert response["final_decision"] is False
    assert response["execution_authority"] == "human"
    assert response["guard_warnings"]
