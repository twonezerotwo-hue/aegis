from __future__ import annotations

from typing import Any

from .registry import get_default_module_registry


def full_module_health() -> dict[str, Any]:
    registry = get_default_module_registry()
    status = registry.dashboard_status()
    status["health_contract"] = {
        "missing_optional_module": "MISSING_MODULE or DEGRADED_MODULE",
        "disabled_module": "DISABLED_MODULE",
        "required_missing": "FAILED",
        "safe_failure": "structured status, no raw import traceback",
    }
    return status

