# AEGIS v6.0 - Quantum AI Futures Extension | Purpose: Pydantic schemas for Binance futures data.
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class QuantumFuturesData(BaseModel):
    symbol: str = Field(default="BTCUSDT")
    funding_rate: float = Field(default=0.0)
    funding_rate_pct: float = Field(default=0.0)
    open_interest_usdt: float = Field(default=0.0)
    long_short_ratio: float = Field(default=1.0)
    futures_signal: str = Field(default="NEUTRAL")
    modifier: float = Field(default=1.0)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))


class QuantumFuturesFallback(QuantumFuturesData):
    futures_signal: str = Field(default="CACHE_FALLBACK")
