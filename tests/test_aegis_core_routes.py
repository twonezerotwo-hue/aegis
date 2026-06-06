import ast
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


def test_aegis_core_health_returns_signal_only_not_final():
    client = _build_client()
    response = client.get("/aegis-core/health")
    assert response.status_code == 200
    data = response.json()
    assert data["decision_permission"] == "SIGNAL_ONLY_NOT_FINAL"
    assert data["final_decision"] is False


def test_aegis_core_signal_returns_both_signals_without_action_or_position_size():
    client = _build_client()
    payload = {
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
    response = client.post("/aegis-core/signal", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "aegis_signal" in data
    assert "brainchain_signal" in data
    assert data["decision_permission"] == "SIGNAL_ONLY_NOT_FINAL"


def test_aegis_core_signal_does_not_include_action():
    client = _build_client()
    response = client.post(
        "/aegis-core/signal",
        json={
            "symbol": "BTC",
            "timeframe": "4h",
            "raw_regime": "LIQUIDITY_EXPANSION",
            "module_scores": {"touche": 0.6, "fundamental": 0.7, "sentinel": 0.8, "news": 0.5, "quantum": 0.55},
        },
    )
    data = response.json()
    assert "action" not in data
    assert "action" not in data["aegis_signal"]
    assert "action" not in data["brainchain_signal"]


def test_aegis_core_signal_does_not_include_position_size():
    client = _build_client()
    response = client.post(
        "/aegis-core/signal",
        json={
            "symbol": "BTC",
            "timeframe": "4h",
            "raw_regime": "LIQUIDITY_EXPANSION",
            "module_scores": {"touche": 0.6, "fundamental": 0.7, "sentinel": 0.8, "news": 0.5, "quantum": 0.55},
        },
    )
    data = response.json()
    assert "position_size" not in data
    assert "position_size" not in data["aegis_signal"]
    assert "position_size" not in data["brainchain_signal"]


def test_aegis_core_signal_keeps_final_decision_false():
    client = _build_client()
    response = client.post(
        "/aegis-core/signal",
        json={
            "symbol": "BTC",
            "timeframe": "4h",
            "raw_regime": "LIQUIDITY_EXPANSION",
            "module_scores": {"touche": 0.6, "fundamental": 0.7, "sentinel": 0.8, "news": 0.5, "quantum": 0.55},
        },
    )
    data = response.json()
    assert data["final_decision"] is False
    assert data["aegis_signal"]["final_decision"] is False
    assert data["brainchain_signal"]["final_decision"] is False


def test_unknown_regime_returns_warning():
    client = _build_client()
    payload = {
        "symbol": "BTC",
        "timeframe": "4h",
        "raw_regime": "UNKNOWN_REGIME",
        "module_scores": {
            "touche": 60,
            "fundamental": 70,
            "sentinel": 65,
            "news": 55,
            "quantum": 52,
        },
    }
    response = client.post("/aegis-core/signal", json=payload)
    assert response.status_code == 200
    warnings = response.json()["warnings"]
    assert any("Unknown regime" in warning for warning in warnings)


def test_missing_module_score_returns_warning():
    client = _build_client()
    payload = {
        "symbol": "BTC",
        "timeframe": "4h",
        "raw_regime": "NORMALIZATION",
        "module_scores": {
            "touche": 0.60,
            "fundamental": 0.70,
        },
    }
    response = client.post("/aegis-core/signal", json=payload)
    assert response.status_code == 200
    data = response.json()
    warnings = data["warnings"]
    assert data["success"] is False
    assert data["blocked"] is True
    assert data["decision_permission"] == "BLOCKED_BY_INSUFFICIENT_DATA"
    assert data["aegis_signal"]["consensus_status"] == "INSUFFICIENT_DATA"
    assert data["aegis_signal"]["consensus_score"] is None
    assert data["brainchain_signal"] is None
    assert any("Missing module score" in warning for warning in warnings)


def test_backtest_evidence_returns_evidence_only_not_final_and_preserves_metrics():
    client = _build_client()
    payload = {
        "symbol": "BTC",
        "timeframe": "4h",
        "metrics": {
            "pnl": 0.53,
            "win_rate": 50.0,
            "trades": 6,
            "sharpe": 5.91,
        },
    }
    response = client.post("/aegis-core/backtest-evidence", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["decision_permission"] == "EVIDENCE_ONLY_NOT_FINAL"


def test_backtest_evidence_does_not_simulate_trades():
    client = _build_client()
    payload = {
        "symbol": "BTC",
        "timeframe": "4h",
        "metrics": {
            "pnl": 0.53,
            "win_rate": 50.0,
            "trades": 6,
            "sharpe": 5.91,
        },
    }
    response = client.post("/aegis-core/backtest-evidence", json=payload)
    data = response.json()
    assert data["metrics"] == payload["metrics"]
    assert "action" not in data
    assert "position_size" not in data
    assert "simulated_trades" not in data


def test_route_file_does_not_import_forbidden_modules():
    route_path = ROOT / "dashboard_react" / "backend" / "routes" / "aegis_core_routes.py"
    tree = ast.parse(route_path.read_text(encoding="utf-8"))
    forbidden = {
        "execution_engine",
        "final_allocator",
        "position_optimizer",
        "optimizer_service",
        "paper_trading",
        "bounded_updater",
    }
    imported: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)

    lowered = " ".join(sorted(imported)).lower()
    for name in forbidden:
        assert name not in lowered
