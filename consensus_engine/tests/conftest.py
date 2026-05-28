"""
Consensus Engine — Test Fixtures
"""
import pytest
from datetime import datetime, timezone

from consensus_engine.src.models import (
    ToucheSignal,
    FundamentalSignal,
    ConsensusConfig,
    RiskMetrics,
)


@pytest.fixture
def default_config():
    """Default consensus configuration."""
    return ConsensusConfig(
        touche_weight=0.50,
        fundamental_weight=0.50,
        eqs_weak_signal=30.0,
        eqs_strong_signal=55.0,
        fundamental_conservative=30.0,
        fundamental_conservative_mult=0.3,
        fundamental_bullish=70.0,
        fundamental_bullish_mult=1.2,
        min_confidence=0.35,
        alignment_bonus=0.15,
        contradiction_penalty=0.30,
        kelly_fraction=0.25,
        kelly_safety_margin=0.5,
        max_position_size=0.15,
    )


@pytest.fixture
def bullish_touche_signal():
    """Bullish Touche signal."""
    return ToucheSignal(
        symbol="BTCUSDT",
        timeframe="4h",
        signal="AL",
        eqs=75.0,
        score=75.0,
        reason="Strong bullish setup",
        phase_results={"phase1": 80, "phase3": 70},
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def bearish_touche_signal():
    """Bearish Touche signal."""
    return ToucheSignal(
        symbol="BTCUSDT",
        timeframe="4h",
        signal="SAT",
        eqs=35.0,
        score=35.0,
        reason="Weak bearish setup",
        phase_results={"phase1": 30, "phase3": 40},
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def neutral_touche_signal():
    """Neutral Touche signal."""
    return ToucheSignal(
        symbol="BTCUSDT",
        timeframe="4h",
        signal="BEKLE",
        eqs=50.0,
        score=50.0,
        reason="Neutral setup",
        phase_results={"phase1": 50, "phase3": 50},
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def bullish_fundamental_signal():
    """Bullish Fundamental signal."""
    return FundamentalSignal(
        symbol="BTCUSDT",
        signal="BULLISH",
        score=80.0,
        factors={"pe_ratio": 15.0, "growth": 20.0},
        reason="Strong fundamentals",
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def bearish_fundamental_signal():
    """Bearish Fundamental signal."""
    return FundamentalSignal(
        symbol="BTCUSDT",
        signal="BEARISH",
        score=25.0,
        factors={"pe_ratio": 30.0, "growth": -10.0},
        reason="Weak fundamentals",
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def neutral_fundamental_signal():
    """Neutral Fundamental signal."""
    return FundamentalSignal(
        symbol="BTCUSDT",
        signal="NEUTRAL",
        score=50.0,
        factors={"pe_ratio": 20.0, "growth": 5.0},
        reason="Mixed fundamentals",
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def default_risk_metrics():
    """Default portfolio risk metrics."""
    return RiskMetrics(
        portfolio_value=100000.0,
        cash_reserve=5000.0,
        total_exposure=50000.0,
        max_single_position=0.10,
        portfolio_volatility=0.02,
        sharpe_ratio=1.5,
        max_drawdown=-0.05,
        correlation_with_benchmark=0.8,
    )
