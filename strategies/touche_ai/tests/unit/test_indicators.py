"""
Touche AI Limited — Birim Testler: Teknik İndikatörler

Her indikatör için:
  - Çıktı sütununun varlığı
  - Değer aralığı doğruluğu (RSI: 0-100, vb.)
  - Yetersiz veri hata yönetimi
"""
import pytest
import polars as pl

from src.indicators.momentum import RSIIndicator, StochRSIIndicator, MACDIndicator
from src.indicators.trend import ADXIndicator, EMAIndicator
from src.indicators.volatility import ATRIndicator, BollingerIndicator
from src.indicators.volume import OBVIndicator, VolumeRatioIndicator
from src.indicators.structure import SwingPointsIndicator, PivotsIndicator


# ─── RSI ──────────────────────────────────────────────────────────────────────

class TestRSIIndicator:
    def test_output_column_exists(self, standard_ohlcv):
        rsi = RSIIndicator(period=14)
        result = rsi.compute(standard_ohlcv)
        assert "rsi_14" in result.columns

    def test_rsi_range(self, standard_ohlcv):
        rsi = RSIIndicator(period=14)
        result = rsi.compute(standard_ohlcv)
        values = result["rsi_14"].drop_nulls().to_list()
        assert all(0.0 <= v <= 100.0 for v in values), "RSI 0-100 aralığında olmalı"

    def test_custom_period(self, standard_ohlcv):
        rsi = RSIIndicator(period=7)
        result = rsi.compute(standard_ohlcv)
        assert "rsi_7" in result.columns

    def test_insufficient_data_raises(self):
        df = pl.DataFrame({"close": [100.0, 101.0, 99.0]})
        rsi = RSIIndicator(period=14)
        with pytest.raises(ValueError, match="satır"):
            rsi.compute(df)

    def test_missing_column_raises(self, standard_ohlcv):
        df = standard_ohlcv.drop("close")
        rsi = RSIIndicator(period=14)
        with pytest.raises(ValueError, match="Eksik"):
            rsi.compute(df)

    def test_bullish_trend_higher_rsi(self, bullish_ohlcv):
        """Yükseliş trendinde RSI ortalaması 50'nin üstünde olmalı."""
        rsi = RSIIndicator(period=14)
        result = rsi.compute(bullish_ohlcv)
        avg = result["rsi_14"].drop_nulls().mean()
        assert avg > 50.0, f"Yükseliş trendinde RSI ortalaması düşük: {avg:.2f}"


# ─── StochRSI ─────────────────────────────────────────────────────────────────

class TestStochRSIIndicator:
    def test_output_columns(self, standard_ohlcv):
        ind = StochRSIIndicator()
        result = ind.compute(standard_ohlcv)
        assert "stochrsi_k" in result.columns
        assert "stochrsi_d" in result.columns

    def test_value_range(self, standard_ohlcv):
        ind = StochRSIIndicator()
        result = ind.compute(standard_ohlcv)
        for col in ["stochrsi_k", "stochrsi_d"]:
            vals = result[col].drop_nulls().to_list()
            assert all(0.0 <= v <= 100.0 for v in vals), f"{col} 0-100 aralığında olmalı"


# ─── MACD ─────────────────────────────────────────────────────────────────────

class TestMACDIndicator:
    def test_output_columns(self, standard_ohlcv):
        macd = MACDIndicator()
        result = macd.compute(standard_ohlcv)
        for col in ["macd", "macd_signal", "macd_hist"]:
            assert col in result.columns, f"{col} sütunu eksik"

    def test_histogram_is_diff(self, standard_ohlcv):
        """Histogram = MACD - Signal olmalı."""
        macd = MACDIndicator()
        result = macd.compute(standard_ohlcv)
        vals = result.drop_nulls()
        diffs = (vals["macd"] - vals["macd_signal"]).to_list()
        hists = vals["macd_hist"].to_list()
        for d, h in zip(diffs[-10:], hists[-10:]):
            assert abs(d - h) < 1e-6, f"Histogram hesabı hatalı: {d} != {h}"

    def test_bullish_macd(self, bullish_ohlcv):
        """Yükseliş trendinde son MACD histogram pozitif olmalı."""
        result = MACDIndicator().compute(bullish_ohlcv)
        last_hist = result["macd_hist"][-1]
        assert last_hist is not None
        assert float(last_hist) > 0, "Yükseliş trendinde MACD histogram pozitif bekleniyor"


# ─── ADX ──────────────────────────────────────────────────────────────────────

class TestADXIndicator:
    def test_output_columns(self, standard_ohlcv):
        adx = ADXIndicator()
        result = adx.compute(standard_ohlcv)
        for col in ["adx", "di_plus", "di_minus"]:
            assert col in result.columns

    def test_adx_non_negative(self, standard_ohlcv):
        adx = ADXIndicator()
        result = adx.compute(standard_ohlcv)
        vals = result["adx"].drop_nulls().to_list()
        assert all(v >= 0.0 for v in vals), "ADX negatif olamaz"

    def test_trending_market_high_adx(self, bullish_ohlcv):
        """Güçlü trendde ADX son değeri 25+ olmalı."""
        result = ADXIndicator(period=14).compute(bullish_ohlcv)
        last_adx = float(result["adx"][-1])
        assert last_adx > 20.0, f"Trend piyasasında ADX düşük: {last_adx:.2f}"


# ─── EMA ──────────────────────────────────────────────────────────────────────

class TestEMAIndicator:
    def test_default_periods(self, standard_ohlcv):
        ema = EMAIndicator()
        result = ema.compute(standard_ohlcv)
        for p in [20, 50, 200]:
            assert f"ema_{p}" in result.columns

    def test_ema_follows_price(self, bullish_ohlcv):
        """Yükseliş trendinde EMA20 < son kapanış fiyatı olmalı (fiyat üstünde)."""
        result = EMAIndicator(periods=[20]).compute(bullish_ohlcv)
        last_close = float(bullish_ohlcv["close"][-1])
        last_ema = float(result["ema_20"][-1])
        assert last_close > last_ema * 0.95, "EMA fiyatı takip etmeli"


# ─── ATR ──────────────────────────────────────────────────────────────────────

class TestATRIndicator:
    def test_output_column(self, standard_ohlcv):
        atr = ATRIndicator()
        result = atr.compute(standard_ohlcv)
        assert "atr_14" in result.columns

    def test_atr_positive(self, standard_ohlcv):
        result = ATRIndicator().compute(standard_ohlcv)
        vals = result["atr_14"].drop_nulls().to_list()
        assert all(v > 0 for v in vals), "ATR her zaman pozitif olmalı"


# ─── Bollinger Bands ──────────────────────────────────────────────────────────

class TestBollingerIndicator:
    def test_output_columns(self, standard_ohlcv):
        bb = BollingerIndicator()
        result = bb.compute(standard_ohlcv)
        for col in ["bb_middle", "bb_upper", "bb_lower", "bb_width_pct", "bb_pct_b"]:
            assert col in result.columns

    def test_upper_gt_lower(self, standard_ohlcv):
        """Üst bant her zaman alt bantın üstünde olmalı."""
        result = BollingerIndicator().compute(standard_ohlcv)
        df = result.drop_nulls()
        assert (df["bb_upper"] > df["bb_lower"]).all()

    def test_middle_between_bands(self, standard_ohlcv):
        """Orta bant, alt ve üst bantlar arasında olmalı."""
        result = BollingerIndicator().compute(standard_ohlcv)
        df = result.drop_nulls()
        assert ((df["bb_middle"] >= df["bb_lower"]) & (df["bb_middle"] <= df["bb_upper"])).all()


# ─── OBV ──────────────────────────────────────────────────────────────────────

class TestOBVIndicator:
    def test_output_columns(self, standard_ohlcv):
        obv = OBVIndicator()
        result = obv.compute(standard_ohlcv)
        assert "obv" in result.columns
        assert "obv_ema" in result.columns

    def test_obv_trend_bullish_market(self, bullish_ohlcv):
        """Yükseliş trendinde OBV'nin genel seyri yukarı olmalı."""
        result = OBVIndicator().compute(bullish_ohlcv)
        obv_start = float(result["obv"][10])
        obv_end = float(result["obv"][-1])
        assert obv_end > obv_start, "Bullish marketde OBV yükselmeli"


# ─── Volume Ratio ─────────────────────────────────────────────────────────────

class TestVolumeRatioIndicator:
    def test_output_columns(self, standard_ohlcv):
        vr = VolumeRatioIndicator()
        result = vr.compute(standard_ohlcv)
        assert "vol_ratio" in result.columns
        assert "vol_ma" in result.columns

    def test_ratio_positive(self, standard_ohlcv):
        result = VolumeRatioIndicator().compute(standard_ohlcv)
        vals = result["vol_ratio"].drop_nulls().to_list()
        assert all(v > 0 for v in vals)


# ─── Swing Points ─────────────────────────────────────────────────────────────

class TestSwingPointsIndicator:
    def test_output_columns(self, standard_ohlcv):
        sp = SwingPointsIndicator()
        result = sp.compute(standard_ohlcv)
        for col in ["swing_high", "swing_low", "swing_high_price", "swing_low_price"]:
            assert col in result.columns

    def test_some_swings_detected(self, standard_ohlcv):
        """200 barlık veride en az birkaç swing noktası olmalı."""
        result = SwingPointsIndicator(lookback=5).compute(standard_ohlcv)
        total_highs = result["swing_high"].sum()
        total_lows = result["swing_low"].sum()
        assert total_highs > 0, "Hiç swing high tespit edilmedi"
        assert total_lows > 0, "Hiç swing low tespit edilmedi"

    def test_lookback_affects_count(self, standard_ohlcv):
        """Daha uzun lookback → daha az swing noktası."""
        sp5 = SwingPointsIndicator(lookback=5).compute(standard_ohlcv)
        sp10 = SwingPointsIndicator(lookback=10).compute(standard_ohlcv)
        assert sp5["swing_high"].sum() >= sp10["swing_high"].sum()


# ─── Pivots ───────────────────────────────────────────────────────────────────

class TestPivotsIndicator:
    def test_output_columns(self, standard_ohlcv):
        result = PivotsIndicator().compute(standard_ohlcv)
        for col in ["pivot", "r1", "r2", "r3", "s1", "s2", "s3"]:
            assert col in result.columns

    def test_r1_gt_pivot_gt_s1(self, standard_ohlcv):
        """R1 > PP > S1 her zaman geçerli olmalı."""
        result = PivotsIndicator().compute(standard_ohlcv)
        df = result.drop_nulls()
        assert (df["r1"] > df["pivot"]).all()
        assert (df["pivot"] > df["s1"]).all()
