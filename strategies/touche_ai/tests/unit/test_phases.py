"""
Touche AI Limited — Birim Testler: 7 Faz

Her faz için:
  - PhaseResult dönüş tipini doğrula
  - Skor 0-100 aralığında olmalı
  - signal BULLISH/BEARISH/NEUTRAL'den biri olmalı
  - Hatalı / yetersiz veride çökmemeli (graceful fallback)
"""
import asyncio
import polars as pl

from src.phases.base import PhaseContext, PhaseResult
from src.phases.phase1_liquidity import LiquiditySweepPhase
from src.phases.phase2_structure import MarketStructurePhase
from src.phases.phase3_zones import ZoneConfluencePhase
from src.phases.phase4_confirm import AccumDistPhase
from src.phases.phase5_timing import EntryTimingPhase
from src.phases.phase6_risk import RiskManagementPhase
from src.phases.phase7_macro import MacroFilterPhase

from src.indicators.momentum import RSIIndicator, StochRSIIndicator, MACDIndicator
from src.indicators.trend import ADXIndicator, EMAIndicator
from src.indicators.volatility import ATRIndicator, BollingerIndicator
from src.indicators.volume import OBVIndicator, VolumeRatioIndicator
from src.indicators.structure import SwingPointsIndicator, PivotsIndicator


# ─── Yardımcı: Tam Zenginleştirilmiş DataFrame ────────────────────────────────

def enrich(df: pl.DataFrame) -> pl.DataFrame:
    """Tüm indikatörleri uygular; testlerde gerçekçi bir DataFrame sağlar."""
    df = RSIIndicator(14).compute(df)
    df = StochRSIIndicator().compute(df)
    df = MACDIndicator().compute(df)
    df = ADXIndicator().compute(df)
    df = EMAIndicator().compute(df)
    df = ATRIndicator().compute(df)
    df = BollingerIndicator().compute(df)
    df = OBVIndicator().compute(df)
    df = VolumeRatioIndicator().compute(df)
    df = SwingPointsIndicator().compute(df)
    df = PivotsIndicator().compute(df)
    return df


def make_ctx(df: pl.DataFrame, config: dict, fundamental: float = None,
             direction: str = "BULLISH") -> PhaseContext:
    atr = float(df["atr_14"][-1]) if "atr_14" in df.columns else 150.0
    return PhaseContext(
        symbol="BTCUSDT",
        timeframe="4h",
        df=df,
        config=config,
        atr=atr,
        fundamental_score=fundamental,
        direction_hint=direction,
    )


# ─── Yardımcı: PhaseResult doğrulama ─────────────────────────────────────────

def assert_valid_result(result: PhaseResult):
    assert isinstance(result, PhaseResult)
    assert 0.0 <= result.score <= 100.0, f"Skor aralık dışı: {result.score}"
    assert result.signal in ("BULLISH", "BEARISH", "NEUTRAL"), f"Geçersiz sinyal: {result.signal}"
    assert isinstance(result.passed, bool)
    assert isinstance(result.reason, str) and len(result.reason) > 0


# ─── Faz 1: Likidite Süpürmesi ────────────────────────────────────────────────

class TestPhase1Liquidity:
    def test_returns_valid_result(self, standard_ohlcv, default_config):
        df = enrich(standard_ohlcv)
        ctx = make_ctx(df, default_config)
        result = asyncio.get_event_loop().run_until_complete(
            LiquiditySweepPhase().run(ctx)
        )
        assert_valid_result(result)
        assert result.phase_id == 1

    def test_graceful_on_missing_swing_columns(self, default_config):
        """swing_high_price sütunu yoksa çökmemeli."""
        df = pl.DataFrame({
            "timestamp": list(range(50)),
            "open":  [100.0] * 50,
            "high":  [101.0] * 50,
            "low":   [99.0]  * 50,
            "close": [100.5] * 50,
            "volume":[500.0] * 50,
        })
        ctx = PhaseContext(symbol="BTCUSDT", timeframe="4h", df=df,
                           config=default_config, atr=1.0)
        result = asyncio.get_event_loop().run_until_complete(
            LiquiditySweepPhase().run(ctx)
        )
        assert_valid_result(result)

    def test_metadata_present(self, standard_ohlcv, default_config):
        df = enrich(standard_ohlcv)
        ctx = make_ctx(df, default_config)
        result = asyncio.get_event_loop().run_until_complete(
            LiquiditySweepPhase().run(ctx)
        )
        assert "atr" in result.metadata


# ─── Faz 2: Piyasa Yapısı ─────────────────────────────────────────────────────

class TestPhase2Structure:
    def test_returns_valid_result(self, standard_ohlcv, default_config):
        df = enrich(standard_ohlcv)
        ctx = make_ctx(df, default_config)
        result = asyncio.get_event_loop().run_until_complete(
            MarketStructurePhase().run(ctx)
        )
        assert_valid_result(result)
        assert result.phase_id == 2

    def test_bullish_market_bullish_or_neutral(self, bullish_ohlcv, default_config):
        df = enrich(bullish_ohlcv)
        ctx = make_ctx(df, default_config)
        result = asyncio.get_event_loop().run_until_complete(
            MarketStructurePhase().run(ctx)
        )
        assert result.signal in ("BULLISH", "NEUTRAL")

    def test_bearish_market_bearish_or_neutral(self, bearish_ohlcv, default_config):
        df = enrich(bearish_ohlcv)
        ctx = make_ctx(df, default_config)
        result = asyncio.get_event_loop().run_until_complete(
            MarketStructurePhase().run(ctx)
        )
        assert result.signal in ("BEARISH", "NEUTRAL")


# ─── Faz 3: Bölgeler + Confluence ─────────────────────────────────────────────

class TestPhase3Zones:
    def test_returns_valid_result(self, standard_ohlcv, default_config):
        df = enrich(standard_ohlcv)
        ctx = make_ctx(df, default_config)
        result = asyncio.get_event_loop().run_until_complete(
            ZoneConfluencePhase().run(ctx)
        )
        assert_valid_result(result)
        assert result.phase_id == 3

    def test_metadata_has_confluences(self, standard_ohlcv, default_config):
        df = enrich(standard_ohlcv)
        ctx = make_ctx(df, default_config)
        result = asyncio.get_event_loop().run_until_complete(
            ZoneConfluencePhase().run(ctx)
        )
        assert "confluences" in result.metadata
        assert isinstance(result.metadata["confluences"], int)


# ─── Faz 4: Teyit ────────────────────────────────────────────────────────────

class TestPhase4Confirm:
    def test_returns_valid_result(self, standard_ohlcv, default_config):
        df = enrich(standard_ohlcv)
        ctx = make_ctx(df, default_config)
        result = asyncio.get_event_loop().run_until_complete(
            AccumDistPhase().run(ctx)
        )
        assert_valid_result(result)
        assert result.phase_id == 4

    def test_metadata_has_vol_ratio(self, standard_ohlcv, default_config):
        df = enrich(standard_ohlcv)
        ctx = make_ctx(df, default_config)
        result = asyncio.get_event_loop().run_until_complete(
            AccumDistPhase().run(ctx)
        )
        assert "vol_ratio" in result.metadata


# ─── Faz 5: Giriş Zamanlaması ────────────────────────────────────────────────

class TestPhase5Timing:
    def test_returns_valid_result(self, standard_ohlcv, default_config):
        df = enrich(standard_ohlcv)
        ctx = make_ctx(df, default_config)
        result = asyncio.get_event_loop().run_until_complete(
            EntryTimingPhase().run(ctx)
        )
        assert_valid_result(result)
        assert result.phase_id == 5

    def test_metadata_has_pattern(self, standard_ohlcv, default_config):
        df = enrich(standard_ohlcv)
        ctx = make_ctx(df, default_config)
        result = asyncio.get_event_loop().run_until_complete(
            EntryTimingPhase().run(ctx)
        )
        assert "pattern" in result.metadata


# ─── Faz 6: Risk Yönetimi ─────────────────────────────────────────────────────

class TestPhase6Risk:
    def test_bullish_direction_sl_below_price(self, standard_ohlcv, default_config):
        df = enrich(standard_ohlcv)
        ctx = make_ctx(df, default_config, direction="BULLISH")
        result = asyncio.get_event_loop().run_until_complete(
            RiskManagementPhase().run(ctx)
        )
        assert_valid_result(result)
        if result.passed:
            current = float(df["close"][-1])
            assert result.metadata["stop_loss"] < current, "Bullish SL fiyatın altında olmalı"
            assert result.metadata["take_profit"] > current, "Bullish TP fiyatın üstünde olmalı"

    def test_neutral_direction_blocked(self, standard_ohlcv, default_config):
        """Yön belirsizse Faz6 passed=False dönmeli."""
        df = enrich(standard_ohlcv)
        ctx = make_ctx(df, default_config, direction="NEUTRAL")
        result = asyncio.get_event_loop().run_until_complete(
            RiskManagementPhase().run(ctx)
        )
        assert result.passed is False

    def test_rr_ratio_in_metadata(self, standard_ohlcv, default_config):
        df = enrich(standard_ohlcv)
        ctx = make_ctx(df, default_config, direction="BULLISH")
        result = asyncio.get_event_loop().run_until_complete(
            RiskManagementPhase().run(ctx)
        )
        if result.passed:
            assert "rr_ratio" in result.metadata
            assert result.metadata["rr_ratio"] >= 1.5


# ─── Faz 7: Makro Filtre ──────────────────────────────────────────────────────

class TestPhase7Macro:
    def test_low_fundamental_blocks(self, standard_ohlcv, default_config):
        """Fundamental < 30 → passed=False."""
        df = enrich(standard_ohlcv)
        ctx = make_ctx(df, default_config, fundamental=15.0)
        result = asyncio.get_event_loop().run_until_complete(
            MacroFilterPhase().run(ctx)
        )
        assert result.passed is False
        assert result.score == 0.0

    def test_high_fundamental_boost(self, standard_ohlcv, default_config):
        """Fundamental > 70 → BULLISH sinyal ve yüksek skor."""
        df = enrich(standard_ohlcv)
        ctx = make_ctx(df, default_config, fundamental=85.0)
        result = asyncio.get_event_loop().run_until_complete(
            MacroFilterPhase().run(ctx)
        )
        assert result.passed is True
        assert result.signal == "BULLISH"
        assert result.score > 60.0

    def test_none_fundamental_neutral(self, standard_ohlcv, default_config):
        """Fundamental=None → NEUTRAL, passed=True (pipeline devam eder)."""
        df = enrich(standard_ohlcv)
        ctx = make_ctx(df, default_config, fundamental=None)
        result = asyncio.get_event_loop().run_until_complete(
            MacroFilterPhase().run(ctx)
        )
        assert result.passed is True
        assert result.signal == "NEUTRAL"
        assert result.score == 50.0

    def test_returns_valid_result(self, standard_ohlcv, default_config):
        df = enrich(standard_ohlcv)
        ctx = make_ctx(df, default_config, fundamental=60.0)
        result = asyncio.get_event_loop().run_until_complete(
            MacroFilterPhase().run(ctx)
        )
        assert_valid_result(result)
        assert result.phase_id == 7
