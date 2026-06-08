from aegis_platform.modules.contract import ModuleManifest
from aegis_platform.modules.registry import ModuleRegistry, build_default_module_registry
from aegis_platform.providers.registry import build_default_provider_registry


def test_module_registry_returns_structured_missing_module():
    registry = ModuleRegistry()
    state = registry.check_module("missing.optional")

    assert state.status == "MISSING_MODULE"
    assert state.enabled is False
    assert state.warnings


def test_default_module_registry_marks_optimizer_disabled():
    registry = build_default_module_registry()
    state = registry.check_module("optimizer.legacy")

    assert state.status == "DISABLED_MODULE"
    assert state.enabled is False
    assert state.manifest["runtime"] == "legacy"
    assert state.manifest["data_safety"]["can_emit_execution"] is False


def test_module_manifest_rejects_execution_capability():
    payload = {
        "module_id": "bad.execution",
        "name": "Bad Execution",
        "version": "1.0.0",
        "category": "signal",
        "enabled": True,
        "required": False,
        "runtime": "active",
        "dependencies": [],
        "provides": [],
        "consumes": [],
        "input_contract": {},
        "output_contract": {},
        "failure_mode": "degrade",
        "data_safety": {
            "requires_verified_data": False,
            "can_emit_live_label": False,
            "can_emit_decision": False,
            "can_emit_execution": True,
        },
    }

    try:
        ModuleManifest.from_dict(payload)
    except Exception as exc:  # noqa: BLE001
        assert "can_emit_execution" in str(exc)
    else:
        raise AssertionError("execution-capable manifest should be rejected")


def test_provider_registry_reports_missing_credentials_without_secret_values(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    registry = build_default_provider_registry()
    state = registry.check_provider("fred")

    assert state.status == "CREDENTIALS_MISSING"
    assert state.credentials_available is False
    assert state.missing_credentials == ["FRED_API_KEY"]
    assert "API_KEY" not in str(state.to_dict().get("warnings", []))


def test_system_status_payloads_are_dashboard_safe():
    module_status = build_default_module_registry().dashboard_status()
    provider_status = build_default_provider_registry().dashboard_status()

    assert module_status["success"] is True
    assert "modules" in module_status
    assert provider_status["success"] is True
    assert "providers" in provider_status
    assert provider_status["safe_mode"] == "PROVIDER_STATUS_ONLY_NO_SECRETS"
