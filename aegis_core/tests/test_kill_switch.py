from aegis_core.risk.kill_switch import evaluate_kill_switch


def _passing_data_integrity() -> dict:
    return {
        "status": "PASS",
        "data_quality_score": 96,
        "hard_block": False,
        "warnings": [],
        "decision_permission": "DATA_GATE_ONLY_NOT_FINAL",
    }


def _failing_data_integrity() -> dict:
    return {
        "status": "FAIL",
        "data_quality_score": 40,
        "hard_block": True,
        "warnings": ["source_missing"],
        "decision_permission": "DATA_GATE_ONLY_NOT_FINAL",
    }


def _passing_risk_result() -> dict:
    return {
        "status": "PASS",
        "hard_block": False,
        "warnings": [],
        "decision_permission": "RISK_ENGINE_ONLY_NOT_FINAL",
        "final_decision": False,
    }


def test_data_integrity_fail_causes_kill_switch_on():
    result = evaluate_kill_switch(_failing_data_integrity(), _passing_risk_result(), None)
    assert result["status"] == "ON"
    assert result["hard_block"] is True
    assert "kill_switch_data_integrity_block" in result["warnings"]


def test_manual_kill_switch_causes_on():
    result = evaluate_kill_switch(
        _passing_data_integrity(),
        _passing_risk_result(),
        {"manual_kill_switch": True},
    )
    assert result["status"] == "ON"
    assert result["hard_block"] is True
    assert "manual_kill_switch" in result["warnings"]


def test_kill_switch_output_stays_non_final_and_has_no_execution_fields():
    result = evaluate_kill_switch(_passing_data_integrity(), _passing_risk_result(), {})
    assert result["status"] == "OFF"
    assert result["final_decision"] is False
    for forbidden in ("action", "position_size", "order", "execution", "broker"):
        assert forbidden not in result
