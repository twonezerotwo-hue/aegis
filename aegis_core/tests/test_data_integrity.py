from aegis_core.data.integrity import validate_data_integrity


def _base_payload() -> dict:
    return {
        "source": "provider_name",
        "backup_source": "backup_provider",
        "observation_date": "2026-04-30",
        "release_timestamp": "2026-04-30T15:30:00+03:00",
        "available_timestamp": "2026-04-30T15:31:05+03:00",
        "is_stale": False,
        "fallback_used": False,
        "data_confidence": 0.96,
        "critical_fields_present": True,
    }


def test_missing_data_integrity_returns_degraded_pass_warning():
    result = validate_data_integrity(None)
    assert result["status"] == "DEGRADED_PASS"
    assert result["data_quality_score"] <= 70
    assert "data_integrity_missing" in result["warnings"]


def test_missing_source_returns_fail_hard_block():
    payload = _base_payload()
    payload["source"] = ""
    result = validate_data_integrity(payload)
    assert result["status"] == "FAIL"
    assert result["hard_block"] is True
    assert "source_missing" in result["warnings"]


def test_missing_available_timestamp_returns_fail_hard_block():
    payload = _base_payload()
    payload.pop("available_timestamp")
    result = validate_data_integrity(payload)
    assert result["status"] == "FAIL"
    assert result["hard_block"] is True
    assert "available_timestamp_missing" in result["warnings"]


def test_critical_fields_false_returns_fail_hard_block():
    payload = _base_payload()
    payload["critical_fields_present"] = False
    result = validate_data_integrity(payload)
    assert result["status"] == "FAIL"
    assert result["hard_block"] is True
    assert "critical_fields_missing" in result["warnings"]


def test_fallback_used_reduces_score_and_warns():
    payload = _base_payload()
    payload["fallback_used"] = True
    result = validate_data_integrity(payload)
    assert result["status"] == "DEGRADED_PASS"
    assert result["data_quality_score"] < 96
    assert "fallback_used" in result["warnings"]


def test_stale_data_reduces_score_and_warns():
    payload = _base_payload()
    payload["is_stale"] = True
    result = validate_data_integrity(payload)
    assert result["status"] == "DEGRADED_PASS"
    assert result["data_quality_score"] < 96
    assert "data_is_stale" in result["warnings"]


def test_low_data_confidence_returns_fail_hard_block():
    payload = _base_payload()
    payload["data_confidence"] = 0.49
    result = validate_data_integrity(payload)
    assert result["status"] == "FAIL"
    assert result["hard_block"] is True
    assert "low_data_confidence" in result["warnings"]
