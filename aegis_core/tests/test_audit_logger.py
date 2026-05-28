from aegis_core.audit.logger import build_audit_record


def _data_result() -> dict:
    return {
        "status": "PASS",
        "data_quality_score": 96,
        "hard_block": False,
        "warnings": ["data_note"],
        "decision_permission": "DATA_GATE_ONLY_NOT_FINAL",
    }


def _aegis_signal() -> dict:
    return {
        "symbol": "BTC",
        "timeframe": "4h",
        "warnings": ["aegis_note"],
    }


def _brainchain_signal() -> dict:
    return {
        "symbol": "BTC",
        "timeframe": "4h",
        "warnings": ["brainchain_note"],
    }


def _risk_result() -> dict:
    return {
        "status": "PASS",
        "hard_block": False,
        "warnings": ["risk_note"],
        "decision_permission": "RISK_ENGINE_ONLY_NOT_FINAL",
        "final_decision": False,
    }


def _kill_switch_result() -> dict:
    return {
        "status": "OFF",
        "hard_block": False,
        "warnings": ["kill_note"],
        "decision_permission": "KILL_SWITCH_ONLY_NOT_FINAL",
        "final_decision": False,
    }


def _ownerbrief() -> dict:
    return {
        "decision_permission": "NO_EXECUTION_SIGNAL_ONLY",
        "final_decision": False,
        "warnings": ["brief_note"],
    }


def test_audit_record_final_decision_false_and_core_fields_present():
    record = build_audit_record(
        route="/aegis-core/signal",
        request_payload={"symbol": "BTC", "timeframe": "4h"},
        data_integrity_result=_data_result(),
        aegis_signal=_aegis_signal(),
        brainchain_signal=_brainchain_signal(),
        risk_result=_risk_result(),
        kill_switch_result=_kill_switch_result(),
        ownerbrief=_ownerbrief(),
    )
    assert record["final_decision"] is False
    assert record["model_version"] == "aegis_core_7.2"
    assert record["route"] == "/aegis-core/signal"
    assert record["symbol"] == "BTC"
    assert record["timeframe"] == "4h"


def test_audit_record_trace_flags_are_correct():
    record = build_audit_record(
        route="/aegis-core/signal",
        request_payload={"symbol": "BTC", "timeframe": "4h"},
        data_integrity_result=_data_result(),
        aegis_signal=None,
        brainchain_signal=None,
        risk_result=_risk_result(),
        kill_switch_result=_kill_switch_result(),
        ownerbrief=None,
    )
    assert record["trace"]["has_data_integrity_result"] is True
    assert record["trace"]["has_aegis_signal"] is False
    assert record["trace"]["has_brainchain_signal"] is False
    assert record["trace"]["has_risk_result"] is True
    assert record["trace"]["has_kill_switch_result"] is True
    assert record["trace"]["has_ownerbrief"] is False
