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


def test_signal_hard_block_does_not_build_normal_signal():
    client = _build_client()
    payload = _signal_payload()
    data_integrity = _data_integrity_payload()
    data_integrity["source"] = ""
    payload["data_integrity"] = data_integrity

    response = client.post("/aegis-core/signal", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is False
    assert data["blocked"] is True
    assert data["decision_permission"] == "BLOCKED_BY_DATA_INTEGRITY"
    assert data["final_decision"] is False
    assert "aegis_signal" not in data
    assert "brainchain_signal" not in data
    assert "source_missing" in data["warnings"]


def test_signal_degraded_pass_still_returns_signal_with_warnings():
    client = _build_client()
    payload = _signal_payload()

    response = client.post("/aegis-core/signal", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["blocked"] is False
    assert data["data_integrity_result"]["status"] == "DEGRADED_PASS"
    assert "data_integrity_missing" in data["warnings"]
    assert "aegis_signal" in data
    assert "brainchain_signal" in data
    assert "data_integrity_missing" in data["aegis_signal"]["warnings"]
    assert "data_integrity_missing" in data["brainchain_signal"]["warnings"]


def test_signal_responses_do_not_include_action_or_position_size():
    client = _build_client()

    degraded_response = client.post("/aegis-core/signal", json=_signal_payload())
    degraded_data = degraded_response.json()
    assert "action" not in degraded_data
    assert "position_size" not in degraded_data
    assert "action" not in degraded_data["aegis_signal"]
    assert "position_size" not in degraded_data["aegis_signal"]
    assert "action" not in degraded_data["brainchain_signal"]
    assert "position_size" not in degraded_data["brainchain_signal"]

    blocked_payload = _signal_payload()
    blocked_data_integrity = _data_integrity_payload()
    blocked_data_integrity["data_confidence"] = 0.40
    blocked_payload["data_integrity"] = blocked_data_integrity
    blocked_response = client.post("/aegis-core/signal", json=blocked_payload)
    blocked_data = blocked_response.json()
    assert "action" not in blocked_data
    assert "position_size" not in blocked_data
