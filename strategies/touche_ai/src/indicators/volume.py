"""
Touche AI Limited — Hacim İndikatörleri
OBV (On-Balance Volume), Volume Ratio
"""
import polars as pl
import structlog

from .base import BaseIndicator

logger = structlog.get_logger(__name__)


class OBVIndicator(BaseIndicator):
    """
    On-Balance Volume (OBV) — Birikimli Yönlü Hacim.

    Hesaplama:
    - close > prev_close → OBV += volume   (alım baskısı)
    - close < prev_close → OBV -= volume   (satım baskısı)
    - close = prev_close → OBV değişmez

    OBV ve fiyat arasındaki diverjans, kritik bir erken uyarı sinyalidir.
    Çıktı sütunları: obv, obv_ema (trendi yumuşatmak için)
    """

    NAME = "OBV"
    REQUIRED_COLUMNS = ["close", "volume"]
    MIN_ROWS = 5

    def __init__(self, ema_period: int = 20):
        self.ema_period = ema_period

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        self.validate(df)

        # Polars koşullu kümülatif toplam:
        # Fiyat artışında +hacim, düşüşünde -hacim, yatayda 0
        df = (
            df
            .with_columns(
                pl.when(pl.col("close") > pl.col("close").shift(1))
                .then(pl.col("volume"))
                .when(pl.col("close") < pl.col("close").shift(1))
                .then(-pl.col("volume"))
                .otherwise(0.0)
                .alias("_obv_delta")
            )
            .with_columns(
                pl.col("_obv_delta").cum_sum().alias("obv")
            )
            .with_columns(
                pl.col("obv").ewm_mean(span=self.ema_period, adjust=False).alias("obv_ema")
            )
            .drop("_obv_delta")
        )

        logger.debug("obv_computed", ema_period=self.ema_period)
        return df


class VolumeRatioIndicator(BaseIndicator):
    """
    Volume Ratio — Güncel Hacmin Ortalamasına Oranı.

    Hesaplama:
    - vol_ma = SMA(volume, period)
    - vol_ratio = volume / vol_ma

    > 1.5 → Ortalamanın üzerinde hacim (işlem geçerliliği yüksek)
    < 0.5 → Düşük hacim (sahte kırılma riski)

    Çıktı sütunları: vol_ma, vol_ratio
    """

    NAME = "VolumeRatio"
    REQUIRED_COLUMNS = ["volume"]
    MIN_ROWS = 5

    def __init__(self, period: int = 20):
        self.period = period

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        self.validate(df)

        df = (
            df
            .with_columns(
                pl.col("volume").rolling_mean(window_size=self.period).alias("vol_ma")
            )
            .with_columns(
                (pl.col("volume") / (pl.col("vol_ma") + 1e-10)).alias("vol_ratio")
            )
        )

        logger.debug("volume_ratio_computed", period=self.period)
        return df


class CMFIndicator(BaseIndicator):
    """
    Chaikin Money Flow (CMF) — Para Akış Yönü ve Gücü.

    Formül:
      MFM = ((Close - Low) - (High - Close)) / (High - Low + ε)  → Money Flow Multiplier
      MFV = MFM × Volume                                          → Money Flow Volume
      CMF(n) = Sum(MFV, n) / Sum(Volume, n)                       → normalised [-1, +1]

    Yorum:
      CMF > +0.1 → Alım baskısı (birikme)
      CMF < -0.1 → Satış baskısı (dağıtma)
      CMF ≈ 0    → Nötr

    OBV slope'tan daha güvenilir: hacim boyutunu ve fiyat kapanış pozisyonunu birleştirir.
    Çıktı sütunu: cmf_{period}
    """

    NAME = "CMF"
    REQUIRED_COLUMNS = ["high", "low", "close", "volume"]
    MIN_ROWS = 5

    def __init__(self, period: int = 20):
        self.period = period

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        self.validate(df)

        df = (
            df
            .with_columns(
                # Money Flow Multiplier
                (
                    (pl.col("close") - pl.col("low")) -
                    (pl.col("high")  - pl.col("close"))
                ) / (pl.col("high") - pl.col("low") + 1e-10)
            ).alias("_mfm")
        )

        # Polars with_columns expects the alias inside
        df = df.with_columns(
            (
                (
                    (pl.col("close") - pl.col("low")) -
                    (pl.col("high")  - pl.col("close"))
                ) / (pl.col("high") - pl.col("low") + 1e-10)
            ).alias("_mfm")
        ).with_columns(
            (pl.col("_mfm") * pl.col("volume")).alias("_mfv")
        ).with_columns([
            pl.col("_mfv").rolling_sum(window_size=self.period, min_periods=3).alias("_sum_mfv"),
            pl.col("volume").rolling_sum(window_size=self.period, min_periods=3).alias("_sum_vol"),
        ]).with_columns(
            (pl.col("_sum_mfv") / (pl.col("_sum_vol") + 1e-10)).alias(f"cmf_{self.period}")
        ).drop(["_mfm", "_mfv", "_sum_mfv", "_sum_vol"])

        logger.debug("cmf_computed", period=self.period)
        return df
