"""Lightweight non-final risk evaluation for AEGIS Core signals."""

from __future__ import annotations


FORBIDDEN_FIELDS = {"action", "position_size", "order", "execution", "broker"}


def _coerce_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def evaluate_signal_risk(
    aegis_signal: dict | None,
    brainchain_signal: dict | None,
    data_integrity_result: dict | None,
    risk_context: dict | None = None,
) -> dict:
    """Evaluate post-signal risk without producing any final decision."""
    warnings: list[str] = []
    status = "PASS"
    hard_block = False

    if isinstance(data_integrity_result, dict) and data_integrity_result.get("status") == "FAIL":
        warnings.append("blocked_due_to_data_integrity_fail")
        status = "BLOCK"
        hard_block = True

    if not isinstance(risk_context, dict) or not risk_context:
        warnings.append("risk_context_missing")
        if not hard_block:
            status = "DEGRADED_PASS"
        return {
            "status": status,
            "hard_block": hard_block,
            "warnings": warnings,
            "decision_permission": "RISK_ENGINE_ONLY_NOT_FINAL",
            "final_decision": False,
        }

    contradiction_score = _coerce_float(risk_context.get("contradiction_score"), 0.0)
    portfolio_daily_loss_pct = _coerce_float(risk_context.get("portfolio_daily_loss_pct"), 0.0)
    portfolio_weekly_loss_pct = _coerce_float(risk_context.get("portfolio_weekly_loss_pct"), 0.0)
    max_daily_loss_pct = abs(_coerce_float(risk_context.get("max_daily_loss_pct"), 3.0))
    max_weekly_loss_pct = abs(_coerce_float(risk_context.get("max_weekly_loss_pct"), 7.0))

    if contradiction_score > 70.0:
        warnings.append("contradiction_score_hard_block")
        status = "BLOCK"
        hard_block = True

    if portfolio_daily_loss_pct <= -max_daily_loss_pct:
        warnings.append("daily_loss_limit_hit")
        status = "BLOCK"
        hard_block = True

    if portfolio_weekly_loss_pct <= -max_weekly_loss_pct:
        warnings.append("weekly_loss_limit_hit")
        status = "BLOCK"
        hard_block = True

    if bool(risk_context.get("volatility_spike")):
        warnings.append("volatility_spike")
        if not hard_block and status == "PASS":
            status = "DEGRADED_PASS"

    if bool(risk_context.get("correlation_break")):
        warnings.append("correlation_break")
        status = "BLOCK"
        hard_block = True

    if bool(risk_context.get("stablecoin_depeg")):
        warnings.append("stablecoin_depeg")
        status = "BLOCK"
        hard_block = True

    if bool(risk_context.get("exchange_outage")):
        warnings.append("exchange_outage")
        status = "BLOCK"
        hard_block = True

    if bool(risk_context.get("critical_risk_breach")):
        warnings.append("critical_risk_breach")
        status = "BLOCK"
        hard_block = True

    return {
        "status": status,
        "hard_block": hard_block,
        "warnings": warnings,
        "decision_permission": "RISK_ENGINE_ONLY_NOT_FINAL",
        "final_decision": False,
    }
