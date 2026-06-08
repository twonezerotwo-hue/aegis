from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from aegis_platform.modules.health import full_module_health
from aegis_platform.modules.registry import get_default_module_registry
from aegis_platform.providers.registry import get_default_provider_registry


router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/modules")
async def system_modules() -> dict[str, Any]:
    """Dashboard-safe module states."""
    return get_default_module_registry().dashboard_status()


@router.get("/modules/{module_id:path}")
async def system_module_detail(module_id: str) -> dict[str, Any]:
    """Dashboard-safe module detail by id."""
    state = get_default_module_registry().check_module(module_id)
    return {
        "success": state.status != "MISSING_MODULE",
        "system_status": "DEGRADED" if state.status != "HEALTHY" else "HEALTHY",
        "module": state.to_dict(),
        "safe_mode": "MODULE_STATUS_ONLY_NO_EXECUTION",
    }


@router.get("/providers")
async def system_providers() -> dict[str, Any]:
    """Dashboard-safe provider states. Never returns secret values."""
    return get_default_provider_registry().dashboard_status()


@router.get("/health/full")
async def system_full_health() -> dict[str, Any]:
    """Combined module/provider health for diagnostics."""
    module_health = full_module_health()
    provider_health = get_default_provider_registry().dashboard_status()
    failed = module_health["system_status"] == "FAILED"
    degraded = (
        failed
        or module_health["system_status"] in {"DEGRADED", "PARTIAL"}
        or provider_health["system_status"] in {"DEGRADED", "PARTIAL"}
    )
    return {
        "success": not failed,
        "system_status": "FAILED" if failed else "DEGRADED" if degraded else "HEALTHY",
        "modules": module_health,
        "providers": provider_health,
        "safe_mode": "FULL_HEALTH_STATUS_ONLY_NO_EXECUTION",
    }

