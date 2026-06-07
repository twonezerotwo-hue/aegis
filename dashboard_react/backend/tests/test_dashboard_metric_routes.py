import sys
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from routes import dashboard


@pytest.mark.asyncio
async def test_touche_metric_prefers_live_service_payload(monkeypatch):
    async def fake_fetch(symbol: str, timeframe: str, modules: set[str] | None = None) -> dict:
        return {
            "touche": {
                "eqs_score": 72,
                "tf_signals": {timeframe: "BUY"},
                "data_mode": "LIVE",
                "source": "touche-ai",
                "fallback_used": False,
                "data_range": {"end": "2026-06-07T10:00:00+00:00"},
            },
            "fundamental": None,
            "news": None,
            "sentinel": None,
            "quantum": None,
        }

    async def fail_prometheus(*args, **kwargs):
        raise AssertionError("Prometheus should not be used when live score is available")

    monkeypatch.setattr(dashboard, "_fetch_live_module_payloads", fake_fetch)
    monkeypatch.setattr(dashboard, "_prometheus_snapshot_for_key", fail_prometheus)

    response = await dashboard.get_touche_metrics(
        symbol="BTC/USDT",
        timeframe="5m",
        prometheus_url="http://prometheus.invalid",
    )

    assert response["score"] > 0.5
    assert response["source"] == "touche-ai"
    assert response["data_status"] == "LIVE"
    assert response["verified"] is True


@pytest.mark.asyncio
async def test_consensus_marks_missing_metric_source_without_live_payload(monkeypatch):
    async def fake_fetch(symbol: str, timeframe: str, modules: set[str] | None = None) -> dict:
        return {
            "touche": None,
            "fundamental": None,
            "news": None,
            "sentinel": None,
            "quantum": None,
        }

    async def fake_prometheus_snapshot(client, *, payload_key: str, timeframe: str, symbol: str | None):
        module = dashboard._PROMETHEUS_MODULES[payload_key]["module"]
        return 0.5, dashboard._build_module_source(
            module=module,
            service="prometheus",
            source="prometheus_missing_metric",
            source_data=f"{payload_key}_missing",
            timestamp=None,
            timestamp_source="none",
            data_status="MISSING",
            fallback_used=False,
            asset_specific=False,
            shared_score=False,
            warnings=["Default neutral module score; Prometheus metric unavailable."],
            value=0.5,
        )

    monkeypatch.setattr(dashboard, "_fetch_live_module_payloads", fake_fetch)
    monkeypatch.setattr(dashboard, "_prometheus_snapshot_for_key", fake_prometheus_snapshot)

    response = await dashboard.get_consensus(
        symbol="BTC/USDT",
        timeframe="5m",
        horizon="medium",
        prometheus_url="http://prometheus.invalid",
    )

    assert response["weighted_score"] == pytest.approx(0.5)
    assert response["data_status"] == "MISSING"
    assert response["verified"] is False
    assert response["module_sources"]["technical"]["source"] == "prometheus_missing_metric"
