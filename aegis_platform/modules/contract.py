from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .errors import ModuleManifestError


ModuleCategory = Literal["data", "signal", "risk", "research", "dashboard", "backtest", "report"]
ModuleRuntime = Literal["active", "research_only", "legacy", "disabled"]
FailureMode = Literal["degrade", "block", "disable", "fallback"]
ModuleStatus = Literal[
    "HEALTHY",
    "DEGRADED_MODULE",
    "MISSING_MODULE",
    "DISABLED_MODULE",
    "UNAVAILABLE_PROVIDER",
    "FAILED",
]

FORBIDDEN_CONTRACT_FIELDS = {
    "action",
    "buy",
    "sell",
    "hold",
    "rebalance",
    "position_size",
    "order",
    "broker",
    "execution",
}


def _without_forbidden(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in FORBIDDEN_CONTRACT_FIELDS}


@dataclass(frozen=True)
class DataSafety:
    requires_verified_data: bool = False
    can_emit_live_label: bool = False
    can_emit_decision: bool = False
    can_emit_execution: bool = False

    def validate(self, module_id: str) -> None:
        if self.can_emit_execution:
            raise ModuleManifestError(f"{module_id} cannot be registered with can_emit_execution=true")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ModuleManifest:
    module_id: str
    name: str
    version: str
    category: ModuleCategory
    enabled: bool
    required: bool
    runtime: ModuleRuntime
    dependencies: list[str] = field(default_factory=list)
    provides: list[str] = field(default_factory=list)
    consumes: list[str] = field(default_factory=list)
    input_contract: dict[str, Any] = field(default_factory=dict)
    output_contract: dict[str, Any] = field(default_factory=dict)
    failure_mode: FailureMode = "degrade"
    data_safety: DataSafety = field(default_factory=DataSafety)
    import_path: str | None = None
    health_endpoint: str | None = None
    fallback_behavior: str = "structured degraded output"
    removable: bool = True
    tested: bool = False
    clear_data_provenance: bool = False
    notes: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ModuleManifest":
        raw_safety = payload.get("data_safety") or {}
        safety = raw_safety if isinstance(raw_safety, DataSafety) else DataSafety(**raw_safety)
        manifest = cls(
            module_id=str(payload["module_id"]),
            name=str(payload["name"]),
            version=str(payload.get("version", "1.0.0")),
            category=payload["category"],
            enabled=bool(payload.get("enabled", True)),
            required=bool(payload.get("required", False)),
            runtime=payload.get("runtime", "active"),
            dependencies=list(payload.get("dependencies", [])),
            provides=list(payload.get("provides", [])),
            consumes=list(payload.get("consumes", [])),
            input_contract=dict(payload.get("input_contract", {})),
            output_contract=dict(payload.get("output_contract", {})),
            failure_mode=payload.get("failure_mode", "degrade"),
            data_safety=safety,
            import_path=payload.get("import_path"),
            health_endpoint=payload.get("health_endpoint"),
            fallback_behavior=str(payload.get("fallback_behavior", "structured degraded output")),
            removable=bool(payload.get("removable", True)),
            tested=bool(payload.get("tested", False)),
            clear_data_provenance=bool(payload.get("clear_data_provenance", False)),
            notes=list(payload.get("notes", [])),
        )
        manifest.validate()
        return manifest

    def validate(self) -> None:
        if not self.module_id or "." not in self.module_id:
            raise ModuleManifestError("module_id must be namespaced, for example macro.market_data")
        if self.category not in {"data", "signal", "risk", "research", "dashboard", "backtest", "report"}:
            raise ModuleManifestError(f"{self.module_id} has invalid category {self.category}")
        if self.runtime not in {"active", "research_only", "legacy", "disabled"}:
            raise ModuleManifestError(f"{self.module_id} has invalid runtime {self.runtime}")
        if self.failure_mode not in {"degrade", "block", "disable", "fallback"}:
            raise ModuleManifestError(f"{self.module_id} has invalid failure_mode {self.failure_mode}")
        forbidden = FORBIDDEN_CONTRACT_FIELDS.intersection(self.output_contract)
        if forbidden:
            raise ModuleManifestError(f"{self.module_id} output_contract contains forbidden fields: {sorted(forbidden)}")
        self.data_safety.validate(self.module_id)

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = asdict(self)
        payload["data_safety"] = self.data_safety.to_dict()
        return _without_forbidden(payload)


@dataclass(frozen=True)
class ModuleState:
    module_id: str
    status: ModuleStatus
    enabled: bool
    runtime: ModuleRuntime
    required: bool
    missing_dependencies: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    manifest: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _without_forbidden(asdict(self))

