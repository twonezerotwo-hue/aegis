"""
Touche AI Limited — Volatilite İndikatörleri
ATR (Average True Range), Bollinger Bands
"""
import polars as pl
import structlog

from .base import BaseIndicator

logger = structlog.get_logger(__name__)


class ATRIndicator(BaseIndicator):
    """
    Average True Range (ATR) — Wilder'ın Yumuşatma Yöntemiyle.

    Hesaplama:
    - TR  = max(H-L, |H-PC|, |L-PC|)
    - ATR = Wilder_RMA(TR, period)

    Risk yönetimi ve stop-loss hesaplamalarının temel girdisidir.

    Çıktı sütunları: atr_{period}
    """

    NAME = "ATR"
    REQUIRED_COLUMNS = ["high", "low", "close"]
    MIN_ROWS = 15

    def __init__(self, period: int = 14):
        self.period = period

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        self.validate(df)

        alpha = 1.0 / self.period
        col_name = f"atr_{self.period}"

        df = (
            df
            .with_columns([
                (pl.col("high") - pl.col("low")).alias("_tr1"),
                (pl.col("high") - pl.col("close").shift(1)).abs().alias("_tr2"),
                (pl.col("low") - pl.col("close").shift(1)).abs().alias("_tr3"),
            ])
            .with_columns(
                pl.max_horizontal("_tr1", "_tr2", "_tr3").alias("_tr")
            )
            .with_columns(
                pl.col("_tr").ewm_mean(alpha=alpha, adjust=False).alias(col_name)
            )
            .drop(["_tr1", "_tr2", "_tr3", "_tr"])
        )

        logger.debug("atr_computed", period=self.period)
        return df


class BollingerIndicator(BaseIndicator):
    """
    Bollinger Bands — Orta, Üst ve Alt Bant + Bant Genişliği.

    Hesaplama:
    - Middle = SMA(close, period)
    - Upper  = Middle + std_dev × StdDev(close, period)
    - Lower  = Middle − std_dev × StdDev(close, period)
    - Width% = (Upper − Lower) / Middle × 100

    Volatilite daralması/genişlemesi için kritik; sıkışma (squeeze) tespitinde kullanılır.

    Çıktı sütunları: bb_middle, bb_upper, bb_lower, bb_width_pct, bb_pct_b
    """

    NAME = "Bollinger"
    REQUIRED_COLUMNS = ["close"]
    MIN_ROWS = 20

    def __init__(self, period: int = 20, std_dev: float = 2.0):
        self.period = period
        self.std_dev = std_dev

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        self.validate(df)

        df = (
            df
            .with_columns([
                pl.col("close").rolling_mean(window_size=self.period).alias("bb_middle"),
                pl.col("close").rolling_std(window_size=self.period).alias("_bb_std"),
            ])
            .with_columns([
                (pl.col("bb_middle") + self.std_dev * pl.col("_bb_std")).alias("bb_upper"),
                (pl.col("bb_middle") - self.std_dev * pl.col("_bb_std")).alias("bb_lower"),
            ])
            .with_columns([
                # Bant Genişlik Yüzdesi: volatilite ölçümü için (DynamicWeightEngine'e beslenebilir)
                (
                    (pl.col("bb_upper") - pl.col("bb_lower"))
                    / (pl.col("bb_middle") + 1e-10)
                    * 100.0
                ).alias("bb_width_pct"),
                # %B: Fiyatın band içindeki relatif konumu (0=alt, 1=üst)
                (
                    (pl.col("close") - pl.col("bb_lower"))
                    / (pl.col("bb_upper") - pl.col("bb_lower") + 1e-10)
                ).alias("bb_pct_b"),
            ])
            .drop("_bb_std")
        )

        logger.debug("bollinger_computed", period=self.period, std_dev=self.std_dev)
        return df
