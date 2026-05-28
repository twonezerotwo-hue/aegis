"""Owner-facing non-final explanation wrapper for AEGIS Core."""

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


def build_ownerbrief(
    aegis_signal: dict | None,
    brainchain_signal: dict | None,
    data_integrity_result: dict | None,
    risk_result: dict | None,
    kill_switch_result: dict | None,
    request_context: dict | None = None,
) -> dict:
    """Build a non-executing owner brief for downstream review."""
    warnings: list[str] = []
    strongest_confirmations: list[str] = []
    main_contradictions: list[str] = []
    risk_notes: list[str] = []
    what_would_change_this: list[str] = []

    if not isinstance(data_integrity_result, dict):
        warnings.append("ownerbrief_missing_data_integrity_result")
        data_status = "UNKNOWN"
    else:
        data_status = str(data_integrity_result.get("status", "UNKNOWN"))

    if not isinstance(risk_result, dict):
        warnings.append("ownerbrief_missing_risk_result")
        risk_status = "UNKNOWN"
    else:
        risk_status = str(risk_result.get("status", "UNKNOWN"))

    if not isinstance(kill_switch_result, dict):
        warnings.append("ownerbrief_missing_kill_switch_result")
        kill_switch = "UNKNOWN"
    else:
        kill_switch = "ON" if str(kill_switch_result.get("status", "OFF")).upper() == "ON" else "OFF"

    if not isinstance(aegis_signal, dict):
        warnings.append("ownerbrief_missing_aegis_signal")
    else:
        consensus_score = aegis_signal.get("consensus_score")
        if isinstance(consensus_score, (int, float)) and float(consensus_score) >= 60.0:
            strongest_confirmations.append(
                f"Consensus score remained firm at {float(consensus_score):.2f}."
            )

        confluence = aegis_signal.get("confluence")
        if isinstance(confluence, dict):
            status = str(confluence.get("status", "unknown")).lower()
            multiplier = confluence.get("multiplier", 1.0)
            if status == "aligned":
                strongest_confirmations.append(
                    f"Multi-timeframe confluence aligned with multiplier {float(multiplier):.2f}."
                )
            elif status in {"mixed", "opposing"}:
                main_contradictions.append(
                    f"Multi-timeframe confluence is {status} with multiplier {float(multiplier):.2f}."
                )

    if not isinstance(brainchain_signal, dict):
        warnings.append("ownerbrief_missing_brainchain_signal")
    else:
        cross_validation = brainchain_signal.get("cross_validation")
        if isinstance(cross_validation, dict) and cross_validation.get("passed") is True:
            strongest_confirmations.append("Cross-validation remained supportive.")
        elif isinstance(cross_validation, dict):
            main_contradictions.append("Cross-validation did not fully confirm the signal context.")

    if data_status == "PASS":
        strongest_confirmations.append("Data integrity checks passed.")
    elif data_status == "DEGRADED_PASS":
        risk_notes.append("Data integrity was degraded and should be reviewed with the warnings.")

    if risk_status == "PASS":
        strongest_confirmations.append("Risk wrapper reported no active block conditions.")
    elif risk_status == "DEGRADED_PASS":
        risk_notes.append("Risk wrapper reported degraded conditions without a hard block.")
    elif risk_status == "BLOCK":
        risk_notes.append("Risk wrapper reported a hard block condition.")

    if kill_switch == "ON":
        risk_notes.append("Kill switch remains ON and downstream handling must stay blocked.")
    elif kill_switch == "OFF":
        strongest_confirmations.append("Kill switch remains OFF.")

    if data_status == "FAIL":
        summary = "Signal blocked by data integrity review; downstream use should pause until metadata is corrected."
    elif risk_status == "BLOCK":
        summary = "Signal blocked by risk engine review; downstream use should pause until risk conditions normalize."
    elif kill_switch == "ON":
        summary = "Kill switch is ON; signal-only output is recorded for review but remains blocked from downstream use."
    else:
        summary = "Signal-only output generated for downstream review with no final authority."

    what_would_change_this.extend(
        [
            "Improved data completeness or freshness could reduce current warnings.",
            "Lower contradiction and loss metrics would improve downstream confidence.",
            "Clearing kill-switch triggers would reopen downstream review pathways.",
        ]
    )

    warnings = _merge_warnings(
        warnings,
        data_integrity_result.get("warnings", []) if isinstance(data_integrity_result, dict) else [],
        risk_result.get("warnings", []) if isinstance(risk_result, dict) else [],
        kill_switch_result.get("warnings", []) if isinstance(kill_switch_result, dict) else [],
        aegis_signal.get("warnings", []) if isinstance(aegis_signal, dict) else [],
        brainchain_signal.get("warnings", []) if isinstance(brainchain_signal, dict) else [],
    )

    return {
        "brief_type": "AEGIS_CORE_OWNERBRIEF",
        "mode": "AEGIS_CORE_SIGNAL_ONLY",
        "data_status": data_status,
        "risk_status": risk_status,
        "kill_switch": kill_switch,
        "decision_permission": "NO_EXECUTION_SIGNAL_ONLY",
        "final_decision": False,
        "summary": summary,
        "strongest_confirmations": strongest_confirmations,
        "main_contradictions": main_contradictions,
        "risk_notes": risk_notes,
        "what_would_change_this": what_would_change_this,
        "warnings": warnings,
    }
