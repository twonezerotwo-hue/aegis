"""
Touche AI - Binance Data Fetcher
LIVE_INTEGRATION: httpx async client with rate limiting, Redis cache fallback, and mock fallback.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx
import pandas as pd
import redis.asyncio as aioredis


logger = logging.getLogger(__name__)

# LIVE_INTEGRATION: Standard OHLCV column names per Binance klines response
_KLINE_COLUMNS = [
    "timestamp", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades", "taker_buy_base",
    "taker_buy_quote", "ignore",
]

_NUMERIC_COLS = ["open", "high", "low", "close", "volume",
                 "quote_volume", "taker_buy_base", "taker_buy_quote"]


def _mock_ohlcv(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    """Deterministic mock OHLCV – used only as last-resort fallback."""
    import random
    rng = random.Random(abs(hash(symbol + interval)) + 42)
    base = 45000.0 if symbol.upper().startswith("BTC") else 3000.0
    now_ms = int(time.time() * 1000)
    rows = []
    price = base
    for i in range(limit):
        price = max(1.0, price * (1 + rng.uniform(-0.003, 0.003)))
        ts = now_ms - (limit - i) * 60_000
        rows.append({
            "timestamp": pd.Timestamp(ts, unit="ms", tz="UTC"),
            "open": price, "high": price * 1.001, "low": price * 0.999,
            "close": price, "volume": rng.uniform(500, 3000),
            "close_time": ts + 59999, "quote_volume": price * rng.uniform(500, 3000),
            "trades": int(rng.uniform(100, 500)),
            "taker_buy_base": rng.uniform(250, 1500),
            "taker_buy_quote": price * rng.uniform(250, 1500),
            "ignore": 0,
        })
    df = pd.DataFrame(rows)
    df[_NUMERIC_COLS] = df[_NUMERIC_COLS].astype(float)
    return df.set_index("timestamp")


class BinanceDataFetcher:
    """
    Async Binance REST data fetcher.

    - LIVE_INTEGRATION: Uses httpx.AsyncClient with configurable timeout and retry.
    - Rate limited via asyncio.Semaphore (max 10 concurrent requests).
    - Falls back to Redis cache (1h TTL) on API error, then to mock data.
    """

    # LIVE_INTEGRATION: Binance klines column names
    COLUMNS = _KLINE_COLUMNS

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        timeout: float = 5.0,
        max_retries: int = 3,
        redis_url: Optional[str] = None,
        cache_ttl: int = 3600,
    ) -> None:
        self._base_url = (base_url or os.getenv("BINANCE_BASE_URL", "https://api.binance.com")).rstrip("/")
        # LIVE_INTEGRATION: API key read only from env/config, never hard-coded
        _key = api_key or os.getenv("BINANCE_API_KEY", "")
        _secret = secret_key or os.getenv("BINANCE_API_SECRET", "")
        self._headers: Dict[str, str] = {}
        if _key:
            self._headers["X-MBX-APIKEY"] = _key
        # secret is kept for signed endpoints but not logged
        self._secret = _secret

        self._timeout = timeout
        self._max_retries = max_retries
        self._semaphore = asyncio.Semaphore(10)  # LIVE_INTEGRATION: rate limiter

        self._cache_ttl = cache_ttl
        _redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        try:
            self._redis: Optional[aioredis.Redis] = aioredis.from_url(_redis_url, decode_responses=True)
        except Exception:
            self._redis = None

        self._data_mode = os.getenv("DATA_MODE", "MOCK").upper()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_ohlcv(
        self, symbol: str, interval: str = "1h", limit: int = 100
    ) -> pd.DataFrame:
        """
        Fetch OHLCV candles.

        LIVE_INTEGRATION: Switches on DATA_MODE env var.
        Returns DataFrame indexed by UTC timestamp.
        """
        if self._data_mode == "LIVE":
            return await self._fetch_binance_live(symbol.upper(), interval, limit)
        return _mock_ohlcv(symbol.upper(), interval, limit)

    async def fetch_ticker_24h(self, symbol: str) -> Dict[str, Any]:
        """Fetch 24h ticker statistics."""
        if self._data_mode != "LIVE":
            return {"symbol": symbol.upper(), "source": "mock"}
        url = f"{self._base_url}/api/v3/ticker/24hr"
        raw = await self._get(url, {"symbol": symbol.upper()})
        return raw if isinstance(raw, dict) else {}

    async def fetch_order_book(self, symbol: str, limit: int = 100) -> Dict[str, Any]:
        """Fetch order book depth."""
        if self._data_mode != "LIVE":
            return {"bids": [], "asks": [], "source": "mock"}
        url = f"{self._base_url}/api/v3/depth"
        raw = await self._get(url, {"symbol": symbol.upper(), "limit": limit})
        return raw if isinstance(raw, dict) else {}

    async def fetch_recent_trades(self, symbol: str, limit: int = 50) -> List[Dict]:
        """Fetch recent trades."""
        if self._data_mode != "LIVE":
            return []
        url = f"{self._base_url}/api/v3/trades"
        raw = await self._get(url, {"symbol": symbol.upper(), "limit": limit})
        return raw if isinstance(raw, list) else []

    def get_data_mode(self) -> str:
        return self._data_mode

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_binance_live(
        self, symbol: str, interval: str, limit: int
    ) -> pd.DataFrame:
        """
        LIVE_INTEGRATION: Core Binance klines fetch with retry + cache fallback.
        """
        cache_key = f"aegis:ohlcv:{symbol}:{interval}:{limit}"
        url = f"{self._base_url}/api/v3/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}

        for attempt in range(1, self._max_retries + 1):
            try:
                async with self._semaphore:
                    async with httpx.AsyncClient(
                        headers=self._headers,
                        timeout=self._timeout,
                    ) as client:
                        resp = await client.get(url, params=params)
                        resp.raise_for_status()
                        data: List[List] = resp.json()

                df = pd.DataFrame(data, columns=self.COLUMNS)
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
                df[_NUMERIC_COLS] = df[_NUMERIC_COLS].astype(float)
                df = df.set_index("timestamp")

                # Persist to cache on success
                await self._cache_set(cache_key, df)
                logger.info(
                    "[DATA] Mode=%s, Source=Binance, Symbol=%s, Interval=%s, Rows=%d",
                    self._data_mode, symbol, interval, len(df),
                )
                return df

            except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                status = getattr(exc.response, "status_code", None) if hasattr(exc, "response") else None
                log_status = status or "timeout"
                logger.warning(
                    "[DATA] Binance attempt %d/%d failed for %s: %s (status=%s)",
                    attempt, self._max_retries, symbol, type(exc).__name__, log_status,
                )
                if attempt == self._max_retries:
                    return await self._fallback(symbol, interval, limit, cache_key)
                await asyncio.sleep(0.5 * attempt)

            except Exception as exc:  # noqa: BLE001
                logger.warning("[DATA] Unexpected error fetching %s: %s", symbol, exc)
                if attempt == self._max_retries:
                    return await self._fallback(symbol, interval, limit, cache_key)
                await asyncio.sleep(0.5 * attempt)

        return await self._fallback(symbol, interval, limit, cache_key)  # pragma: no cover

    async def _fallback(
        self, symbol: str, interval: str, limit: int, cache_key: str
    ) -> pd.DataFrame:
        """
        LIVE_INTEGRATION: Fallback chain: Redis cache → safe mock.
        Logs BINANCE_FALLBACK warning in all cases.
        """
        # Try Redis cache first
        cached = await self._cache_get(cache_key)
        if cached is not None:
            logger.warning("[DATA] Fallback activated for %s – serving Redis cache", symbol)
            logger.warning("BINANCE_FALLBACK: Using safe defaults")
            return cached

        # Last resort: mock data
        logger.warning("[DATA] Fallback activated for %s – serving mock data (no cache)", symbol)
        logger.warning("BINANCE_FALLBACK: Using safe defaults")
        return _mock_ohlcv(symbol, interval, limit)

    async def _get(self, url: str, params: Dict) -> Any:
        """Generic GET with semaphore guard."""
        async with self._semaphore:
            async with httpx.AsyncClient(
                headers=self._headers,
                timeout=self._timeout,
            ) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()

    # ------------------------------------------------------------------
    # Redis cache helpers
    # ------------------------------------------------------------------

    async def _cache_set(self, key: str, df: pd.DataFrame) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.setex(key, self._cache_ttl, df.to_json())
        except Exception as exc:
            logger.debug("[CACHE] set failed: %s", exc)

    async def _cache_get(self, key: str) -> Optional[pd.DataFrame]:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
            if raw:
                df = pd.read_json(raw)
                if "timestamp" in df.columns:
                    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
                    df = df.set_index("timestamp")
                elif not isinstance(df.index, pd.DatetimeIndex):
                    df.index = pd.to_datetime(df.index, utc=True, errors="coerce")
                return df
        except Exception as exc:
            logger.debug("[CACHE] get failed: %s", exc)
        return None
