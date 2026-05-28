"""
Touche AI Limited — Yapı İndikatörleri
Swing Points (Salınım Noktaları), Classic Pivot Points
"""
import polars as pl
import structlog

from .base import BaseIndicator

logger = structlog.get_logger(__name__)


class SwingPointsIndicator(BaseIndicator):
    """
    Swing High / Swing Low Tespiti.

    Bir bar, komşularının tümünden yüksek (veya düşük) olduğunda
    swing noktası sayılır. Piyasa yapısı (HH/HL/LH/LL) analizinin temelidir.

    Algoritma:
    - i bir swing high ise: high[i] >= high[i-k..i+k] tüm k ∈ [1, lookback]
    - i bir swing low  ise: low[i]  <= low[i-k..i+k]  tüm k ∈ [1, lookback]

    Çıktı sütunları: swing_high (bool), swing_low (bool),
                     swing_high_price (float | null), swing_low_price (float | null)
    """

    NAME = "SwingPoints"
    REQUIRED_COLUMNS = ["high", "low"]
    MIN_ROWS = 11

    def __init__(self, lookback: int = 5):
        self.lookback = lookback

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        self.validate(df)

        highs = df["high"].to_list()
        lows = df["low"].to_list()
        n = len(highs)
        lb = self.lookback

        swing_high = [False] * n
        swing_low = [False] * n

        for i in range(lb, n - lb):
            window_h = highs[i - lb: i + lb + 1]
            window_l = lows[i - lb: i + lb + 1]
            # Gereksinim: tam merkezdeki değer penceredeki max/min olmalı
            if highs[i] == max(window_h):
                swing_high[i] = True
            if lows[i] == min(window_l):
                swing_low[i] = True

        df = df.with_columns([
            pl.Series("swing_high", swing_high),
            pl.Series("swing_low", swing_low),
        ])

        # Fiyat seviyelerini ayrı sütun olarak tut (null = swing değil)
        df = df.with_columns([
            pl.when(pl.col("swing_high"))
            .then(pl.col("high"))
            .otherwise(None)
            .alias("swing_high_price"),
            pl.when(pl.col("swing_low"))
            .then(pl.col("low"))
            .otherwise(None)
            .alias("swing_low_price"),
        ])

        logger.debug("swing_points_computed", lookback=self.lookback,
                     total_highs=sum(swing_high), total_lows=sum(swing_low))
        return df


class PivotsIndicator(BaseIndicator):
    """
    Classic Pivot Points — Destek/Direnç Seviyeleri.

    Hesaplama (Klasik Yöntem):
    - PP = (H + L + C) / 3
    - R1 = 2*PP − L   |   S1 = 2*PP − H
    - R2 = PP + (H-L) |   S2 = PP − (H-L)
    - R3 = H + 2*(PP-L) | S3 = L − 2*(H-PP)

    Her bar için bir önceki barın H/L/C değerleri kullanılır
    (periyodik pivot mantığına en yakın intrabar yaklaşımı).

    Çıktı sütunları: pivot, r1, r2, r3, s1, s2, s3
    """

    NAME = "Pivots"
    REQUIRED_COLUMNS = ["high", "low", "close"]
    MIN_ROWS = 2

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        self.validate(df)

        # Önceki barın H/L/C'si kullanılır (shift(1))
        df = (
            df
            .with_columns([
                pl.col("high").shift(1).alias("_ph"),
                pl.col("low").shift(1).alias("_pl"),
                pl.col("close").shift(1).alias("_pc"),
            ])
            .with_columns(
                ((pl.col("_ph") + pl.col("_pl") + pl.col("_pc")) / 3.0).alias("pivot")
            )
            .with_columns([
                (2.0 * pl.col("pivot") - pl.col("_pl")).alias("r1"),
                (2.0 * pl.col("pivot") - pl.col("_ph")).alias("s1"),
                (pl.col("pivot") + pl.col("_ph") - pl.col("_pl")).alias("r2"),
                (pl.col("pivot") - pl.col("_ph") + pl.col("_pl")).alias("s2"),
            ])
            .with_columns([
                (pl.col("_ph") + 2.0 * (pl.col("pivot") - pl.col("_pl"))).alias("r3"),
                (pl.col("_pl") - 2.0 * (pl.col("_ph") - pl.col("pivot"))).alias("s3"),
            ])
            .drop(["_ph", "_pl", "_pc"])
        )

        logger.debug("pivots_computed", rows=len(df))
        return df
