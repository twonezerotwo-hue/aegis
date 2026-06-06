from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import FORBIDDEN_SAFE_FIELDS


RESEARCH_ONLY_PACKAGE = "aegis_research"
SAFE_CORE_FORBIDDEN_IMPORTS = {
    "strategies.execution_engine",
    "dashboard_react.backend.routes.paper_trading",
    "macro_bridge.run",
    "macro_bridge.executor.trade_executor",
    "consensus_engine.src.final_allocator",
    "consensus_engine.src.position_optimizer",
    "consensus_engine.src.bounded_updater",
    "optimizer_service",
}

RESTRICTED_PRODUCTION_DEPENDENCY_LICENSES = {"GPL-3.0", "AGPL-3.0", "NOASSERTION"}


def assert_no_forbidden_fields(payload: dict[str, Any]) -> None:
    present = FORBIDDEN_SAFE_FIELDS.intersection(payload)
    if present:
        raise ValueError(f"Research payload contains forbidden fields: {sorted(present)}")


def safe_core_python_files(root: Path) -> list[Path]:
    return sorted((root / "aegis_core").rglob("*.py"))
