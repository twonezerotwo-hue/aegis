from aegis_core.reports.ownerbrief import build_ownerbrief


def _data_result(status: str) -> dict:
    return {
        "status": status,
        "data_quality_score": 96 if status != "FAIL" else 40,
        "hard_block": status == "FAIL",
        "warnings": [],
        "decision_permission": "DATA_GATE_ONLY_NOT_FINAL",
    }


def _risk_result(status: str) -> dict:
    return {
        "status": status,
        "hard_block": status == "BLOCK",
        "warnings": [],
        "decision_permission": "RISK_ENGINE_ONLY_NOT_FINAL",
        "final_decision": False,
    }


def _kill_result(status: str) -> dict:
    return {
        "status": status,
        "hard_block": status == "ON",
        "warnings": [],
        "decision_permission": "KILL_SWITCH_ONLY_NOT_FINAL",
        "final_decision": False,
    }


def _aegis_signal() -> dict:
    return {
        "symbol": "BTC",
        "timeframe": "4h",
        "consensus_score": 66.5,
        "confluence": {"status": "aligned", "multiplier": 1.15, "warnings": []},
        "warnings": [],
    }


def _brainchain_signal() -> dict:
    return {
        "symbol": "BTC",
        "timeframe": "4h",
        "cross_validation": {"passed": True, "method": "multi_tf_confluence", "multiplier": 1.15, "warnings": []},
        "warnings": [],
    }


def _sanitized_text(payload: dict) -> str:
    clean = dict(payload)
    clean["decision_permission"] = ""
    return str(clean).lower()


def test_ownerbrief_final_decision_false_and_permission_fixed():
    brief = build_ownerbrief(
        _aegis_signal(),
        _brainchain_signal(),
        _data_result("PASS"),
        _risk_result("PASS"),
        _kill_result("OFF"),
    )
    assert brief["final_decision"] is False
    assert brief["decision_permission"] == "NO_EXECUTION_SIGNAL_ONLY"


def test_data_integrity_fail_summary_mentions_block():
    brief = build_ownerbrief(
        None,
        None,
        _data_result("FAIL"),
        _risk_result("BLOCK"),
        _kill_result("ON"),
    )
    assert "blocked by data integrity" in brief["summary"].lower()


def test_risk_block_summary_mentions_risk_engine():
    brief = build_ownerbrief(
        _aegis_signal(),
        _brainchain_signal(),
        _data_result("PASS"),
        _risk_result("BLOCK"),
        _kill_result("OFF"),
    )
    assert "blocked by risk engine" in brief["summary"].lower()


def test_kill_switch_on_summary_mentions_kill_switch():
    brief = build_ownerbrief(
        _aegis_signal(),
        _brainchain_signal(),
        _data_result("PASS"),
        _risk_result("PASS"),
        _kill_result("ON"),
    )
    assert "kill switch is on" in brief["summary"].lower()


def test_normal_signal_summary_mentions_signal_only_output():
    brief = build_ownerbrief(
        _aegis_signal(),
        _brainchain_signal(),
        _data_result("PASS"),
        _risk_result("PASS"),
        _kill_result("OFF"),
    )
    assert "signal-only output generated" in brief["summary"].lower()


def test_ownerbrief_avoids_forbidden_fields_and_language():
    brief = build_ownerbrief(
        _aegis_signal(),
        _brainchain_signal(),
        _data_result("PASS"),
        _risk_result("PASS"),
        _kill_result("OFF"),
    )
    assert "action" not in brief
    assert "position_size" not in brief
    sanitized = _sanitized_text(brief)
    for forbidden in ("action", "position_size", "broker", "buy", "sell"):
        assert forbidden not in sanitized
