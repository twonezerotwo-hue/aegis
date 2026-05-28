from aegis_core.engine.consensus import build_aegis_signal


def test_consensus_output_has_signal_only_permission():
    signal = build_aegis_signal(
        symbol="BTCUSDT",
        timeframe="1h",
        module_scores={
            "touche": 0.80,
            "fundamental": 72,
            "news": 0.55,
            "sentinel": 40,
            "quantum": 0.20,
        },
        raw_regime="NORMALIZATION",
    )
    assert signal["decision_permission"] == "SIGNAL_ONLY_NOT_FINAL"
    assert signal["final_decision"] is False


def test_consensus_output_has_no_action_and_no_position_size():
    signal = build_aegis_signal(
        symbol="ETHUSDT",
        timeframe="4h",
        module_scores={"technical": 0.75, "fundamental": 0.65},
        raw_regime="RISK_OFF",
    )
    assert "action" not in signal
    assert "position_size" not in signal
