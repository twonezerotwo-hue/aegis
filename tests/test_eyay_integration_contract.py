import json
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


def _manifest() -> dict:
    manifest_path = ROOT / "aegis_core" / "integration_manifest.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


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
            "quantum": 0.524
        },
        "higher_tf_scores": {
            "4h": 0.67,
            "1d": 0.70
        },
        "data_integrity": {
            "source": "provider_name",
            "backup_source": "backup_provider",
            "observation_date": "2026-05-01",
            "release_timestamp": "2026-05-01T15:30:00+03:00",
            "available_timestamp": "2026-05-01T15:31:05+03:00",
            "is_stale": False,
            "fallback_used": False,
            "data_confidence": 0.96,
            "critical_fields_present": True
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
            "critical_risk_breach": False
        },
        "kill_switch_context": {
            "manual_kill_switch": False,
            "broker_api_error": False,
            "unexpected_correlation_break": False,
            "backtest_timestamp_violation": False,
            "system_integrity_error": False
        }
    }


def test_integration_manifest_exists():
    assert (ROOT / "aegis_core" / "integration_manifest.json").exists()


def test_approved_routes_are_only_aegis_core_routes():
    manifest = _manifest()
    assert manifest["approved_routes"]
    assert all(route.startswith("/aegis-core/") for route in manifest["approved_routes"])


def test_forbidden_fields_include_action_and_position_size():
    manifest = _manifest()
    assert "action" in manifest["forbidden_fields"]
    assert "position_size" in manifest["forbidden_fields"]


def test_final_decision_allowed_is_false():
    manifest = _manifest()
    assert manifest["final_decision_allowed"] is False


def test_execution_allowed_is_false():
    manifest = _manifest()
    assert manifest["execution_allowed"] is False


def test_contract_document_exists():
    assert (ROOT / "docs" / "EYAY_BRAINCHAIN_AEGIS_INTEGRATION_CONTRACT.md").exists()


def test_legacy_isolation_document_exists():
    assert (ROOT / "docs" / "LEGACY_ENDPOINT_ISOLATION.md").exists()


def test_signal_response_still_contains_ownerbrief_and_audit_record():
    client = _build_client()
    response = client.post("/aegis-core/signal", json=_signal_payload())
    assert response.status_code == 200
    data = response.json()
    assert "ownerbrief" in data
    assert "audit_record" in data


def test_signal_response_still_does_not_contain_action_or_position_size():
    client = _build_client()
    response = client.post("/aegis-core/signal", json=_signal_payload())
    data = response.json()
    assert "action" not in data
    assert "position_size" not in data
    assert "action" not in data["aegis_signal"]
    assert "position_size" not in data["aegis_signal"]
    assert "action" not in data["brainchain_signal"]
    assert "position_size" not in data["brainchain_signal"]


def test_backtest_evidence_response_remains_evidence_only_not_final():
    client = _build_client()
    response = client.post(
        "/aegis-core/backtest-evidence",
        json={
            "symbol": "BTC",
            "timeframe": "4h",
            "metrics": {
                "pnl": 0.53,
                "win_rate": 50.0,
                "trades": 6,
                "sharpe": 5.91
            }
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["decision_permission"] == "EVIDENCE_ONLY_NOT_FINAL"
