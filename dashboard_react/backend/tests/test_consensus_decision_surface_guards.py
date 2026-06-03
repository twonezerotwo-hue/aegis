from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[3]
CONSENSUS_MAIN_PATH = ROOT / "consensus_engine" / "main.py"
VENV_SITE_PACKAGES = ROOT / ".venv" / "Lib" / "site-packages"

for path in (ROOT, VENV_SITE_PACKAGES):
    if path.exists() and str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _load_consensus_module(monkeypatch, *, enabled: bool):
    monkeypatch.delenv("AEGIS_ENABLE_LEGACY_DECISION_OUTPUTS", raising=False)
    module_name = "aegis_consensus_main_phase3"
    cached_module = sys.modules.get(module_name)
    if cached_module is not None:
        cached_module.LEGACY_DECISION_OUTPUTS_ENABLED = enabled
        return cached_module

    if enabled:
        monkeypatch.setenv("AEGIS_ENABLE_LEGACY_DECISION_OUTPUTS", "true")

    spec = importlib.util.spec_from_file_location(module_name, CONSENSUS_MAIN_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    module.LEGACY_DECISION_OUTPUTS_ENABLED = enabled
    return module


def test_default_runtime_strips_legacy_decision_fields(monkeypatch):
    module = _load_consensus_module(monkeypatch, enabled=False)

    guarded = module._apply_decision_surface_guard(
        {
            "action": "BUY",
            "position_size": 0.18,
            "green_light": True,
            "green_light_thresholds": {"buy_gt": 0.65},
            "confidence": 0.82,
            "warnings": ["baseline-warning"],
        }
    )

    for forbidden in ("action", "position_size", "green_light", "green_light_thresholds"):
        assert forbidden not in guarded

    assert guarded["confidence"] == 0.82
    assert guarded["decision_surface"]["enabled"] is False
    assert guarded["decision_surface"]["env_var"] == "AEGIS_ENABLE_LEGACY_DECISION_OUTPUTS"
    assert "Legacy decision outputs disabled; analysis-only response emitted." in guarded["warnings"]


def test_opt_in_runtime_preserves_legacy_decision_fields(monkeypatch):
    module = _load_consensus_module(monkeypatch, enabled=True)

    guarded = module._apply_decision_surface_guard(
        {
            "action": "SELL",
            "position_size": 0.11,
            "green_light": True,
            "green_light_thresholds": {"sell_lt": 0.35},
        }
    )

    assert guarded["action"] == "SELL"
    assert guarded["position_size"] == 0.11
    assert guarded["green_light"] is True
    assert guarded["decision_surface"]["enabled"] is True
    assert guarded["decision_surface"]["mode"] == "legacy_opt_in"


def test_health_reports_decision_surface_mode(monkeypatch):
    module = _load_consensus_module(monkeypatch, enabled=False)
    client = TestClient(module.app)

    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["decision_surface"]["enabled"] is False
    assert data["decision_surface"]["mode"] == "analysis_only"
    assert data["decision_surface"]["env_var"] == "AEGIS_ENABLE_LEGACY_DECISION_OUTPUTS"
