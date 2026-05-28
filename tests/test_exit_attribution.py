import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from strategies.analyzer_ai.services.attribution_engine import ExitAttributionEngine


def test_exit_attribution_empty_data_returns_empty_modules(monkeypatch):
    monkeypatch.setattr(ExitAttributionEngine, "_init_redis", lambda self: None)
    engine = ExitAttributionEngine()
    monkeypatch.setattr(engine, "_fetch_trade_rows", lambda period: [])

    result = engine.compute("7d")

    assert result.period == "7d"
    assert result.modules == {}


def test_exit_attribution_scoring_matrix(monkeypatch):
    monkeypatch.setattr(ExitAttributionEngine, "_init_redis", lambda self: None)
    engine = ExitAttributionEngine()

    sample_rows = [
        {"entry_reason": "Touche_EQS_78", "exit_reason": "StopLoss", "exit_price": 43000, "pnl_pct": -2.5},
        {"entry_reason": "Touche_EQS_81", "exit_reason": "TakeProfit", "exit_price": 47000, "pnl_pct": 3.2},
        {"entry_reason": "Macro protection", "exit_reason": "SENTINEL Risk-Off VIX spike", "exit_price": 45500, "pnl_pct": 1.1},
        {"entry_reason": "Liquidity entry", "exit_reason": "QUANTUM liquidity spread widened", "exit_price": 44800, "pnl_pct": -0.9},
        {"entry_reason": "Conflict setup", "exit_reason": "conflict fundamental early warning", "exit_price": 44000, "pnl_pct": -0.2},
    ]

    monkeypatch.setattr(engine, "_fetch_trade_rows", lambda period: sample_rows)

    result = engine.compute("30d")

    assert result.period == "30d"
    assert "touche_ai" in result.modules
    assert "sentinel_ai" in result.modules
    assert "fundamental_ai" in result.modules
    assert "quantum_ai" in result.modules

    assert result.modules["touche_ai"].attribution_score == 0.0  # -1.0 + 1.0
    assert result.modules["sentinel_ai"].attribution_score == 0.5
    assert result.modules["fundamental_ai"].attribution_score == 0.2
    assert result.modules["quantum_ai"].attribution_score == -0.5
    assert result.modules["sentinel_ai"].role == "Risk Saver"
