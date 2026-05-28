"""Evidence-only backtest wrapper for AEGIS Core.

Source references:
- dashboard_react/backend/routes/backtest_routes.py
- dashboard_react/frontend/src/types/backtestV2.ts
"""

from __future__ import annotations

FORBIDDEN_EVIDENCE_KEYS = {"action", "position_size", "order", "execution", "broker"}


def format_backtest_evidence(raw_metrics: dict) -> dict:
    """Wrap raw metrics as evidence-only output without simulating trades."""
    warnings: list[str] = []

    if not isinstance(raw_metrics, dict):
        warnings.append("Backtest metrics payload was not a dictionary; returning an empty metrics block.")
        metrics = {}
    else:
        metrics = dict(raw_metrics)
        forbidden = sorted(key for key in FORBIDDEN_EVIDENCE_KEYS if key in metrics)
        if forbidden:
            warnings.append(
                "Backtest metrics included non-core decision fields: "
                + ", ".join(forbidden)
                + "."
            )

    return {
        "metrics": metrics,
        "evidence_source": "AEGIS_BACKTEST",
        "decision_permission": "EVIDENCE_ONLY_NOT_FINAL",
        "warnings": warnings,
    }
