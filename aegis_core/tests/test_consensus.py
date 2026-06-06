from aegis_core.engine.consensus import (
    build_aegis_signal,
    calculate_consensus_score,
    normalize_module_scores,
)


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


def test_quantum_signed_conviction_keeps_neutral_distinct_from_bearish():
    bearish = normalize_module_scores({"quantum": -1.5})
    neutral = normalize_module_scores({"quantum": 0.0})
    bullish = normalize_module_scores({"quantum": 1.5})

    assert bearish["quantum"] == 0.0
    assert neutral["quantum"] == 50.0
    assert bullish["quantum"] == 100.0


def test_missing_modules_are_excluded_and_weights_redistributed():
    result = calculate_consensus_score(
        module_scores={"touche": 100, "fundamental": 100, "news": 100},
        weights={
            "touche": 0.30,
            "fundamental": 0.40,
            "news": 0.10,
            "sentinel": 0.15,
            "quantum": 0.05,
        },
    )

    assert result["consensus_status"] == "AVAILABLE"
    assert result["consensus_score"] == 100.0
    assert result["missing_modules"] == ["sentinel", "quantum"]
    assert result["contributions"]["sentinel"]["source"] == "missing_excluded"
    assert result["contributions"]["sentinel"]["score"] is None
    assert all("neutral fallback" not in warning for warning in result["warnings"])


def test_consensus_requires_three_positive_weight_modules():
    result = calculate_consensus_score(
        module_scores={"touche": 100, "fundamental": 100},
        weights={
            "touche": 0.30,
            "fundamental": 0.40,
            "news": 0.10,
            "sentinel": 0.15,
            "quantum": 0.05,
        },
    )

    assert result["consensus_status"] == "INSUFFICIENT_DATA"
    assert result["consensus_available"] is False
    assert result["consensus_score"] is None
    assert result["weights_used"] == {}
