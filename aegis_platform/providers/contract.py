from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


ProviderStatus = Literal[
    "AVAILABLE",
    "UNAVAILABLE_PROVIDER",
    "CREDENTIALS_MISSING",
    "DISABLED_PROVIDER",
    "DEGRADED_PROVIDER",
]


@dataclass(frozen=True)
class ProviderManifest:
    provider_id: str
    name: str
    provider_type: str
    enabled: bool = True
    required_credentials: list[str] = field(default_factory=list)
    optional_package: str | None = None
    rate_limit_note: str = "Provider-specific rate limits apply."
    output_fields: list[str] = field(default_factory=list)
    verified_capability: bool = False
    fallback_behavior: str = "mark affected fields degraded/unverified"
    timestamp_behavior: str = "preserve provider timestamp when available; do not fabricate source freshness"
    read_only: bool = True
    production_allowed: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProviderState:
    provider_id: str
    status: ProviderStatus
    enabled: bool
    credentials_available: bool
    missing_credentials: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    manifest: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

