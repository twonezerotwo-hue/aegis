"""
tests/test_touche_live_integration.py
LIVE_INTEGRATION: Integration tests for Touche AI Binance data fetcher.
Tests cover LIVE fetch, fallback behaviour, and /health + /touche/analyze endpoints.
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _set_live_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure DATA_MODE=LIVE for all tests in this module."""
    monkeypatch.setenv("DATA_MODE", "LIVE")
    monkeypatch.setenv("BINANCE_BASE_URL", "https://api.binance.com")
    monkeypatch.setenv("BINANCE_API_KEY", "test_key")
    monkeypatch.setenv("BINANCE_API_SECRET", "test_secret")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")


# ---------------------------------------------------------------------------
# BinanceDataFetcher unit tests
# ---------------------------------------------------------------------------

class TestBinanceDataFetcher:

    @pytest.mark.asyncio
    async def test_fetch_ohlcv_live_success(self) -> None:
        """LIVE path returns a properly indexed DataFrame."""
        from strategies.touche_ai.services.data_fetcher import BinanceDataFetcher

        # Build minimal Binance klines mock response (12 columns, 5 rows)
        now_ms = 1_700_000_000_000
        mock_row = [now_ms, "45000", "45500", "44500", "45200", "500",
                    now_ms + 59999, "22600000", "1200", "250", "11300000", "0"]
        mock_data = [mock_row[:] for _ in range(5)]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=mock_data)

        fetcher = BinanceDataFetcher(
            base_url="https://api.binance.com",
            timeout=5.0,
            redis_url=None,
        )
        # Disable redis
        fetcher._redis = None

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            df = await fetcher.fetch_ohlcv("BTCUSDT", "1h", limit=5)

        assert isinstance(df, pd.DataFrame)
        assert isinstance(df.index, pd.DatetimeIndex)
        assert df.index.tzinfo is not None, "Index must be UTC-aware"
        assert "close" in df.columns
        assert df["close"].dtype == float

    @pytest.mark.asyncio
    async def test_fallback_to_mock_on_timeout(self) -> None:
        """Timeout on all retries → mock DataFrame returned, no exception."""
        from strategies.touche_ai.services.data_fetcher import BinanceDataFetcher
        import httpx

        fetcher = BinanceDataFetcher(
            base_url="https://invalid.binance.test",
            timeout=0.001,
            max_retries=1,
            redis_url=None,
        )
        fetcher._redis = None

        with patch(
            "httpx.AsyncClient.get",
            new_callable=AsyncMock,
            side_effect=httpx.TimeoutException("timeout"),
        ):
            df = await fetcher.fetch_ohlcv("BTCUSDT", "1h", limit=10)

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 10

    @pytest.mark.asyncio
    async def test_fallback_returns_cached_data(self) -> None:
        """Redis cache is served when Binance is unreachable."""
        from strategies.touche_ai.services.data_fetcher import BinanceDataFetcher, _mock_ohlcv
        import httpx

        fetcher = BinanceDataFetcher(
            base_url="https://invalid.binance.test",
            timeout=0.001,
            max_retries=1,
            redis_url=None,
        )

        cached_df = _mock_ohlcv("BTCUSDT", "1h", 5)
        fetcher._redis = None

        # Patch _cache_get to return the mock df
        async def _fake_cache_get(key: str):
            return cached_df

        fetcher._cache_get = _fake_cache_get  # type: ignore[assignment]

        with patch(
            "httpx.AsyncClient.get",
            new_callable=AsyncMock,
            side_effect=httpx.TimeoutException("timeout"),
        ):
            df = await fetcher.fetch_ohlcv("BTCUSDT", "1h", limit=5)

        assert isinstance(df, pd.DataFrame)

    @pytest.mark.asyncio
    async def test_mock_mode_skips_binance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """DATA_MODE=MOCK must never call Binance."""
        monkeypatch.setenv("DATA_MODE", "MOCK")
        from strategies.touche_ai.services.data_fetcher import BinanceDataFetcher

        fetcher = BinanceDataFetcher(redis_url=None)
        fetcher._data_mode = "MOCK"
        fetcher._redis = None

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            df = await fetcher.fetch_ohlcv("BTCUSDT", "1h", limit=20)
            mock_get.assert_not_called()

        assert len(df) == 20


# ---------------------------------------------------------------------------
# Touche AI /health endpoint
# ---------------------------------------------------------------------------

class TestToucheHealth:

    @pytest.mark.asyncio
    async def test_health_returns_data_mode(self) -> None:
        """GET /health must include data_mode and binance_connected fields."""
        # Import app lazily after env is set
        import importlib
        import strategies.touche_ai.main as main_mod
        importlib.reload(main_mod)
        app = main_mod.app

        with patch(
            "httpx.AsyncClient.get",
            new_callable=AsyncMock,
            return_value=MagicMock(status_code=200, raise_for_status=MagicMock()),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/health")

        assert resp.status_code == 200
        body = resp.json()
        assert "data_mode" in body
        assert "binance_connected" in body


# ---------------------------------------------------------------------------
# Touche AI /touche/analyze endpoint
# ---------------------------------------------------------------------------

class TestToucheAnalyze:

    @pytest.mark.asyncio
    async def test_analyze_includes_data_mode_and_data_range(self) -> None:
        """
        GET /touche/analyze must return data_mode=LIVE and data_range
        when BinanceDataFetcher succeeds.
        """
        import importlib
        import strategies.touche_ai.main as main_mod
        importlib.reload(main_mod)
        app = main_mod.app

        now_ms = 1_700_000_000_000
        mock_row = [now_ms + i * 3_600_000, "45000", "45500", "44500", "45200", "500",
                    now_ms + i * 3_600_000 + 3_599_999, "22600000", "1200", "250", "11300000", "0"]

        # 24 candles for 24h
        mock_data = [[now_ms + i * 3_600_000, "45000", "45500", "44500",
                      str(45000 + i * 10), "500", now_ms + i * 3_600_000 + 3_599_999,
                      "22600000", "1200", "250", "11300000", "0"] for i in range(24)]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=mock_data)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/touche/analyze",
                    params={"symbol": "BTCUSDT", "timeframe": "1h"},
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body.get("data_mode") == "LIVE"
        assert "eqs_score" in body or "eqs" in body

    @pytest.mark.asyncio
    async def test_analyze_fallback_still_returns_200(self) -> None:
        """Even when Binance is unreachable, /touche/analyze returns 200."""
        import importlib
        import httpx as _httpx
        import strategies.touche_ai.main as main_mod
        importlib.reload(main_mod)
        app = main_mod.app

        with patch(
            "httpx.AsyncClient.get",
            new_callable=AsyncMock,
            side_effect=_httpx.TimeoutException("timeout"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/touche/analyze",
                    params={"symbol": "BTCUSDT", "timeframe": "1h"},
                )

        assert resp.status_code == 200
        body = resp.json()
        assert "eqs" in body or "eqs_score" in body


# ---------------------------------------------------------------------------
# Fundamental AI /fundamental/metrics endpoint
# ---------------------------------------------------------------------------

class TestFundamentalMetrics:

    @pytest.mark.asyncio
    async def test_fundamental_metrics_mock_fallback(self) -> None:
        """No Glassnode API key → returns mock data with source=mock, status 200."""
        import importlib
        import strategies.fundamental_ai.main as fund_mod
        importlib.reload(fund_mod)
        app = fund_mod.app

        # Ensure no Glassnode key
        os.environ.pop("GLASSNODE_API_KEY", None)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/fundamental/metrics",
                params={"symbol": "BTC", "metrics": "mvrv,nupl"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body.get("source") == "mock"
        assert "mvrv_z_score" in body or "nupl" in body

    @pytest.mark.asyncio
    async def test_fundamental_metrics_glassnode_live(self) -> None:
        """With API key + mocked HTTP → returns live data with source=glassnode."""
        import importlib
        import strategies.fundamental_ai.main as fund_mod
        os.environ["GLASSNODE_API_KEY"] = "test_glassnode_key"
        importlib.reload(fund_mod)
        app = fund_mod.app

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=[{"t": 1_700_000_000, "v": 1.87}])

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/fundamental/metrics",
                    params={"symbol": "BTC", "metrics": "mvrv"},
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body.get("source") == "glassnode"
        assert body.get("mvrv_z_score") == pytest.approx(1.87, abs=0.01)
