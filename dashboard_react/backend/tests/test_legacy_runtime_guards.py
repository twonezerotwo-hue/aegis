from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = ROOT / "dashboard_react" / "backend"
MAIN_PATH = BACKEND_ROOT / "main.py"

for path in (ROOT, BACKEND_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _load_main_module(monkeypatch):
    for env_var in (
        "AEGIS_ENABLE_LEGACY_RUNTIME",
        "AEGIS_ENABLE_PAPER_TRADING",
        "AEGIS_ENABLE_EXECUTION_ENDPOINTS",
        "AEGIS_ENABLE_OPTIMIZER_ENDPOINTS",
    ):
        monkeypatch.delenv(env_var, raising=False)

    module_name = "aegis_dashboard_main_phase2_test"
    sys.modules.pop(module_name, None)

    spec = importlib.util.spec_from_file_location(module_name, MAIN_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_main_file_avoids_top_level_legacy_imports():
    tree = ast.parse(MAIN_PATH.read_text(encoding="utf-8-sig"))
    top_level_imports: list[str] = []

    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level_imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported = ", ".join(alias.name for alias in node.names)
            top_level_imports.append(f"{node.module}:{imported}")

    joined = " | ".join(top_level_imports)
    assert "routes:paper_trading" not in joined
    assert "routes:paper_autotrader_routes" not in joined
    assert "routes:optimizer_agent_routes" not in joined
    assert "unified_optimizer" not in joined
    assert "execution_engine" not in joined


def test_default_runtime_disables_legacy_execution_and_optimizer(monkeypatch):
    module = _load_main_module(monkeypatch)
    client = TestClient(module.app)

    execute_response = client.post(
        "/execute",
        json={
            "symbol": "BTCUSDT",
            "action": "BUY",
            "timeframe": "4h",
            "quantity": 1.0,
            "price": 100000.0,
            "risk_pct": 0.01,
        },
    )
    assert execute_response.status_code == 503
    execute_data = execute_response.json()
    assert execute_data["detail"]["feature"] == "live execution endpoint"
    assert execute_data["detail"]["env_var"] == "AEGIS_ENABLE_EXECUTION_ENDPOINTS"

    optimizer_response = client.get("/api/optimizer/status")
    assert optimizer_response.status_code == 200
    optimizer_data = optimizer_response.json()
    assert optimizer_data["enabled"] is False
    assert optimizer_data["feature"] == "optimizer endpoints"
    assert optimizer_data["env_var"] == "AEGIS_ENABLE_OPTIMIZER_ENDPOINTS"

    optimizer_run_response = client.post("/api/optimizer/run", json={})
    assert optimizer_run_response.status_code == 503
    optimizer_run_data = optimizer_run_response.json()
    assert optimizer_run_data["detail"]["feature"] == "optimizer agent routes"
    assert optimizer_run_data["detail"]["env_var"] == "AEGIS_ENABLE_OPTIMIZER_ENDPOINTS"


def test_default_runtime_disables_paper_trading_routes(monkeypatch):
    module = _load_main_module(monkeypatch)
    client = TestClient(module.app)

    response = client.get("/api/paper/status")
    assert response.status_code == 503
    data = response.json()
    assert data["detail"]["feature"] == "paper trading routes"
    assert data["detail"]["env_var"] == "AEGIS_ENABLE_PAPER_TRADING"

    auto_response = client.get("/api/paper_auto/status")
    assert auto_response.status_code == 503
    auto_data = auto_response.json()
    assert auto_data["detail"]["feature"] == "paper auto routes"
    assert auto_data["detail"]["env_var"] == "AEGIS_ENABLE_PAPER_TRADING"
