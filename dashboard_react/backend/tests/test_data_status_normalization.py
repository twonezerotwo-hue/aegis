from __future__ import annotations

from pathlib import Path
import sys
import asyncio


ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = ROOT / "dashboard_react" / "backend"

for path in (ROOT, BACKEND_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from routes import dashboard as dashboard_routes  # noqa: E402


def test_news_payload_uses_nested_signal_timestamp():
    payload = {
        "signals": [
            {"timestamp": "2026-06-01T08:46:07.825740Z"},
        ]
    }

    assert dashboard_routes._extract_payload_timestamp(payload, "news") == "2026-06-01T08:46:07.825740Z"


def test_fundamental_mock_payload_is_marked_mock_and_excluded_from_live_scores():
    payload = {
        "source": "glassnode",
        "quality": "mock",
        "nupl": 0.34,
        "mvrv_z_score": 1.87,
    }

    assert dashboard_routes._payload_data_status(payload, "fundamental", "1h") == "MOCK"
    scores = dashboard_routes._extract_live_scores({"fundamental": payload}, "1h")
    assert scores["fundamental"] is None


def test_touche_live_mode_no_longer_falls_back_to_unknown():
    payload = {
        "source": "touche-ai",
        "data_mode": "LIVE",
        "fallback_used": False,
        "tf_signals": {"1h": "NEUTRAL"},
    }

    assert dashboard_routes._payload_data_status(payload, "touche", "1h") == "LIVE"


def test_partial_fallback_beats_unknown_in_consensus_aggregation():
    aggregated = dashboard_routes._aggregate_status(["UNKNOWN", "PARTIAL_FALLBACK"])
    assert aggregated == "PARTIAL_FALLBACK"


def test_macro_asset_scoring_prefers_live_market_and_configured_sentinel(monkeypatch):
    async def fake_fetch_market_data():
        return {
            "dxy": {"value": 99.0, "source": "yfinance:DX-Y.NYB", "timestamp": "2026-06-01T00:00:00+00:00", "fallback_used": False},
            "vix": {"value": 15.8, "source": "yfinance:^VIX", "timestamp": "2026-06-01T00:00:00+00:00", "fallback_used": False},
            "us10y": {"value": 4.45, "source": "yfinance:^TNX", "timestamp": "2026-06-01T00:00:00+00:00", "fallback_used": False},
            "brent": {"value": 94.1, "source": "yfinance:BZ=F", "timestamp": "2026-06-01T00:00:00+00:00", "fallback_used": False},
            "xau": {"value": 4536.0, "source": "yfinance:GC=F", "timestamp": "2026-06-01T00:00:00+00:00", "fallback_used": False},
            "hg": {"value": 6.54, "source": "yfinance:HG=F", "timestamp": "2026-06-01T00:00:00+00:00", "fallback_used": False},
        }

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "timestamp": "2026-06-01T11:00:00Z",
                "event_risk_score": 0.21,
                "source": "sentinel-ai",
                "macro_snapshot": {
                    "dxy": 99.0,
                    "vix": 15.8,
                    "us10y": 4.45,
                    "brent": 94.1,
                    "xau": 4536.0,
                    "hg": 6.54,
                },
            }

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params=None):
            assert url == "http://configured-sentinel:8004/sentinel/event_risk"
            assert params == {"symbol": "BTC", "horizon": "medium"}
            return DummyResponse()

    monkeypatch.setattr(dashboard_routes, "fetch_market_data", fake_fetch_market_data)
    monkeypatch.setattr(dashboard_routes, "_SENTINEL_URL", "http://configured-sentinel:8004")
    monkeypatch.setattr(dashboard_routes.httpx, "AsyncClient", lambda timeout=0.0: DummyClient())

    bundle = asyncio.run(dashboard_routes._fetch_macro_for_asset_scoring("medium"))

    assert bundle["data_status"] == "LIVE"
    assert bundle["fallback_used"] is False
    assert bundle["source"] == "market_data_live"
    assert bundle["metrics"]["event_risk_score"] == 0.21
