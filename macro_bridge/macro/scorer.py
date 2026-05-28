from macro_bridge.utils.helpers import clamp


def _scale_inverse(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    ratio = (value - low) / (high - low)
    return clamp(1.0 - (2.0 * ratio), -1.0, 1.0)


def _scale_direct(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    ratio = (value - low) / (high - low)
    return clamp((2.0 * ratio) - 1.0, -1.0, 1.0)


def _scale_center(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    mid = (low + high) / 2.0
    half = (high - low) / 2.0
    if half == 0:
        return 0.0
    return clamp(1.0 - abs(value - mid) / half, -1.0, 1.0)


def calculate_score(dxy: float, us10y: float, btc_d: float, usdt_d: float, hg: float, vix: float) -> float:
    """Returns a macro score in range [-1, 1]."""
    liquidity = (_scale_inverse(dxy, 99.0, 106.0) + _scale_inverse(us10y, 3.4, 5.0)) / 2.0
    crypto_structure = (_scale_center(btc_d, 46.0, 60.0) + _scale_inverse(usdt_d, 2.5, 8.0)) / 2.0
    real_economy = _scale_direct(hg, 3.0, 4.8)
    volatility = _scale_inverse(vix, 12.0, 32.0)

    score = (liquidity * 0.35) + (crypto_structure * 0.30) + (real_economy * 0.20) + (volatility * 0.15)
    return clamp(score, -1.0, 1.0)
