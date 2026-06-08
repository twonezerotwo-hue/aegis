from __future__ import annotations

import importlib.util
import os
from collections import OrderedDict
from typing import Any

from .contract import ProviderManifest, ProviderState


def _package_available(package: str | None) -> bool:
    if not package:
        return True
    return importlib.util.find_spec(package) is not None


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: OrderedDict[str, ProviderManifest] = OrderedDict()

    def register(self, manifest: ProviderManifest) -> ProviderManifest:
        self._providers[manifest.provider_id] = manifest
        return manifest

    def get_manifest(self, provider_id: str) -> ProviderManifest | None:
        return self._providers.get(provider_id)

    def list_manifests(self) -> list[ProviderManifest]:
        return list(self._providers.values())

    def check_provider(self, provider_id: str) -> ProviderState:
        manifest = self._providers.get(provider_id)
        if manifest is None:
            return ProviderState(
                provider_id=provider_id,
                status="UNAVAILABLE_PROVIDER",
                enabled=False,
                credentials_available=False,
                warnings=[f"Provider '{provider_id}' is not registered."],
            )

        missing_credentials = [
            env_name
            for env_name in manifest.required_credentials
            if not os.getenv(env_name)
        ]
        credentials_available = len(missing_credentials) == 0
        warnings: list[str] = []

        if not manifest.enabled:
            status = "DISABLED_PROVIDER"
            warnings.append("Provider is disabled by manifest.")
        elif missing_credentials:
            status = "CREDENTIALS_MISSING"
            warnings.append("Required credential environment variable is missing.")
        elif not _package_available(manifest.optional_package):
            status = "UNAVAILABLE_PROVIDER"
            warnings.append(f"Optional package unavailable: {manifest.optional_package}")
        else:
            status = "AVAILABLE"

        return ProviderState(
            provider_id=manifest.provider_id,
            status=status,
            enabled=manifest.enabled,
            credentials_available=credentials_available,
            missing_credentials=missing_credentials,
            warnings=warnings,
            manifest=manifest.to_dict(),
        )

    def list_states(self) -> list[ProviderState]:
        return [self.check_provider(manifest.provider_id) for manifest in self._providers.values()]

    def dashboard_status(self) -> dict[str, Any]:
        return {
            "success": True,
            "system_status": self.system_status(),
            "providers": [state.to_dict() for state in self.list_states()],
            "safe_mode": "PROVIDER_STATUS_ONLY_NO_SECRETS",
        }

    def system_status(self) -> str:
        states = self.list_states()
        if any(state.status == "AVAILABLE" for state in states):
            if any(state.status in {"CREDENTIALS_MISSING", "UNAVAILABLE_PROVIDER", "DEGRADED_PROVIDER"} for state in states):
                return "PARTIAL"
            return "HEALTHY"
        return "DEGRADED"


def build_default_provider_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    for provider in (
        ProviderManifest(
            provider_id="yfinance",
            name="Yahoo Finance via yfinance",
            provider_type="market_data",
            optional_package="yfinance",
            output_fields=["dxy", "vix", "us10y", "brent", "xau", "hg"],
            verified_capability=True,
            production_allowed=False,
            notes=["Research/dashboard market data; field timestamps must come from provider rows."],
        ),
        ProviderManifest(
            provider_id="coingecko.public",
            name="CoinGecko Public Global API",
            provider_type="market_data",
            output_fields=["btc_d", "usdt_d"],
            verified_capability=True,
            rate_limit_note="Public endpoint; may rate-limit without API key.",
            production_allowed=False,
        ),
        ProviderManifest(
            provider_id="sentinel.macro",
            name="Sentinel Macro Service",
            provider_type="risk",
            output_fields=["event_risk_score", "hours_to_event", "regime"],
            verified_capability=True,
            rate_limit_note="Internal service URL from SENTINEL_URL.",
            production_allowed=False,
        ),
        ProviderManifest(
            provider_id="binance.public",
            name="Binance Public Market Data",
            provider_type="market_data",
            output_fields=["ticker", "ohlcv"],
            verified_capability=True,
            rate_limit_note="Public REST limits apply; no private credentials required.",
            production_allowed=False,
            notes=["Read-only public market data only."],
        ),
        ProviderManifest(
            provider_id="fred",
            name="FRED Economic Data",
            provider_type="macro_data",
            required_credentials=["FRED_API_KEY"],
            output_fields=["macro_series"],
            verified_capability=True,
            production_allowed=False,
        ),
        ProviderManifest(
            provider_id="newsapi",
            name="NewsAPI",
            provider_type="news",
            required_credentials=["NEWSAPI_KEY"],
            output_fields=["news_items", "source_timestamp"],
            verified_capability=False,
            production_allowed=False,
        ),
        ProviderManifest(
            provider_id="openbb.placeholder",
            name="OpenBB Future Provider",
            provider_type="research_data",
            optional_package="openbb",
            output_fields=["provider_catalog"],
            verified_capability=False,
            production_allowed=False,
            notes=["Placeholder only; license/dependency review required before import."],
        ),
        ProviderManifest(
            provider_id="ccxt.read_only.placeholder",
            name="CCXT Read-only Placeholder",
            provider_type="crypto_market_data",
            optional_package="ccxt",
            output_fields=["ticker", "ohlcv"],
            verified_capability=True,
            production_allowed=False,
            notes=["Only public read-only methods are allowed; no credentials or order calls."],
        ),
    ):
        registry.register(provider)
    return registry


_DEFAULT_REGISTRY: ProviderRegistry | None = None


def get_default_provider_registry() -> ProviderRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = build_default_provider_registry()
    return _DEFAULT_REGISTRY

