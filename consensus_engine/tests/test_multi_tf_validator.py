from consensus_engine.src.multi_tf_validator import MultiTFValidator


validator = MultiTFValidator()


def test_opposite_1h_and_4h_forces_hold():
    result = validator.validate({"15m": "BUY", "1h": "BUY", "4h": "SELL", "1d": "BUY"})

    assert result.is_valid is False
    assert result.final_signal == "HOLD"


def test_15m_cannot_override_neutral_1h():
    result = validator.validate({"15m": "BUY", "1h": "HOLD", "4h": "BUY", "1d": "BUY"})

    assert result.is_valid is False
    assert result.final_signal == "HOLD"


def test_15m_only_refines_entry_timing():
    result = validator.validate({"15m": "SELL", "1h": "BUY", "4h": "BUY", "1d": "BUY"})

    assert result.is_valid is True
    assert result.final_signal == "BUY"
    assert "entry timing" in result.reason
