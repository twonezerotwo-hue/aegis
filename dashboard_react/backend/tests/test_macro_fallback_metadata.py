"""
Static tests for macro.py fallback metadata contract.
Tests the AEGIS v7.2 canonical provenance contract:
  - data_status: LIVE | PARTIAL_FALLBACK | FALLBACK
  - field_sources: {field: source_string}
  - fallback_fields / verified_fields
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routes import macro as macro_routes


class _FailingAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, *args, **kwargs):
        raise RuntimeError("sentinel down")

    async def post(self, *args, **kwargs):
        raise RuntimeError("sentinel down")


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _StaticAsyncClient:
    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, *args, **kwargs):
        return _Response(self._payload)


def _all_market_fallbacks() -> dict:
    """Return a fetch_market_data result where every market field is hardcoded fallback."""
    return {
        field: {
            "value": macro_routes._FALLBACK_METRICS[field],
            "source": "hardcoded_fallback",
            "timestamp": None,
            "verified": False,
            "fallback_used": True,
            "fallback_reason": "mocked_failure",
        }
        for field in macro_routes._MARKET_FIELDS
    }


def test_macro_fallback_metadata():
    """When all market sources AND sentinel fail, response must be full FALLBACK."""
    async def _mock_fetch():
        return _all_market_fallbacks()

    with patch.object(macro_routes, "fetch_market_data", _mock_fetch), \
         patch.object(macro_routes.httpx, "AsyncClient", _FailingAsyncClient):
        response = asyncio.run(macro_routes.get_macro_metrics("medium"))

    assert response["fallback_used"] is True
    assert response["verified"] is False
    assert response["live"] is False
    assert response["data_status"] == "FALLBACK"
    assert response["source"] == "all_hardcoded_fallback"
    assert response["warning"] is not None and "hardcoded" in response["warning"].lower()
    assert response["allocation_horizon"] == "medium"
    assert response["allocation_profile"] == "fallback_illustrative"
    assert "Illustrative allocation based on incomplete/fallback macro data." in response["warnings"]
    assert response["fallback_fields"] == sorted(macro_routes._ALL_FIELDS)
    assert response["verified_fields"] == []
    assert response["field_sources"]["dxy"] == "hardcoded_fallback"


def test_macro_partial_fallback_metadata():
    """When sentinel provides event fields but market data is all fallback → PARTIAL_FALLBACK."""
    payload = {
        "event_risk_score": 0.51,
        "hours_to_event": 12,
        "timestamp": "2026-05-01T10:15:00+00:00",
    }

    async def _mock_fetch():
        return _all_market_fallbacks()

    with patch.object(macro_routes, "fetch_market_data", _mock_fetch), \
         patch.object(
             macro_routes.httpx,
             "AsyncClient",
             lambda *args, **kwargs: _StaticAsyncClient(payload),
         ):
        response = asyncio.run(macro_routes.get_macro_metrics("medium"))

    assert response["fallback_used"] is True
    assert response["verified"] is False
    assert response["live"] is False
    assert response["data_status"] == "PARTIAL_FALLBACK"
    # source string must contain "partial_plus_fallback" for apiV2.ts isPartialFallbackSource
    assert "partial_plus_fallback" in response["source"]
    assert response["allocation_horizon"] == "medium"
    assert response["allocation_profile"] == "fallback_illustrative"
    assert "Illustrative allocation based on incomplete/fallback macro data." in response["warnings"]
    assert "fallback_fields" in response
    assert "dxy" in response["fallback_fields"]
    assert "event_risk_score" not in response["fallback_fields"]
    assert "sentinel" in response["field_sources"]["event_risk_score"]
    assert response["field_sources"]["dxy"].startswith("hardcoded_fallback")


def test_macro_exact_fallback_constant_cluster_is_marked_partial():
    """When sentinel responds (provides event fields) but all market data is fallback → PARTIAL_FALLBACK."""
    payload = {
        "event_risk_score": 0.3,
        "hours_to_event": 24,
        "timestamp": "2026-05-01T10:15:00+00:00",
        # macro_snapshot with market values is ignored — market data comes from yfinance/CoinGecko
        "macro_snapshot": {
            "dxy": 98.5,
            "vix": 22.0,
            "us10y": 4.25,
            "brent": 92.0,
            "xau": 4800.0,
            "btc_d": 59.8,
            "usdt_d": 7.5,
        },
    }

    async def _mock_fetch():
        return _all_market_fallbacks()

    with patch.object(macro_routes, "fetch_market_data", _mock_fetch), \
         patch.object(
             macro_routes.httpx,
             "AsyncClient",
             lambda *args, **kwargs: _StaticAsyncClient(payload),
         ):
        response = asyncio.run(macro_routes.get_macro_metrics("medium"))

    assert response["data_status"] == "PARTIAL_FALLBACK"
    assert response["verified"] is False
    assert response["live"] is False
    assert "partial_plus_fallback" in response["source"]
    assert "dxy" in response["fallback_fields"]
    assert response["field_sources"]["dxy"].startswith("hardcoded_fallback")
    assert "sentinel" in response["field_sources"]["event_risk_score"]
