from macro_bridge.macro.regime import detect_regime


def test_detects_risk_off():
    regime = detect_regime(dxy=105.0, us10y=4.2, vix=19.0, brent=85.0, xau=2050.0)
    assert regime == "risk_off"


def test_detects_liquidity_expansion():
    regime = detect_regime(dxy=100.5, us10y=3.8, vix=14.0, brent=78.0, xau=1980.0)
    assert regime == "liquidity_expansion"


def test_detects_stagflation():
    regime = detect_regime(dxy=102.0, us10y=4.3, vix=19.0, brent=101.0, xau=2200.0)
    assert regime == "stagflation"
