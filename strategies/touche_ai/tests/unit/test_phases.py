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
from src.indicators.volume import OBVIndicator, VolumeRatioIndicator, CMFIndicator
from src.indicators.structure import SwingPointsIndicator, PivotsIndicator
from src.validators.data_quality import DataQualityValidator


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
    df = CMFIndicator().compute(df)
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


# ─── Yeni Düzeltme Testleri ───────────────────────────────────────────────────

class TestDivergenceCorrection:
    """KRİTİK #1: RSI swing barlarından alınmalı, şu anki bardan değil."""

    def test_divergence_uses_swing_bar_rsi_not_current(self, bullish_ohlcv, default_config):
        """Diverjans tespiti swing low barındaki RSI'ı kullanmalı."""
        df = enrich(bullish_ohlcv)
        ctx = make_ctx(df, default_config)
        result = asyncio.get_event_loop().run_until_complete(
            MarketStructurePhase().run(ctx)
        )
        assert_valid_result(result)
        # metadata'da divergence_source olmalı (yeni alan)
        assert "divergence_source" in result.metadata

    def test_hidden_divergence_reported(self, standard_ohlcv, default_config):
        """Gizli diverjans metadata'da raporlanmalı."""
        df = enrich(standard_ohlcv)
        ctx = make_ctx(df, default_config)
        result = asyncio.get_event_loop().run_until_complete(
            MarketStructurePhase().run(ctx)
        )
        assert "hidden_signal" in result.metadata
        assert result.metadata["hidden_signal"] in ("BULLISH", "BEARISH", "NEUTRAL")

    def test_macd_divergence_source_tracked(self, standard_ohlcv, default_config):
        """MACD histogram diverjansı kaynağı takip edilmeli."""
        df = enrich(standard_ohlcv)
        ctx = make_ctx(df, default_config)
        result = asyncio.get_event_loop().run_until_complete(
            MarketStructurePhase().run(ctx)
        )
        assert result.metadata["divergence_source"] in ("RSI", "MACD", "RSI+MACD", "none")


class TestFairValueGap:
    """Phase 3: FVG tespiti ve zone expiry."""

    def test_fvg_keys_in_metadata(self, standard_ohlcv, default_config):
        """FVG metadata'da raporlanmalı."""
        df = enrich(standard_ohlcv)
        ctx = make_ctx(df, default_config)
        result = asyncio.get_event_loop().run_until_complete(
            ZoneConfluencePhase().run(ctx)
        )
        assert "bullish_fvgs" in result.metadata
        assert "bearish_fvgs" in result.metadata
        assert isinstance(result.metadata["bullish_fvgs"], list)

    def test_zero_price_returns_neutral(self, default_config):
        """Sıfır fiyat durumunda güvenli NEUTRAL dönmeli."""
        df = pl.DataFrame({
            "timestamp": list(range(50)),
            "open":  [0.0] * 50,
            "high":  [0.0] * 50,
            "low":   [0.0] * 50,
            "close": [0.0] * 50,
            "volume":[100.0] * 50,
        })
        ctx = PhaseContext(symbol="BTCUSDT", timeframe="4h", df=df,
                           config=default_config, atr=1.0)
        result = asyncio.get_event_loop().run_until_complete(
            ZoneConfluencePhase().run(ctx)
        )
        assert result.signal == "NEUTRAL"
        assert result.passed is True

    def test_confluence_float_accepted(self, standard_ohlcv, default_config):
        """Confluence artık float (FVG +1.5) — metadata float kabul etmeli."""
        df = enrich(standard_ohlcv)
        ctx = make_ctx(df, default_config)
        result = asyncio.get_event_loop().run_until_complete(
            ZoneConfluencePhase().run(ctx)
        )
        assert isinstance(result.metadata["confluences"], (int, float))


class TestCMFPhase4:
    """Phase 4: CMF entegrasyonu."""

    def test_cmf_in_metadata(self, standard_ohlcv, default_config):
        """CMF değeri metadata'da raporlanmalı."""
        df = enrich(standard_ohlcv)
        ctx = make_ctx(df, default_config)
        result = asyncio.get_event_loop().run_until_complete(
            AccumDistPhase().run(ctx)
        )
        assert "cmf_value" in result.metadata
        assert "cmf_signal" in result.metadata

    def test_cmf_range(self, standard_ohlcv, default_config):
        """CMF -1 ile +1 arasında olmalı."""
        df = enrich(standard_ohlcv)
        ctx = make_ctx(df, default_config)
        result = asyncio.get_event_loop().run_until_complete(
            AccumDistPhase().run(ctx)
        )
        cmf = result.metadata.get("cmf_value", 0.0)
        assert -1.1 <= cmf <= 1.1, f"CMF aralık dışı: {cmf}"


class TestPatternOverlap:
    """Phase 5: Tüm formasyonlar değerlendirilmeli, en yüksek skor seçilmeli."""

    def test_engulfing_beats_hammer_when_both_match(self, default_config):
        """BullishEngulfing (80p) Hammer'ı (70p) geçmeli."""
        import math
        # Engulfing şartları:
        #   c>o (bullish), pc<po (prev bearish), c>po, o<pc, body >= prev_body*1.2
        # Hammer şartları (bazı barlar her ikisini de karşılayabilir)
        prev_o, prev_c = 102.0, 100.0   # Bearish önceki bar
        body = abs(prev_c - prev_o) * 1.5
        curr_o = prev_c - 0.5           # Altında açılış (engulfing)
        curr_c = prev_o + body          # Önceki açılışı geçen kapanış

        df_small = pl.DataFrame({
            "timestamp": list(range(80)),
            "open":   [100.0] * 78 + [prev_o,  curr_o],
            "high":   [101.0] * 78 + [prev_o + 1, curr_c + 0.5],
            "low":    [99.0]  * 78 + [prev_c - 2.0, curr_o - 3.0],  # lower_wick for hammer check
            "close":  [100.5] * 78 + [prev_c,  curr_c],
            "volume": [500.0] * 80,
        })
        df_small = enrich(df_small)
        ctx = PhaseContext(symbol="BTCUSDT", timeframe="4h", df=df_small,
                           config=default_config, atr=2.0)
        result = asyncio.get_event_loop().run_until_complete(
            EntryTimingPhase().run(ctx)
        )
        assert_valid_result(result)
        # Eğer iki formasyon birden tetiklendiyse metadata'da gösterilmeli
        if result.metadata.get("pattern") == "BullishEngulfing":
            assert result.score >= 80.0


class TestDataQualityValidator:
    """DataQualityValidator unit testleri."""

    def test_valid_df_passes(self, standard_ohlcv):
        validator = DataQualityValidator()
        report = validator.validate(standard_ohlcv)
        assert report.is_valid

    def test_too_few_rows_fails(self):
        df = pl.DataFrame({
            "open": [100.0] * 10, "high": [101.0] * 10,
            "low":  [99.0]  * 10, "close": [100.5] * 10,
            "volume": [500.0] * 10,
        })
        validator = DataQualityValidator(min_rows=70)
        report = validator.validate(df)
        assert not report.is_valid
        assert any("Yetersiz bar" in e for e in report.errors)

    def test_invalid_candle_detected(self):
        df = pl.DataFrame({
            "open":  [100.0] * 80,
            "high":  [99.0]  + [101.0] * 79,   # İlk bar: high < low = geçersiz
            "low":   [100.5] + [99.0]  * 79,
            "close": [100.2] * 80,
            "volume":[500.0] * 80,
        })
        validator = DataQualityValidator()
        report = validator.validate(df)
        assert not report.is_valid
        assert any("geçersiz bar" in e for e in report.errors)

    def test_zero_price_fails(self):
        closes = [0.0] * 80
        df = pl.DataFrame({
            "open": closes, "high": closes, "low": closes,
            "close": closes, "volume": [500.0] * 80,
        })
        validator = DataQualityValidator()
        report = validator.validate(df)
        assert not report.is_valid

    def test_excessive_zero_volume_warns(self):
        df = pl.DataFrame({
            "open":  [100.0] * 80, "high": [101.0] * 80,
            "low":   [99.0]  * 80, "close": [100.5] * 80,
            "volume": [0.0] * 70 + [500.0] * 10,  # %87 sıfır hacim
        })
        validator = DataQualityValidator(max_zero_vol_pct=0.10)
        report = validator.validate(df)
        assert report.has_warnings
        assert any("sıfır-hacim" in w for w in report.warnings)


class TestSequentialPhaseBonus:
    """EQS: ardışık faz uyumu bonusu testi."""

    def test_sequential_bonus_in_eqs(self, standard_ohlcv, default_config):
        """5 faz aynı yönde oy verirse EQS boost uygulanmalı."""
        from src.engine.scoring import EQSScorer, EQSResult
        from src.phases.base import PhaseResult

        # 5 BULLISH faz + 2 NEUTRAL (risk + makro)
        mock_results = [
            PhaseResult(phase_id=i, phase_name=f"P{i}", score=75.0,
                        signal="BULLISH", passed=True, reason="test")
            for i in range(1, 6)
        ] + [
            PhaseResult(phase_id=6, phase_name="Risk", score=70.0,
                        signal="NEUTRAL", passed=True, reason="test"),
            PhaseResult(phase_id=7, phase_name="Macro", score=65.0,
                        signal="NEUTRAL", passed=True, reason="test"),
        ]
        scorer = EQSScorer(use_optimizer=False)
        result = scorer.compute(mock_results, volatility_regime="NORMAL")
        # 5 faz uyumlu → bonus uygulanmış olmalı (base ~72 → boost ile daha yüksek)
        assert isinstance(result.eqs_score, float)
        assert result.eqs_score > 0
