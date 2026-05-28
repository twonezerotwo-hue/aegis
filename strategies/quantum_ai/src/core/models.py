"""
Quantum AI Limited — Data Models

Pydantic models for type-safe data structures.
"""
from typing import Any, Dict, List
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict


# ─── Enums ───────────────────────────────────────────────────────────────────

class OrderSide(str, Enum):
    """Order side enumeration."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order type enumeration."""
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP = "STOP"
    TRAILING_STOP = "TRAILING_STOP"


class OrderStatus(str, Enum):
    """Order status enumeration."""
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"


class ArbitrageType(str, Enum):
    """Arbitrage type enumeration."""
    CROSS_EXCHANGE = "CROSS_EXCHANGE"
    FUNDING_RATE = "FUNDING_RATE"
    CALENDAR_SPREAD = "CALENDAR_SPREAD"
    TRIANGULAR = "TRIANGULAR"


# ─── Order Models ────────────────────────────────────────────────────────────

class Order(BaseModel):
    """Single order model."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    price: float
    quantity: float
    status: OrderStatus
    filled_qty: float = 0.0
    filled_price: float = 0.0
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    exchange: str = "binance"
    
    metadata: Dict[str, Any] = {}


class QuoteLevel(BaseModel):
    """Single quote level (bid/ask pair)."""
    price: float
    quantity: float
    level: int


class TwoSidedQuote(BaseModel):
    """Two-sided market quote."""
    symbol: str
    bid_price: float
    ask_price: float
    bid_qty: float
    ask_qty: float
    mid_price: float
    spread_bps: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ─── Market Data Models ──────────────────────────────────────────────────────

class MarketSnapshot(BaseModel):
    """Market snapshot at a point in time."""
    symbol: str
    timestamp: datetime
    
    mid_price: float
    bid_price: float
    ask_price: float
    bid_qty: float
    ask_qty: float
    
    last_trade_price: float
    last_trade_qty: float
    
    volatility_1h: float
    volatility_24h: float
    
    volume_24h: float
    vwap_24h: float


# ─── Position Models ────────────────────────────────────────────────────────

class Position(BaseModel):
    """Trading position."""
    symbol: str
    quantity: float
    avg_entry_price: float
    current_price: float
    
    @property
    def mark_to_market(self) -> float:
        """Mark-to-market value."""
        return self.quantity * self.current_price
    
    @property
    def unrealized_pnl(self) -> float:
        """Unrealized P&L."""
        return (self.current_price - self.avg_entry_price) * self.quantity


class Inventory(BaseModel):
    """Inventory state."""
    positions: Dict[str, Position]
    total_value: float
    net_position: float
    gross_position: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ─── Arbitrage Models ───────────────────────────────────────────────────────

class ArbOpportunity(BaseModel):
    """Arbitrage opportunity."""
    arb_type: ArbitrageType
    symbol: str
    
    # Legs
    leg_a_exchange: str
    leg_a_price: float
    leg_b_exchange: str
    leg_b_price: float
    
    # Spread
    spread_bps: float
    spread_pct: float
    
    # Profitability
    gross_pnl: float
    fee_cost: float
    net_pnl: float
    
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ─── Risk Models ────────────────────────────────────────────────────────────

class RiskMetrics(BaseModel):
    """Risk metrics snapshot."""
    timestamp: datetime
    
    # Position risk
    net_position: float
    gross_position: float
    max_position_value: float
    
    # Market risk
    volatility: float
    value_at_risk: float  # 95% 1-day VaR
    expected_shortfall: float
    
    # Daily limits
    daily_pnl: float
    daily_loss: float
    daily_trades: int
    daily_volume: float
    
    # Status
    risk_limit_breached: bool = False
    warnings: List[str] = []


# ─── Performance Models ──────────────────────────────────────────────────────

class StrategyPerformance(BaseModel):
    """Strategy performance metrics."""
    timestamp: datetime
    
    # Returns
    pnl: float
    pnl_pct: float
    
    # Statistics
    realized_pnl: float
    unrealized_pnl: float
    fees_paid: float
    
    # Ratios
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    
    # Trade statistics
    trades_total: int
    trades_winning: int
    avg_fill_rate: float
    
    metadata: Dict[str, Any] = {}


# ─── Configuration Models ───────────────────────────────────────────────────

class MMParameters(BaseModel):
    """Market Making parameters."""
    gamma: float = 0.075
    inventory_target: float = 0.0
    order_arrival_lambda: float = 10.0
    time_horizon: float = 60.0
    min_spread_bps: float = 0.5
    max_spread_bps: float = 10.0


class InstrumentConfig(BaseModel):
    """Instrument configuration."""
    symbol: str
    type: str = "spot"
    enabled: bool = True
    
    tick_size: float
    lot_size: float
    min_order_size: float
    max_order_size: float
    
    maker_fee_bps: float
    taker_fee_bps: float
    
    volatility_annual_pct: float
    priority: int = 1
