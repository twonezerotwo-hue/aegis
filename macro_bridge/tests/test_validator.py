from macro_bridge.aegis.validator import validate_signal


def test_strong_buy_when_macro_and_aegis_align():
    out = validate_signal(0.5, "BUY")
    assert out["combined_decision"] == "GUCLU_AL"
    assert out["conflict"] is False


def test_conflict_on_negative_macro_buy_signal():
    out = validate_signal(-0.3, "BUY")
    assert out["combined_decision"] == "CELISKI_POZISYON_KUCULT"
    assert out["conflict"] is True
