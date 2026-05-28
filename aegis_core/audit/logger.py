"""In-memory audit record builder for AEGIS Core signal flows."""

from __future__ import annotations


def _merge_warnings(*warning_lists: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for warning_list in warning_lists:
        for warning in warning_list or []:
            item = str(warning)
            if item not in seen:
                seen.add(item)
                merged.append(item)
    return merged


def build_audit_record(
    route: str,
    request_payload: dict,
    data_integrity_result: dict | None,
    aegis_signal: dict | None,
    brainchain_signal: dict | None,
    risk_result: dict | None,
    kill_switch_result: dict | None,
    ownerbrief: dict | None,
) -> dict:
    """Build a trace-only audit record without writing to disk."""
    request_payload = request_payload if isinstance(request_payload, dict) else {}

    symbol = request_payload.get("symbol")
    if not symbol and isinstance(aegis_signal, dict):
        symbol = aegis_signal.get("symbol")
    if not symbol and isinstance(brainchain_signal, dict):
        symbol = brainchain_signal.get("symbol")

    timeframe = request_payload.get("timeframe")
    if not timeframe and isinstance(aegis_signal, dict):
        timeframe = aegis_signal.get("timeframe")
    if not timeframe and isinstance(brainchain_signal, dict):
        timeframe = brainchain_signal.get("timeframe")

    warnings = _merge_warnings(
        data_integrity_result.get("warnings", []) if isinstance(data_integrity_result, dict) else [],
        aegis_signal.get("warnings", []) if isinstance(aegis_signal, dict) else [],
        brainchain_signal.get("warnings", []) if isinstance(brainchain_signal, dict) else [],
        risk_result.get("warnings", []) if isinstance(risk_result, dict) else [],
        kill_switch_result.get("warnings", []) if isinstance(kill_switch_result, dict) else [],
        ownerbrief.get("warnings", []) if isinstance(ownerbrief, dict) else [],
    )

    return {
        "audit_type": "AEGIS_CORE_SIGNAL_AUDIT",
        "model_version": "aegis_core_7.2",
        "route": route,
        "symbol": symbol,
        "timeframe": timeframe,
        "data_quality_score": (
            data_integrity_result.get("data_quality_score")
            if isinstance(data_integrity_result, dict)
            else None
        ),
        "data_status": (
            data_integrity_result.get("status")
            if isinstance(data_integrity_result, dict)
            else "UNKNOWN"
        ),
        "risk_status": risk_result.get("status") if isinstance(risk_result, dict) else "UNKNOWN",
        "kill_switch_status": (
            kill_switch_result.get("status") if isinstance(kill_switch_result, dict) else "UNKNOWN"
        ),
        "decision_permission": (
            ownerbrief.get("decision_permission")
            if isinstance(ownerbrief, dict)
            else "NO_EXECUTION_SIGNAL_ONLY"
        ),
        "final_decision": False,
        "source_engine": "AEGIS",
        "warnings": warnings,
        "trace": {
            "has_data_integrity_result": isinstance(data_integrity_result, dict),
            "has_aegis_signal": isinstance(aegis_signal, dict),
            "has_brainchain_signal": isinstance(brainchain_signal, dict),
            "has_risk_result": isinstance(risk_result, dict),
            "has_kill_switch_result": isinstance(kill_switch_result, dict),
            "has_ownerbrief": isinstance(ownerbrief, dict),
        },
    }
