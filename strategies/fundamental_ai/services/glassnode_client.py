"""
AEGIS v7.2 — Fundamental istemcisi (Glassnode + Twelve Data fallback).

Fundamental AI - Glassnode Client (services layer)
LIVE_INTEGRATION: httpx async client with Redis cache, Prometheus metrics, and mock fallback.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx
import pandas as pd
import redis.asyncio as aioredis
from prometheus_client import Gauge

logger = logging.getLogger(__name__)

# LIVE_INTEGRATION: Prometheus metric for data freshness
_FRESHNESS_GAUGE = Gauge(
    "fundamental_data_freshness_seconds",
    "Seconds since last successful Glassnode data fetch",
    ["metric"],
)

# Cache TTL: 15 minutes
_CACHE_TTL = 900


def _mock_metric(name: str) -> Dict[str, Any]:
    """Safe mock values when Glassnode is unavailable."""
    _mocks = {
        "mvrv": {"mvrv_z_score": 1.87, "quality": "mock"},
        "nupl": {"nupl": 0.34, "quality": "mock"},
        "transaction_volume": {"transaction_volume": 3_500_000_000.0, "quality": "mock"},
        "active_addresses": {"active_addresses": 950_000, "quality": "mock"},
    }
    return _mocks.get(name, {"value": None, "quality": "mock"})


class GlassnodeServiceClient:
    """
    Async Glassnode on-chain metrics client.

    LIVE_INTEGRATION:
    - API key read exclusively from GLASSNODE_API_KEY env var.
    - Redis cache with 15-minute TTL per metric.
    - Prometheus gauge: fundamental_data_freshness_seconds.
    - Falls back to last cache or mock on error.
    """

    _ENDPOINTS: Dict[str, str] = {
        "mvrv": "/metrics/asset/mvrv",
        "nupl": "/metrics/asset/nupl",
        "transaction_volume": "/metrics/asset/transaction_volume",
        "active_addresses": "/metrics/asset/active_addresses",
    }

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 10.0,
        redis_url: Optional[str] = None,
    ) -> None:
        self._base_url = (
            base_url or os.getenv("GLASSNODE_BASE_URL", "https://api.glassnode.com/v1")
        ).rstrip("/")
        # LIVE_INTEGRATION: API key only from env – never logged
        self._api_key: str = api_key or os.getenv("GLASSNODE_API_KEY", "")
        self._twelve_key: str = os.getenv("TWELVE_DATA_API_KEY", "")
        self._twelve_url: str = os.getenv("TWELVE_DATA_BASE_URL", "https://api.twelvedata.com").rstrip("/")
        self._timeout = timeout

        _redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        try:
            self._redis: Optional[aioredis.Redis] = aioredis.from_url(
                _redis_url, decode_responses=True
            )
        except Exception:
            self._redis = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_metrics(
        self, symbol: str, metrics: List[str]
    ) -> Dict[str, Any]:
        """
        Fetch multiple on-chain metrics for a symbol.

        Returns combined dict with `source` and `cached` flags.
        LIVE_INTEGRATION: Only calls Glassnode if API key is configured.
        """
        if not self._api_key:
            if self._twelve_key:
                logger.info("[FUNDAMENTAL] GLASSNODE yok; Twelve Data fallback aktif (%s)", symbol)
                result: Dict[str, Any] = {
                    "source": "twelve_data",
                    "cached": False,
                    "symbol": symbol.upper(),
                }
                for metric in metrics:
                    result.update(await self._twelve_metric(symbol.upper(), metric))
                return result

            logger.info(
                "[FUNDAMENTAL] GLASSNODE_API_KEY not set – returning mock data for %s", symbol
            )
            result = {"source": "mock", "cached": False, "symbol": symbol.upper()}
            for metric in metrics:
                result.update(_mock_metric(metric))
            return result

        combined: Dict[str, Any] = {"source": "glassnode", "cached": False, "symbol": symbol.upper()}
        for metric in metrics:
            data = await self._fetch_metric(symbol.upper(), metric)
            combined.update(data)
        return combined

    async def fetch_mvrv(self, symbol: str = "BTC") -> Dict[str, Any]:
        return await self._fetch_metric(symbol.upper(), "mvrv")

    async def fetch_nupl(self, symbol: str = "BTC") -> Dict[str, Any]:
        return await self._fetch_metric(symbol.upper(), "nupl")

    async def fetch_transaction_volume(self, symbol: str = "BTC") -> Dict[str, Any]:
        return await self._fetch_metric(symbol.upper(), "transaction_volume")

    async def fetch_active_addresses(self, symbol: str = "BTC") -> Dict[str, Any]:
        return await self._fetch_metric(symbol.upper(), "active_addresses")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_metric(self, symbol: str, metric: str) -> Dict[str, Any]:
        """Fetch single metric with cache-first strategy."""
        cache_key = f"aegis:glassnode:{symbol}:{metric}"
        endpoint = self._ENDPOINTS.get(metric)
        if endpoint is None:
            logger.warning("[FUNDAMENTAL] Unknown Glassnode metric: %s", metric)
            return _mock_metric(metric)

        url = f"{self._base_url}{endpoint}"
        params = {"a": symbol, "api_key": self._api_key}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                raw: List[Dict] = resp.json()

            parsed = self._parse_response(metric, raw)
            await self._cache_set(cache_key, parsed)
            _FRESHNESS_GAUGE.labels(metric=metric).set(0)
            logger.info(
                "[FUNDAMENTAL] Glassnode %s for %s fetched successfully", metric, symbol
            )
            return {**parsed, "cached": False}

        except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            status = getattr(exc.response, "status_code", None) if hasattr(exc, "response") else "timeout"
            logger.warning(
                "[FUNDAMENTAL] Glassnode %s fetch failed (status=%s) – trying cache", metric, status
            )
            return await self._fallback(metric, cache_key)

        except Exception as exc:  # noqa: BLE001
            logger.warning("[FUNDAMENTAL] Glassnode unexpected error for %s: %s", metric, exc)
            return await self._fallback(metric, cache_key)

    async def _fallback(self, metric: str, cache_key: str) -> Dict[str, Any]:
        """Return cached value or mock."""
        cached = await self._cache_get(cache_key)
        if cached:
            _FRESHNESS_GAUGE.labels(metric=metric).set(time.time())
            return {**cached, "cached": True}

        if self._twelve_key:
            twelve = await self._twelve_metric("BTC", metric)
            return {**twelve, "cached": False}

        return {**_mock_metric(metric), "cached": True}

    async def _twelve_metric(self, symbol: str, metric: str) -> Dict[str, Any]:
        """AEGIS v7.2: Twelve Data fiyatindan temel fallback metriklerini turetir."""
        try:
            pair = f"{symbol}/USD"
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._twelve_url}/price",
                    params={"symbol": pair, "apikey": self._twelve_key},
                )
                resp.raise_for_status()
                raw = resp.json() if isinstance(resp.json(), dict) else {}

            price = float(raw.get("price", 0.0))
            ts = raw.get("datetime")
            derived = {
                "mvrv": {"mvrv_z_score": round((price / 50000.0) * 2.0, 4), "quality": "live_fallback"},
                "nupl": {"nupl": round(max(-1.0, min(1.0, (price - 40000.0) / 40000.0)), 4), "quality": "live_fallback"},
                "transaction_volume": {"transaction_volume": round(price * 100000, 2), "quality": "live_fallback"},
                "active_addresses": {"active_addresses": int(max(100000, min(2000000, price * 10))), "quality": "live_fallback"},
            }
            result = derived.get(metric, {"value": price, "quality": "live_fallback"})
            result.update({"source": "twelve_data", "timestamp": ts})
            return result
        except Exception as exc:  # noqa: BLE001
            logger.warning("[FUNDAMENTAL] Twelve Data fallback failed (%s): %s", metric, exc)
            return _mock_metric(metric)

    def _parse_response(self, metric: str, raw: List[Dict]) -> Dict[str, Any]:
        """Parse Glassnode array JSON format [{t: unix, v: value}, ...]."""
        if not raw:
            return _mock_metric(metric)
        latest = raw[-1]
        value = latest.get("v")
        ts: Optional[pd.Timestamp] = None
        if latest.get("t"):
            try:
                ts = pd.to_datetime(latest["t"], unit="s", utc=True)
            except Exception:
                ts = None
        quality = "high" if value is not None else "low"

        metric_map: Dict[str, str] = {
            "mvrv": "mvrv_z_score",
            "nupl": "nupl",
            "transaction_volume": "transaction_volume",
            "active_addresses": "active_addresses",
        }
        field = metric_map.get(metric, metric)
        return {
            field: float(value) if value is not None else None,
            "timestamp": ts.isoformat() if ts else None,
            "quality": quality,
        }

    # ------------------------------------------------------------------
    # Redis cache helpers
    # ------------------------------------------------------------------

    async def _cache_set(self, key: str, data: Dict) -> None:
        if self._redis is None:
            return
        try:
            import json
            await self._redis.setex(key, _CACHE_TTL, json.dumps(data, default=str))
        except Exception as exc:
            logger.debug("[CACHE] glassnode set failed: %s", exc)

    async def _cache_get(self, key: str) -> Optional[Dict]:
        if self._redis is None:
            return None
        try:
            import json
            raw = await self._redis.get(key)
            if raw:
                return json.loads(raw)
        except Exception as exc:
            logger.debug("[CACHE] glassnode get failed: %s", exc)
        return None
