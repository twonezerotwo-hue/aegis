from __future__ import annotations

import importlib.util
from collections import OrderedDict
from typing import Any

from .contract import DataSafety, ModuleManifest, ModuleState


def _module_available(import_path: str | None) -> bool:
    if not import_path:
        return True
    candidates = [import_path]
    if import_path.startswith("dashboard_react.backend."):
        candidates.append(import_path.replace("dashboard_react.backend.", "", 1))
    for candidate in candidates:
        try:
            if importlib.util.find_spec(candidate) is not None:
                return True
        except (ImportError, ModuleNotFoundError, AttributeError, ValueError):
            continue
    return False


class ModuleRegistry:
    def __init__(self) -> None:
        self._manifests: OrderedDict[str, ModuleManifest] = OrderedDict()

    def register(self, manifest: ModuleManifest | dict[str, Any]) -> ModuleManifest:
        parsed = manifest if isinstance(manifest, ModuleManifest) else ModuleManifest.from_dict(manifest)
        parsed.validate()
        self._manifests[parsed.module_id] = parsed
        return parsed

    def list_manifests(self) -> list[ModuleManifest]:
        return list(self._manifests.values())

    def get_manifest(self, module_id: str) -> ModuleManifest | None:
        return self._manifests.get(module_id)

    def check_module(self, module_id: str) -> ModuleState:
        manifest = self._manifests.get(module_id)
        if manifest is None:
            return ModuleState(
                module_id=module_id,
                status="MISSING_MODULE",
                enabled=False,
                runtime="disabled",
                required=False,
                warnings=[f"Module '{module_id}' is not registered."],
            )

        missing_dependencies = [
            dependency
            for dependency in manifest.dependencies
            if dependency not in self._manifests or not self._manifests[dependency].enabled
        ]
        warnings: list[str] = []

        if not manifest.enabled or manifest.runtime == "disabled":
            status = "DISABLED_MODULE"
            warnings.append("Module is disabled by manifest/runtime.")
        elif not _module_available(manifest.import_path):
            status = "MISSING_MODULE" if manifest.required else "DEGRADED_MODULE"
            warnings.append(f"Optional import unavailable: {manifest.import_path}")
        elif missing_dependencies:
            status = "DEGRADED_MODULE"
            warnings.append("One or more declared dependencies are missing or disabled.")
        elif manifest.runtime == "legacy":
            status = "DISABLED_MODULE"
            warnings.append("Legacy module is not active in default safe runtime.")
        else:
            status = "HEALTHY"

        return ModuleState(
            module_id=manifest.module_id,
            status=status,
            enabled=manifest.enabled,
            runtime=manifest.runtime,
            required=manifest.required,
            missing_dependencies=missing_dependencies,
            warnings=warnings,
            manifest=manifest.to_dict(),
        )

    def list_states(self) -> list[ModuleState]:
        return [self.check_module(manifest.module_id) for manifest in self._manifests.values()]

    def system_status(self) -> str:
        states = self.list_states()
        required_failed = any(
            state.required and state.status in {"MISSING_MODULE", "FAILED"}
            for state in states
        )
        degraded = any(
            state.status in {"DEGRADED_MODULE", "MISSING_MODULE", "UNAVAILABLE_PROVIDER"}
            for state in states
            if state.enabled
        )
        if required_failed:
            return "FAILED"
        if degraded:
            return "DEGRADED"
        if any(state.status == "DISABLED_MODULE" for state in states):
            return "PARTIAL"
        return "HEALTHY"

    def dashboard_status(self) -> dict[str, Any]:
        states = [state.to_dict() for state in self.list_states()]
        return {
            "success": True,
            "system_status": self.system_status(),
            "modules": states,
            "safe_mode": "MODULE_STATUS_ONLY_NO_EXECUTION",
        }


def _manifest(
    module_id: str,
    name: str,
    *,
    category: str,
    runtime: str = "active",
    enabled: bool = True,
    required: bool = False,
    dependencies: list[str] | None = None,
    provides: list[str] | None = None,
    consumes: list[str] | None = None,
    import_path: str | None = None,
    health_endpoint: str | None = None,
    failure_mode: str = "degrade",
    requires_verified_data: bool = False,
    can_emit_live_label: bool = False,
    can_emit_decision: bool = False,
    removable: bool = True,
    tested: bool = False,
    clear_data_provenance: bool = False,
    notes: list[str] | None = None,
) -> ModuleManifest:
    return ModuleManifest(
        module_id=module_id,
        name=name,
        version="1.0.0",
        category=category,  # type: ignore[arg-type]
        enabled=enabled,
        required=required,
        runtime=runtime,  # type: ignore[arg-type]
        dependencies=dependencies or [],
        provides=provides or [],
        consumes=consumes or [],
        input_contract={},
        output_contract={
            "status": "structured",
            "data_status": "LIVE | RECENT | STALE | FALLBACK | PARTIAL_FALLBACK | MISSING | UNKNOWN",
        },
        failure_mode=failure_mode,  # type: ignore[arg-type]
        data_safety=DataSafety(
            requires_verified_data=requires_verified_data,
            can_emit_live_label=can_emit_live_label,
            can_emit_decision=can_emit_decision,
            can_emit_execution=False,
        ),
        import_path=import_path,
        health_endpoint=health_endpoint,
        fallback_behavior="return structured degraded output without crashing",
        removable=removable,
        tested=tested,
        clear_data_provenance=clear_data_provenance,
        notes=notes or [],
    )


def build_default_module_registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    for manifest in (
        _manifest(
            "core.signal",
            "AEGIS Core Signal",
            category="signal",
            required=True,
            import_path="aegis_core",
            health_endpoint="/aegis-core/health",
            requires_verified_data=True,
            can_emit_decision=False,
            removable=False,
            tested=True,
            clear_data_provenance=True,
            notes=["Signal-only. No broker, order, or execution surface."],
        ),
        _manifest(
            "research.catalog",
            "External Repo Research Matrix",
            category="research",
            runtime="research_only",
            import_path="aegis_research.external_repo_matrix",
            health_endpoint="/api/agent/research/external-repo-matrix",
            removable=True,
            tested=True,
            notes=["Metadata-only; does not affect runtime signals."],
        ),
        _manifest(
            "macro.market_data",
            "Macro Market Data Provider Layer",
            category="data",
            dependencies=[],
            import_path="dashboard_react.backend.routes.macro",
            health_endpoint="/api/macro",
            requires_verified_data=True,
            can_emit_live_label=True,
            removable=False,
            tested=True,
            clear_data_provenance=True,
        ),
        _manifest(
            "agent.orchestrator",
            "Safe Agent Orchestrator",
            category="signal",
            dependencies=["macro.market_data"],
            import_path="dashboard_react.backend.services.agent_loop",
            health_endpoint="/api/agent/status",
            requires_verified_data=False,
            can_emit_decision=False,
            removable=True,
            tested=True,
            clear_data_provenance=True,
        ),
        _manifest(
            "consensus.engine",
            "Consensus Engine Service",
            category="signal",
            import_path="consensus_engine",
            health_endpoint="http://localhost:8005/health",
            removable=True,
            tested=False,
            notes=["External service may be down; dashboard should degrade."],
        ),
        _manifest(
            "analyzer.ai",
            "Analyzer AI Service",
            category="report",
            import_path="strategies.analyzer_ai",
            health_endpoint="http://localhost:8007/health",
            removable=True,
            tested=False,
        ),
        _manifest(
            "sentinel.macro",
            "Sentinel Macro Service",
            category="risk",
            import_path="strategies.sentinel_ai",
            health_endpoint="http://localhost:8004/health",
            removable=True,
            tested=False,
            clear_data_provenance=True,
        ),
        _manifest(
            "dashboard.backend",
            "Dashboard Backend API",
            category="dashboard",
            required=True,
            import_path="dashboard_react.backend.main",
            health_endpoint="/health",
            removable=False,
            tested=True,
        ),
        _manifest(
            "dashboard.frontend",
            "Dashboard Frontend",
            category="dashboard",
            health_endpoint="http://localhost:3001",
            removable=False,
            tested=True,
        ),
        _manifest(
            "backtest.evidence",
            "Backtest Evidence Routes",
            category="backtest",
            import_path="dashboard_react.backend.routes.backtest_routes",
            health_endpoint="/backtest",
            removable=True,
            tested=True,
        ),
        _manifest(
            "optimizer.legacy",
            "Legacy Optimizer Service",
            category="research",
            runtime="legacy",
            enabled=False,
            import_path="optimizer_service",
            health_endpoint="http://localhost:8008/health",
            failure_mode="disable",
            removable=True,
            tested=True,
            notes=["Disabled for dashboard by default; cannot mutate weights from active UI."],
        ),
        _manifest(
            "paper.legacy",
            "Paper Trading Legacy Runtime",
            category="research",
            runtime="legacy",
            enabled=False,
            import_path="dashboard_react.backend.routes.paper_trading",
            failure_mode="disable",
            removable=True,
            tested=True,
            notes=["Explicit opt-in only. Not part of safe signal path."],
        ),
        _manifest(
            "news.sentiment",
            "News AI Limited",
            category="data",
            import_path=None,
            health_endpoint="http://localhost:8006/health",
            removable=True,
            tested=False,
            clear_data_provenance=True,
        ),
    ):
        registry.register(manifest)
    return registry


_DEFAULT_REGISTRY: ModuleRegistry | None = None


def get_default_module_registry() -> ModuleRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = build_default_module_registry()
    return _DEFAULT_REGISTRY
