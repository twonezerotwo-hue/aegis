"""
Touche AI - Binance Data Fetcher
LIVE_INTEGRATION: httpx async client with rate limiting and real-data cache fallback.
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

_KLINE_COLUMNS = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trades",
    "taker_buy_base",
    "taker_buy_quote",
    "ignore",
]

_NUMERIC_COLS = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "taker_buy_base",
    "taker_buy_quote",
]


def _mock_ohlcv(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    """Explicit opt-in mock path kept only for controlled local development."""
    import random

    rng = random.Random(abs(hash(symbol + interval)) + 42)
    base = 45000.0 if symbol.upper().startswith("BTC") else 3000.0
    now_ms = int(time.time() * 1000)
    rows = []
    price = base
    for i in range(limit):
        price = max(1.0, price * (1 + rng.uniform(-0.003, 0.003)))
        ts = now_ms - (limit - i) * 60_000
        rows.append(
            {
                "timestamp": pd.Timestamp(ts, unit="ms", tz="UTC"),
                "open": price,
                "high": price * 1.001,
                "low": price * 0.999,
                "close": price,
                "volume": rng.uniform(500, 3000),
                "close_time": ts + 59999,
                "quote_volume": price * rng.uniform(500, 3000),
                "trades": int(rng.uniform(100, 500)),
                "taker_buy_base": rng.uniform(250, 1500),
                "taker_buy_quote": price * rng.uniform(250, 1500),
                "ignore": 0,
            }
        )
    df = pd.DataFrame(rows)
    df[_NUMERIC_COLS] = df[_NUMERIC_COLS].astype(float)
    return df.set_index("timestamp")


class DataUnavailableError(RuntimeError):
    """Raised when no live or cached market data is available."""


class BinanceDataFetcher:
    """
    Async Binance REST data fetcher.

    - Uses public Binance market-data endpoints.
    - Falls back to Redis-cached real data on live API failure.
    - Mock data is disabled by default and requires ALLOW_MOCK_DATA=true.
    """

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
        api_key_value = api_key or os.getenv("BINANCE_API_KEY", "")
        self._secret = secret_key or os.getenv("BINANCE_API_SECRET", "")
        self._headers: Dict[str, str] = {}
        if api_key_value:
            self._headers["X-MBX-APIKEY"] = api_key_value

        self._timeout = timeout
        self._max_retries = max_retries
        self._semaphore = asyncio.Semaphore(10)
        self._cache_ttl = cache_ttl
        self._data_mode = os.getenv("DATA_MODE", "LIVE").upper()
        self._allow_mock = os.getenv("ALLOW_MOCK_DATA", "false").lower() == "true"
        self._last_fetch_meta: Dict[str, Any] = {
            "source": "uninitialized",
            "timestamp": None,
            "verified": False,
            "fallback_used": False,
            "cached": False,
            "data_status": "UNKNOWN",
            "warning": "No market data fetched yet.",
        }

        redis_target = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        try:
            self._redis: Optional[aioredis.Redis] = aioredis.from_url(redis_target, decode_responses=True)
        except Exception:
            self._redis = None

    # Binance'de olmayan emtia sembollerinin yfinance karşılıkları
    # XAG/XAU Binance spot'ta yok; yfinance vadeli kontrat verisi kullanılır
    _YFINANCE_SYMBOL_MAP: Dict[str, str] = {
        "XAGUSDT": "SI=F",   # Gümüş (Silver Futures)
        "XAUUSDT": "GC=F",   # Altın (Gold Futures)
        "WTIUSDT": "CL=F",   # Ham Petrol (WTI Crude)
        "BRENTUSDT": "BZ=F", # Brent Petrol
    }

    # yfinance interval → Binance interval dönüşümü
    _YF_INTERVAL_MAP: Dict[str, str] = {
        "1m": "1m", "3m": "5m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "60m", "2h": "60m", "4h": "1d", "6h": "1d", "8h": "1d",
        "12h": "1d", "1d": "1d", "3d": "1wk", "1w": "1wk", "1M": "1mo",
    }

    async def fetch_ohlcv(self, symbol: str, interval: str = "1h", limit: int = 100) -> pd.DataFrame:
        """
        Fetch OHLCV candles.

        Modes:
        - LIVE: Binance önce, başarısız olursa yfinance (XAG/XAU için)
        - CACHE_ONLY: sadece Redis cache
        """
        normalized_symbol = symbol.upper().strip()
        normalized_mode = self._data_mode.upper()
        cache_key = f"aegis:ohlcv:{normalized_symbol}:{interval}:{limit}"

        if normalized_mode == "CACHE_ONLY":
            cached = await self._cache_get(cache_key)
            if cached is not None:
                self._remember_meta("redis_cache", cached, verified=True, cached=True, data_status="RECENT")
                return cached
            raise DataUnavailableError(f"No cached OHLCV data available for {normalized_symbol} {interval}")

        try:
            return await self._fetch_binance_live(normalized_symbol, interval, limit, cache_key)
        except DataUnavailableError:
            # ── yfinance fallback: Binance'de olmayan emtialar ─────────────
            yf_ticker = self._YFINANCE_SYMBOL_MAP.get(normalized_symbol)
            if yf_ticker:
                try:
                    df = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self._fetch_yfinance(yf_ticker, interval, limit),
                    )
                    self._last_fetch_meta = {
                        "source": f"yfinance_{yf_ticker}",
                        "timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
                        "verified": True,
                        "fallback_used": True,
                        "cached": False,
                        "data_status": "LIVE",
                        "warning": f"Binance'de spot çifti yok; yfinance ({yf_ticker}) kullanıldı.",
                    }
                    return df
                except Exception as yf_exc:
                    logger.warning("yfinance fallback failed for %s (%s): %s",
                                   normalized_symbol, yf_ticker, yf_exc)

            if self._allow_mock:
                self._last_fetch_meta = {
                    "source": "explicit_mock_opt_in",
                    "timestamp": None,
                    "verified": False,
                    "fallback_used": True,
                    "cached": False,
                    "data_status": "MOCK",
                    "warning": "Mock OHLCV used because ALLOW_MOCK_DATA=true.",
                }
                return _mock_ohlcv(normalized_symbol, interval, limit)
            raise

    def _fetch_yfinance(self, yf_ticker: str, binance_interval: str, limit: int) -> pd.DataFrame:
        """
        yfinance'ten OHLCV verisi çek ve Binance formatına dönüştür.
        Bloklanabilir (executor içinde çalışmalı).
        """
        import yfinance as yf

        yf_interval = self._YF_INTERVAL_MAP.get(binance_interval, "1d")

        # yfinance period: limit bar için yeterli süreyi hesapla
        if yf_interval in ("1m",):
            period = "7d"
        elif yf_interval in ("5m", "15m", "30m"):
            period = "60d"
        elif yf_interval in ("60m",):
            period = "730d"
        else:
            period = "max"

        hist = yf.Ticker(yf_ticker).history(period=period, interval=yf_interval)
        if hist.empty:
            raise DataUnavailableError(f"yfinance returned empty data for {yf_ticker}")

        hist = hist.tail(limit).copy()
        hist.index = hist.index.tz_localize("UTC") if hist.index.tzinfo is None else hist.index.tz_convert("UTC")

        df = pd.DataFrame({
            "open":         hist["Open"].astype(float),
            "high":         hist["High"].astype(float),
            "low":          hist["Low"].astype(float),
            "close":        hist["Close"].astype(float),
            "volume":       hist["Volume"].astype(float),
            "close_time":   0,
            "quote_volume": 0.0,
            "trades":       0,
            "taker_buy_base":  0.0,
            "taker_buy_quote": 0.0,
            "ignore":       0,
        }, index=hist.index)
        df.index.name = "timestamp"
        return df

    async def fetch_ticker_24h(self, symbol: str) -> Dict[str, Any]:
        """Fetch 24h ticker statistics from Binance public REST."""
        raw = await self._get(f"{self._base_url}/api/v3/ticker/24hr", {"symbol": symbol.upper().strip()})
        if not isinstance(raw, dict):
            raise DataUnavailableError(f"Ticker 24h unavailable for {symbol.upper().strip()}")
        raw.setdefault("source", "binance_public")
        raw.setdefault("verified", True)
        raw.setdefault("fallback_used", False)
        raw.setdefault("data_status", "LIVE")
        return raw

    async def fetch_order_book(self, symbol: str, limit: int = 100) -> Dict[str, Any]:
        """Fetch order book depth from Binance public REST."""
        raw = await self._get(
            f"{self._base_url}/api/v3/depth",
            {"symbol": symbol.upper().strip(), "limit": limit},
        )
        if not isinstance(raw, dict):
            raise DataUnavailableError(f"Order book unavailable for {symbol.upper().strip()}")
        raw.setdefault("source", "binance_public")
        raw.setdefault("verified", True)
        raw.setdefault("fallback_used", False)
        raw.setdefault("data_status", "LIVE")
        return raw

    async def fetch_recent_trades(self, symbol: str, limit: int = 50) -> List[Dict]:
        """Fetch recent trades from Binance public REST."""
        raw = await self._get(
            f"{self._base_url}/api/v3/trades",
            {"symbol": symbol.upper().strip(), "limit": limit},
        )
        if not isinstance(raw, list):
            raise DataUnavailableError(f"Recent trades unavailable for {symbol.upper().strip()}")
        return raw

    def get_data_mode(self) -> str:
        return self._data_mode

    def get_last_fetch_meta(self) -> Dict[str, Any]:
        return dict(self._last_fetch_meta)

    async def _fetch_binance_live(self, symbol: str, interval: str, limit: int, cache_key: str) -> pd.DataFrame:
        url = f"{self._base_url}/api/v3/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}

        for attempt in range(1, self._max_retries + 1):
            try:
                async with self._semaphore:
                    async with httpx.AsyncClient(headers=self._headers, timeout=self._timeout) as client:
                        resp = await client.get(url, params=params)
                        resp.raise_for_status()
                        data: List[List] = resp.json()

                df = pd.DataFrame(data, columns=self.COLUMNS)
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
                df[_NUMERIC_COLS] = df[_NUMERIC_COLS].astype(float)
                df = df.set_index("timestamp")

                await self._cache_set(cache_key, df)
                self._remember_meta("binance_public", df, verified=True, cached=False, data_status="LIVE")
                logger.info(
                    "[DATA] Mode=%s Source=Binance Symbol=%s Interval=%s Rows=%d",
                    self._data_mode,
                    symbol,
                    interval,
                    len(df),
                )
                return df
            except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                status = getattr(exc.response, "status_code", None) if hasattr(exc, "response") else None
                logger.warning(
                    "[DATA] Binance attempt %d/%d failed for %s (%s)",
                    attempt,
                    self._max_retries,
                    symbol,
                    status or type(exc).__name__,
                )
                if attempt == self._max_retries:
                    return await self._fallback(symbol, interval, cache_key)
                await asyncio.sleep(0.5 * attempt)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[DATA] Unexpected error fetching %s %s: %s", symbol, interval, exc)
                if attempt == self._max_retries:
                    return await self._fallback(symbol, interval, cache_key)
                await asyncio.sleep(0.5 * attempt)

        return await self._fallback(symbol, interval, cache_key)

    async def _fallback(self, symbol: str, interval: str, cache_key: str) -> pd.DataFrame:
        cached = await self._cache_get(cache_key)
        if cached is not None:
            logger.warning("[DATA] Live fetch failed for %s %s - serving Redis cache", symbol, interval)
            self._remember_meta("redis_cache", cached, verified=True, cached=True, data_status="RECENT")
            return cached

        self._last_fetch_meta = {
            "source": "binance_unavailable",
            "timestamp": None,
            "verified": False,
            "fallback_used": False,
            "cached": False,
            "data_status": "MISSING",
            "warning": f"Live Binance OHLCV unavailable for {symbol} {interval} and cache miss.",
        }
        raise DataUnavailableError(f"Live Binance OHLCV unavailable for {symbol} {interval}")

    async def _get(self, url: str, params: Dict[str, Any]) -> Any:
        async with self._semaphore:
            async with httpx.AsyncClient(headers=self._headers, timeout=self._timeout) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()

    def _remember_meta(
        self,
        source: str,
        df: pd.DataFrame,
        *,
        verified: bool,
        cached: bool,
        data_status: str,
    ) -> None:
        timestamp = df.index[-1].isoformat() if len(df.index) else None
        self._last_fetch_meta = {
            "source": source,
            "timestamp": timestamp,
            "verified": verified,
            "fallback_used": False,
            "cached": cached,
            "data_status": data_status,
            "warning": None,
        }

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
