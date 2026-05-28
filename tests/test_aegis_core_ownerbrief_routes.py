import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "dashboard_react" / "backend"

for path in (ROOT, BACKEND_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from routes.aegis_core_routes import router


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _signal_payload() -> dict:
    return {
        "symbol": "BTC",
        "timeframe": "4h",
        "raw_regime": "LIQUIDITY_EXPANSION",
        "module_scores": {
            "touche": 0.465,
            "fundamental": 0.860,
            "sentinel": 0.679,
            "news": 0.500,
            "quantum": 0.524,
        },
        "higher_tf_scores": {
            "4h": 0.67,
            "1d": 0.70,
        },
        "data_integrity": {
            "source": "provider_name",
            "backup_source": "backup_provider",
            "observation_date": "2026-04-30",
            "release_timestamp": "2026-04-30T15:30:00+03:00",
            "available_timestamp": "2026-04-30T15:31:05+03:00",
            "is_stale": False,
            "fallback_used": False,
            "data_confidence": 0.96,
            "critical_fields_present": True,
        },
        "risk_context": {
            "contradiction_score": 25,
            "portfolio_daily_loss_pct": 0.0,
            "portfolio_weekly_loss_pct": 0.0,
            "max_daily_loss_pct": 3.0,
            "max_weekly_loss_pct": 7.0,
            "volatility_spike": False,
            "correlation_break": False,
            "stablecoin_depeg": False,
            "exchange_outage": False,
            "critical_risk_breach": False,
        },
        "kill_switch_context": {
            "manual_kill_switch": False,
            "broker_api_error": False,
            "unexpected_correlation_break": False,
            "backtest_timestamp_violation": False,
            "system_integrity_error": False,
        },
    }


def test_route_response_includes_ownerbrief_and_audit_record():
    client = _build_client()
    response = client.post("/aegis-core/signal", json=_signal_payload())
    assert response.status_code == 200
    data = response.json()
    assert "ownerbrief" in data
    assert "audit_record" in data
    assert data["ownerbrief"]["final_decision"] is False
    assert data["audit_record"]["final_decision"] is False


def test_blocked_route_response_includes_ownerbrief_and_audit_record():
    client = _build_client()
    payload = _signal_payload()
    payload["data_integrity"]["source"] = ""
    response = client.post("/aegis-core/signal", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["blocked"] is True
    assert "ownerbrief" in data
    assert "audit_record" in data
    assert data["ownerbrief"]["summary"].lower().find("blocked by data integrity") >= 0


def test_ownerbrief_and_audit_outputs_do_not_include_action_or_position_size():
    client = _build_client()
    response = client.post("/aegis-core/signal", json=_signal_payload())
    data = response.json()
    for payload_key in ("ownerbrief", "audit_record"):
        assert "action" not in data[payload_key]
        assert "position_size" not in data[payload_key]
