"""
Sentinel AI — Test Fixtures
"""
import pytest
from datetime import datetime, timezone

from strategies.sentinel_ai.src.models import (
    VIXIndicator,
    DXYIndicator,
    FearGreedIndicator,
    FedRatesIndicator,
    OilPricesIndicator,
)


@pytest.fixture
def sample_config():
    """Default configuration."""
    return {
        "multiplier_floor": 0.1,
        "multiplier_ceiling": 1.0,
        "default_multiplier": 1.0,
    }


@pytest.fixture
def normal_market_data():
    """Normal market conditions."""
    return {
        "vix": 20.0,
        "dxy": 103.0,
        "fear_greed": 50.0,
        "fed_rates": 4.5,
        "oil_prices": 80.0,
    }


@pytest.fixture
def risk_off_market_data():
    """Risk-off market conditions."""
    return {
        "vix": 35.0,  # Extreme fear
        "dxy": 107.0,  # Strong dollar
        "fear_greed": 25.0,  # Fear
        "fed_rates": 5.5,  # High rates
        "oil_prices": 95.0,  # Elevated
    }


@pytest.fixture
def risk_on_market_data():
    """Risk-on market conditions."""
    return {
        "vix": 12.0,  # Complacency
        "dxy": 100.5,  # Weak dollar
        "fear_greed": 85.0,  # Extreme greed
        "fed_rates": 3.5,  # Low rates
        "oil_prices": 70.0,  # Low
    }


@pytest.fixture
def panic_market_data():
    """Panic market conditions."""
    return {
        "vix": 45.0,  # Extreme fear
        "dxy": 108.5,  # Very strong dollar
        "fear_greed": 15.0,  # Extreme fear
        "fed_rates": 5.5,  # High rates
        "oil_prices": 110.0,  # Very high
    }


@pytest.fixture
def vix_indicator():
    """VIX indicator."""
    return VIXIndicator(
        value=25.0,
        change_pct=5.0,
        regime="FEAR",
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def dxy_indicator():
    """DXY indicator."""
    return DXYIndicator(
        value=105.0,
        change_pct=2.0,
        strength="STRONG",
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def fear_greed_indicator():
    """Fear & Greed indicator."""
    return FearGreedIndicator(
        value=40.0,
        classification="Fear",
        timestamp=datetime.now(timezone.utc),
        components={"momentum": 40, "volatility": 40},
    )


@pytest.fixture
def fed_rates_indicator():
    """Fed Rates indicator."""
    return FedRatesIndicator(
        current_rate=4.5,
        trend="STABLE",
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def oil_prices_indicator():
    """Oil prices indicator."""
    return OilPricesIndicator(
        price_usd=85.0,
        change_pct=2.5,
        trend="NEUTRAL",
        timestamp=datetime.now(timezone.utc),
    )
