"""
Touche AI Limited — Pytest Fixtures
Tüm test modülleri tarafından paylaşılan sabit veri ve mock nesneleri.
"""
import os
import sys
import random

import polars as pl
import pytest

# Test modüllerinin src dizinine erişebilmesi için path patch
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../")))

# ─── OHLCV Test Verisi ────────────────────────────────────────────────────────

def _make_ohlcv(n: int, seed: int = 42, start_price: float = 30_000.0) -> pl.DataFrame:
    """
    n bar OHLCV test verisi üretir.
    random.seed ile tekrar edilebilir sonuçlar garanti altına alınır.
    """
    random.seed(seed)
    closes = [start_price]
    for _ in range(n - 1):
        pct = random.gauss(0.0002, 0.015)  # Hafif bullish bias
        closes.append(max(100.0, closes[-1] * (1 + pct)))

    opens  = [c * (1 + random.uniform(-0.003, 0.003)) for c in closes]
    highs  = [max(o, c) * (1 + random.uniform(0.0, 0.008)) for o, c in zip(opens, closes)]
    lows   = [min(o, c) * (1 - random.uniform(0.0, 0.008)) for o, c in zip(opens, closes)]
    vols   = [random.uniform(500, 5000) for _ in range(n)]

    return pl.DataFrame({
        "timestamp": list(range(n)),
        "open":   opens,
        "high":   highs,
        "low":    lows,
        "close":  closes,
        "volume": vols,
    })


@pytest.fixture
def small_ohlcv() -> pl.DataFrame:
    """50 bar — minimum gereksinim testleri için."""
    return _make_ohlcv(50)


@pytest.fixture
def standard_ohlcv() -> pl.DataFrame:
    """200 bar — normal indikatör ve faz testleri için."""
    return _make_ohlcv(200)


@pytest.fixture
def large_ohlcv() -> pl.DataFrame:
    """500 bar — entegrasyon ve performans testleri için."""
    return _make_ohlcv(500)


@pytest.fixture
def bullish_ohlcv() -> pl.DataFrame:
    """Belirgin yükseliş trendi — bullish sinyal testleri için."""
    random.seed(99)
    n = 200
    closes = [10_000.0]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1 + random.uniform(0.005, 0.020)))  # Her bar +0.5-2%

    opens  = [c * 0.998 for c in closes]
    highs  = [c * (1 + random.uniform(0.003, 0.010)) for c in closes]
    lows   = [c * (1 - random.uniform(0.001, 0.005)) for c in closes]
    vols   = [random.uniform(2000, 8000) for _ in range(n)]

    return pl.DataFrame({
        "timestamp": list(range(n)),
        "open": opens, "high": highs, "low": lows, "close": closes, "volume": vols,
    })


@pytest.fixture
def bearish_ohlcv() -> pl.DataFrame:
    """Belirgin düşüş trendi — bearish sinyal testleri için."""
    random.seed(77)
    n = 200
    closes = [50_000.0]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1 - random.uniform(0.005, 0.018)))

    opens  = [c * 1.002 for c in closes]
    highs  = [c * (1 + random.uniform(0.001, 0.005)) for c in closes]
    lows   = [c * (1 - random.uniform(0.003, 0.010)) for c in closes]
    vols   = [random.uniform(2000, 8000) for _ in range(n)]

    return pl.DataFrame({
        "timestamp": list(range(n)),
        "open": opens, "high": highs, "low": lows, "close": closes, "volume": vols,
    })


@pytest.fixture
def mock_redis(mocker):
    """Redis bağlantısını sanallaştırır (tüm çağrıları engeller)."""
    return mocker.AsyncMock()


@pytest.fixture
def default_config() -> dict:
    """Standart strateji konfigürasyonu (YAML yerine dict olarak)."""
    return {
        "indicators": {
            "rsi": {"period": 14},
            "stoch_rsi": {"rsi_period": 14, "stoch_period": 14, "smooth_k": 3, "smooth_d": 3},
            "macd": {"fast": 12, "slow": 26, "signal": 9},
            "adx": {"period": 14, "strong_trend_threshold": 25},
            "ema": {"fast": 20, "slow": 50, "trend": 200},
            "atr": {"period": 14},
            "bollinger": {"period": 20, "std_dev": 2.0},
            "volume_ratio": {"period": 20},
            "swing_points": {"lookback": 5},
        },
        "phases": {
            "phase1_liquidity": {"sweep_atr_threshold": 0.5, "min_wick_body_ratio": 0.6, "lookback_bars": 20},
            "phase2_structure": {"swing_lookback": 5, "divergence_lookback": 10, "min_swing_points": 2},
            "phase3_zones":     {"zone_tolerance_atr": 0.3, "confluence_min": 2},
            "phase4_confirm":   {"volume_ratio_threshold": 1.5, "lookback_bars": 10, "obv_trend_bars": 5},
            "phase5_timing":    {"engulfing_ratio": 1.2, "pin_bar_wick_ratio": 0.65, "doji_body_ratio": 0.1},
            "phase6_risk":      {"sl_atr_multiplier": 1.5, "min_rr_ratio": 1.5, "max_rr_ratio": 10.0, "tp_rr_ratio": 2.0},
            "phase7_macro":     {"fundamental_block_threshold": 30.0, "fundamental_boost_threshold": 70.0},
        },
        "scoring": {
            "weights": {"phase1": 0.15, "phase2": 0.20, "phase3": 0.20,
                        "phase4": 0.15, "phase5": 0.15, "phase6": 0.05, "phase7": 0.10},
            "thresholds": {"strong_signal": 75, "weak_signal": 50, "no_trade": 40},
        },
    }
