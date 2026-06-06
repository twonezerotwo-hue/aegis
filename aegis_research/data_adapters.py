from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from typing import Any

from .models import DataSnapshot


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def missing_dependency_snapshot(source: str, package: str) -> DataSnapshot:
    return DataSnapshot(
        source=source,
        source_timestamp=None,
        ingested_at=_now_iso(),
        data_status="MISSING",
        verified=False,
        fallback_used=False,
        values={},
        warnings=[f"Optional package '{package}' is not installed; no fallback data was used."],
    )


class YFinanceReadOnlyAdapter:
    """Research/dev market data adapter.

    yfinance data is convenient but must not be displayed as verified exchange
    live data without separate validation.
    """

    package = "yfinance"

    def is_available(self) -> bool:
        return importlib.util.find_spec(self.package) is not None

    def describe(self) -> DataSnapshot:
        if not self.is_available():
            return missing_dependency_snapshot("yfinance", self.package)
        return DataSnapshot(
            source="yfinance",
            source_timestamp=None,
            ingested_at=_now_iso(),
            data_status="RECENT",
            verified=False,
            fallback_used=False,
            values={},
            warnings=["Research/dev adapter only; not verified live market data by itself."],
        )


class FinanceToolkitReadOnlyAdapter:
    package = "financetoolkit"

    def is_available(self) -> bool:
        return importlib.util.find_spec(self.package) is not None

    def describe(self) -> DataSnapshot:
        if not self.is_available():
            return missing_dependency_snapshot("FinanceToolkit", self.package)
        return DataSnapshot(
            source="FinanceToolkit",
            source_timestamp=None,
            ingested_at=_now_iso(),
            data_status="RECENT",
            verified=False,
            fallback_used=False,
            values={},
            warnings=["Research-only fundamentals adapter; source provenance is required per query."],
        )


class TechnicalAnalysisReadOnlyAdapter:
    packages = ("ta", "pandas_ta_classic")

    def availability(self) -> dict[str, str]:
        return {
            package: "available" if importlib.util.find_spec(package) else "missing_optional_dependency"
            for package in self.packages
        }

    def describe(self) -> DataSnapshot:
        availability = self.availability()
        return DataSnapshot(
            source="technical-analysis-adapters",
            source_timestamp=None,
            ingested_at=_now_iso(),
            data_status="RECENT" if "available" in availability.values() else "MISSING",
            verified=False,
            fallback_used=False,
            values={"availability": availability},
            warnings=["Indicator output is evidence only and must be range-normalized before scoring."],
        )


def adapter_inventory() -> dict[str, Any]:
    return {
        "yfinance": YFinanceReadOnlyAdapter().describe().to_dict(),
        "finance_toolkit": FinanceToolkitReadOnlyAdapter().describe().to_dict(),
        "technical_analysis": TechnicalAnalysisReadOnlyAdapter().describe().to_dict(),
    }
