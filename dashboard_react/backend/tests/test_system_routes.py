import sys
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parents[1]
for path in (BACKEND_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from routes.system import system_full_health, system_module_detail, system_modules, system_providers


@pytest.mark.asyncio
async def test_system_modules_returns_structured_states():
    payload = await system_modules()

    assert payload["success"] is True
    assert payload["system_status"] in {"HEALTHY", "DEGRADED", "PARTIAL", "FAILED"}
    assert any(item["module_id"] == "optimizer.legacy" for item in payload["modules"])


@pytest.mark.asyncio
async def test_system_module_detail_handles_missing_module():
    payload = await system_module_detail("not.registered")

    assert payload["success"] is False
    assert payload["module"]["status"] == "MISSING_MODULE"


@pytest.mark.asyncio
async def test_system_providers_returns_credentials_missing_not_crash(monkeypatch):
    monkeypatch.delenv("NEWSAPI_KEY", raising=False)
    payload = await system_providers()

    assert payload["success"] is True
    assert any(item["status"] == "CREDENTIALS_MISSING" for item in payload["providers"])


@pytest.mark.asyncio
async def test_system_full_health_is_safe_status_only():
    payload = await system_full_health()

    assert payload["success"] in {True, False}
    assert payload["safe_mode"] == "FULL_HEALTH_STATUS_ONLY_NO_EXECUTION"
    assert "modules" in payload
    assert "providers" in payload
