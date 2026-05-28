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
    }


def _data_integrity_payload() -> dict:
    return {
        "source": "provider_name",
        "backup_source": "backup_provider",
        "observation_date": "2026-04-30",
        "release_timestamp": "2026-04-30T15:30:00+03:00",
        "available_timestamp": "2026-04-30T15:31:05+03:00",
        "is_stale": False,
        "fallback_used": False,
        "data_confidence": 0.96,
        "critical_fields_present": True,
    }


def _risk_context_payload() -> dict:
    return {
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
    }


def _kill_switch_context_payload() -> dict:
    return {
        "manual_kill_switch": False,
        "broker_api_error": False,
        "unexpected_correlation_break": False,
        "backtest_timestamp_violation": False,
        "system_integrity_error": False,
    }


def test_signal_blocked_by_risk_does_not_include_action_or_position_size():
    client = _build_client()
    payload = _signal_payload()
    risk_context = _risk_context_payload()
    risk_context["stablecoin_depeg"] = True
    payload["data_integrity"] = _data_integrity_payload()
    payload["risk_context"] = risk_context
    payload["kill_switch_context"] = _kill_switch_context_payload()

    response = client.post("/aegis-core/signal", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is False
    assert data["blocked"] is True
    assert data["decision_permission"] == "BLOCKED_BY_RISK_OR_KILL_SWITCH"
    assert data["risk_result"]["status"] == "BLOCK"
    assert data["kill_switch_result"]["status"] == "ON"
    for forbidden in ("action", "position_size"):
        assert forbidden not in data
        assert forbidden not in data["aegis_signal"]
        assert forbidden not in data["brainchain_signal"]


def test_signal_blocked_by_kill_switch_does_not_include_action_or_position_size():
    client = _build_client()
    payload = _signal_payload()
    payload["data_integrity"] = _data_integrity_payload()
    payload["risk_context"] = _risk_context_payload()
    kill_context = _kill_switch_context_payload()
    kill_context["manual_kill_switch"] = True
    payload["kill_switch_context"] = kill_context

    response = client.post("/aegis-core/signal", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is False
    assert data["blocked"] is True
    assert data["decision_permission"] == "BLOCKED_BY_RISK_OR_KILL_SWITCH"
    assert data["kill_switch_result"]["status"] == "ON"
    for forbidden in ("action", "position_size"):
        assert forbidden not in data
        assert forbidden not in data["aegis_signal"]
        assert forbidden not in data["brainchain_signal"]


def test_normal_pass_returns_signals_and_non_final_wrappers():
    client = _build_client()
    payload = _signal_payload()
    payload["data_integrity"] = _data_integrity_payload()
    payload["risk_context"] = _risk_context_payload()
    payload["kill_switch_context"] = _kill_switch_context_payload()

    response = client.post("/aegis-core/signal", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["blocked"] is False
    assert data["decision_permission"] == "SIGNAL_ONLY_NOT_FINAL"
    assert "aegis_signal" in data
    assert "brainchain_signal" in data
    assert data["risk_result"]["status"] == "PASS"
    assert data["risk_result"]["final_decision"] is False
    assert data["kill_switch_result"]["status"] == "OFF"
    assert data["kill_switch_result"]["final_decision"] is False
    for payload_key in ("risk_result", "kill_switch_result"):
        for forbidden in ("action", "position_size", "order", "execution", "broker"):
            assert forbidden not in data[payload_key]
