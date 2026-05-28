"""Lightweight kill-switch evaluation for safe AEGIS Core flows."""

from __future__ import annotations


def evaluate_kill_switch(
    data_integrity_result: dict | None,
    risk_result: dict | None,
    kill_switch_context: dict | None = None,
) -> dict:
    """Evaluate whether a non-executing kill switch should block downstream use."""
    warnings: list[str] = []
    status = "OFF"
    hard_block = False

    if not isinstance(kill_switch_context, dict) or not kill_switch_context:
        warnings.append("kill_switch_context_missing")
        kill_switch_context = {}

    if isinstance(data_integrity_result, dict) and data_integrity_result.get("hard_block") is True:
        warnings.append("kill_switch_data_integrity_block")
        status = "ON"
        hard_block = True

    if isinstance(risk_result, dict) and risk_result.get("hard_block") is True:
        warnings.append("kill_switch_risk_engine_block")
        status = "ON"
        hard_block = True

    for key in (
        "manual_kill_switch",
        "broker_api_error",
        "unexpected_correlation_break",
        "backtest_timestamp_violation",
        "system_integrity_error",
    ):
        if bool(kill_switch_context.get(key)):
            warnings.append(key)
            status = "ON"
            hard_block = True

    return {
        "status": status,
        "hard_block": hard_block,
        "warnings": warnings,
        "decision_permission": "KILL_SWITCH_ONLY_NOT_FINAL",
        "final_decision": False,
    }
