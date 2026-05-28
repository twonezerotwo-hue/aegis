from aegis_core.adapters.brainchain_adapter import to_brainchain_signal
from aegis_core.engine.confluence import apply_multi_tf_confluence
from aegis_core.engine.consensus import build_aegis_signal


def test_brainchain_adapter_maps_scores_correctly():
    signal = build_aegis_signal(
        symbol="BTCUSDT",
        timeframe="1h",
        module_scores={
            "touche": 81,
            "fundamental": 64,
            "sentinel": 73,
            "news": 59,
            "quantum": 42,
        },
        raw_regime="NORMALIZATION",
        confluence=apply_multi_tf_confluence(68, {"4h": 75, "1d": 70}),
    )
    adapted = to_brainchain_signal(signal)

    assert adapted["scores"]["technical_score"] == 81.0
    assert adapted["scores"]["fundamental_score"] == 64.0
    assert adapted["scores"]["macro_score"] == 73.0
    assert adapted["scores"]["sentiment_score"] == 59.0
    assert adapted["scores"]["quant_score"] == 42.0


def test_brainchain_adapter_keeps_final_decision_false():
    signal = build_aegis_signal(
        symbol="SOLUSDT",
        timeframe="4h",
        module_scores={"touche": 70, "fundamental": 70, "news": 70},
        raw_regime="ACCUMULATION",
    )
    adapted = to_brainchain_signal(signal)
    assert adapted["final_decision"] is False
    assert adapted["decision_permission"] == "SIGNAL_ONLY_NOT_FINAL"


def test_missing_fields_produce_warnings():
    adapted = to_brainchain_signal({"module_scores": {"touche": 77}})
    assert adapted["warnings"]
    assert any("Missing symbol" in warning for warning in adapted["warnings"])
    assert any(
        "Missing module score for 'fundamental_score'" in warning
        for warning in adapted["warnings"]
    )
