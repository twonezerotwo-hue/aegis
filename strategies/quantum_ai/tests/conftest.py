"""
Quantum AI Limited — Test Fixtures
"""
import pytest
from datetime import datetime, timezone

from strategies.quantum_ai.src.core.models import (
    Order,
    Position,
    Inventory,
    TwoSidedQuote,
    MMParameters,
    OrderSide,
    OrderType,
    OrderStatus,
)


@pytest.fixture
def sample_config():
    """Default MM configuration (as dict for general use)."""
    return {
        "gamma": 0.075,
        "order_arrival_lambda": 10.0,
        "min_spread_bps": 0.5,
        "max_spread_bps": 10.0,
        "max_inventory": 1000.0,
        "portfolio_value": 100000.0,
        "lookback_days": 30,
    }


@pytest.fixture
def mm_params():
    """Default MM parameters (Pydantic model)."""
    return MMParameters(
        gamma=0.075,
        inventory_target=0.0,
        order_arrival_lambda=10.0,
        time_horizon=60.0,
        min_spread_bps=0.5,
        max_spread_bps=10.0,
    )


@pytest.fixture
def btcusdt_market_data():
    """Sample BTCUSDT market data."""
    return {
        "symbol": "BTCUSDT",
        "mid_price": 50000.0,
        "volatility": 0.02,
        "bid": 49950.0,
        "ask": 50050.0,
        "time_to_expiry": 1.0,
        "fill_rate": 0.6,
        "timestamp": datetime.now(timezone.utc),
    }


@pytest.fixture
def ethusdt_market_data():
    """Sample ETHUSDT market data."""
    return {
        "symbol": "ETHUSDT",
        "mid_price": 3000.0,
        "volatility": 0.025,
        "bid": 2995.0,
        "ask": 3005.0,
        "time_to_expiry": 1.0,
        "fill_rate": 0.55,
        "timestamp": datetime.now(timezone.utc),
    }


@pytest.fixture
def sample_order():
    """Sample trading order."""
    return Order(
        order_id="ORDER_001",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        price=50000.0,
        quantity=0.1,
        order_type=OrderType.LIMIT,
        status=OrderStatus.PENDING,
        exchange="binance",
    )


@pytest.fixture
def sample_position():
    """Sample portfolio position."""
    return Position(
        symbol="BTCUSDT",
        size=0.5,
        entry_price=48000.0,
        current_price=50000.0,
        unrealized_pnl=500.0,
        unrealized_pnl_percent=0.02,
    )


@pytest.fixture
def sample_inventory():
    """Sample inventory state."""
    return Inventory(
        symbol="BTCUSDT",
        quantity=10.0,
        total_value=500000.0,
        inventory_risk=0.05,
        skew_ratio=0.3,
    )


@pytest.fixture
def sample_two_sided_quote():
    """Sample two-sided quote."""
    return TwoSidedQuote(
        symbol="BTCUSDT",
        bid_price=49975.0,
        ask_price=50025.0,
        bid_qty=0.5,
        ask_qty=0.5,
        mid_price=50000.0,
        spread_bps=5.0,
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def portfolio_state():
    """Portfolio state for testing."""
    return {
        "portfolio_value": 100000.0,
        "cash_reserve": 20000.0,
        "total_exposure": 80000.0,
        "daily_returns": [0.001, -0.002, 0.0015, -0.001, 0.003],
        "positions": {
            "BTCUSDT": {
                "size": 0.5,
                "price": 50000.0,
                "delta": 0.8,
            },
            "ETHUSDT": {
                "size": 5.0,
                "price": 3000.0,
                "delta": 0.6,
            },
        },
    }


@pytest.fixture
def exchange_prices():
    """Multi-exchange prices for arbitrage testing."""
    return {
        "binance": 50000.0,
        "coinbase": 50100.0,
        "kraken": 49950.0,
    }


@pytest.fixture
def funding_rate_data():
    """Funding rate data for testing."""
    return {
        "BTCUSDT": {
            "perpetual_rate": 0.0001,  # 0.01%
            "spot_price": 50000.0,
            "perpetual_price": 50050.0,
            "funding_interval": 28800,  # 8 hours
        },
        "ETHUSDT": {
            "perpetual_rate": 0.00008,
            "spot_price": 3000.0,
            "perpetual_price": 3010.0,
            "funding_interval": 28800,
        },
    }


@pytest.fixture
def historical_returns():
    """Historical returns for VAR calculation."""
    return [
        0.002, -0.001, 0.003, -0.0015, 0.0025,
        -0.002, 0.0018, -0.0012, 0.0035, -0.0008,
        0.001, -0.003, 0.0022, -0.0018, 0.0028,
    ]
