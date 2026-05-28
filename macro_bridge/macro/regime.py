from macro_bridge.config.settings import BRENT_THRESHOLD, DXY_THRESHOLDS, US10Y_THRESHOLDS, VIX_THRESHOLDS


def detect_regime(dxy: float, us10y: float, vix: float, brent: float, xau: float) -> str:
    """Detects macro regime from key cross-asset indicators."""
    if brent >= BRENT_THRESHOLD and xau >= 2100 and (vix >= 18 or us10y >= 4.2):
        return "stagflation"

    if dxy >= DXY_THRESHOLDS["risk_off"] or vix >= VIX_THRESHOLDS["risk_off"] or us10y >= US10Y_THRESHOLDS["risk_off"]:
        return "risk_off"

    if (
        dxy <= DXY_THRESHOLDS["liquidity_expansion"]
        and vix <= VIX_THRESHOLDS["liquidity_expansion"]
        and us10y <= US10Y_THRESHOLDS["liquidity_expansion"]
    ):
        return "liquidity_expansion"

    return "normalization"
