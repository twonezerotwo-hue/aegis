from aegis_core.risk.risk_engine import evaluate_signal_risk


def _passing_data_integrity() -> dict:
    return {
        "status": "PASS",
        "data_quality_score": 96,
        "hard_block": False,
        "warnings": [],
        "decision_permission": "DATA_GATE_ONLY_NOT_FINAL",
    }


def _base_risk_context() -> dict:
    return {
        "contradiction_score": 25,
        "portfolio_daily_loss_pct": 0.0,
        "portfolio_weekly_loss_pct": 0.0,
        "max_daily_loss_pct": 3.0,
        "max_weekly_loss_pct": 7.0,
        "volatility_spike": False,
        "correlation_break": False,
        "stablecoin_depeg": False,
        "exchange_outage": False,
        "critical_risk_breach": False,
    }


def test_missing_risk_context_returns_degraded_pass_warning():
    result = evaluate_signal_risk(None, None, _passing_data_integrity(), None)
    assert result["status"] == "DEGRADED_PASS"
    assert result["hard_block"] is False
    assert "risk_context_missing" in result["warnings"]


def test_contradiction_score_above_70_blocks():
    context = _base_risk_context()
    context["contradiction_score"] = 71
    result = evaluate_signal_risk(None, None, _passing_data_integrity(), context)
    assert result["status"] == "BLOCK"
    assert result["hard_block"] is True
    assert "contradiction_score_hard_block" in result["warnings"]


def test_daily_loss_breach_blocks():
    context = _base_risk_context()
    context["portfolio_daily_loss_pct"] = -3.0
    result = evaluate_signal_risk(None, None, _passing_data_integrity(), context)
    assert result["status"] == "BLOCK"
    assert result["hard_block"] is True
    assert "daily_loss_limit_hit" in result["warnings"]


def test_weekly_loss_breach_blocks():
    context = _base_risk_context()
    context["portfolio_weekly_loss_pct"] = -7.0
    result = evaluate_signal_risk(None, None, _passing_data_integrity(), context)
    assert result["status"] == "BLOCK"
    assert result["hard_block"] is True
    assert "weekly_loss_limit_hit" in result["warnings"]


def test_volatility_spike_degrades_without_hard_block():
    context = _base_risk_context()
    context["volatility_spike"] = True
    result = evaluate_signal_risk(None, None, _passing_data_integrity(), context)
    assert result["status"] == "DEGRADED_PASS"
    assert result["hard_block"] is False
    assert "volatility_spike" in result["warnings"]


def test_stablecoin_depeg_blocks():
    context = _base_risk_context()
    context["stablecoin_depeg"] = True
    result = evaluate_signal_risk(None, None, _passing_data_integrity(), context)
    assert result["status"] == "BLOCK"
    assert result["hard_block"] is True
    assert "stablecoin_depeg" in result["warnings"]


def test_exchange_outage_blocks_and_risk_output_stays_non_final():
    context = _base_risk_context()
    context["exchange_outage"] = True
    result = evaluate_signal_risk(None, None, _passing_data_integrity(), context)
    assert result["status"] == "BLOCK"
    assert result["hard_block"] is True
    assert "exchange_outage" in result["warnings"]
    assert result["final_decision"] is False
    for forbidden in ("action", "position_size", "order", "execution", "broker"):
        assert forbidden not in result
