"""
Touche AI Limited — Trend İndikatörleri
ADX (Average Directional Index), EMA (Exponential Moving Average)
"""
import polars as pl
import structlog

from .base import BaseIndicator

logger = structlog.get_logger(__name__)


class ADXIndicator(BaseIndicator):
    """
    Average Directional Index (ADX) — Wilder'ın Yöntemiyle.

    Hesaplama:
    1. TR  = max(H-L, |H-PC|, |L-PC|)
    2. +DM = max(H - PH, 0) eğer (H-PH) > (PL-L) ise, yoksa 0
    3. -DM = max(PL - L, 0) eğer (PL-L) > (H-PH) ise, yoksa 0
    4. ATR  = Wilder RMA(TR, period)
    5. +DI  = 100 × Wilder_RMA(+DM) / ATR
    6. -DI  = 100 × Wilder_RMA(-DM) / ATR
    7. DX   = 100 × |+DI - -DI| / (+DI + -DI)
    8. ADX  = Wilder_RMA(DX, period)

    Çıktı sütunları: adx, di_plus, di_minus
    """

    NAME = "ADX"
    REQUIRED_COLUMNS = ["high", "low", "close"]
    MIN_ROWS = 30

    def __init__(self, period: int = 14):
        self.period = period

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        self.validate(df)

        alpha = 1.0 / self.period

        df = (
            df
            # ── Gerçek Aralık (True Range) ───────────────────────────
            .with_columns([
                (pl.col("high") - pl.col("low")).alias("_tr1"),
                (pl.col("high") - pl.col("close").shift(1)).abs().alias("_tr2"),
                (pl.col("low") - pl.col("close").shift(1)).abs().alias("_tr3"),
            ])
            .with_columns(
                pl.max_horizontal("_tr1", "_tr2", "_tr3").alias("_tr")
            )
            # ── Yönlü Hareketler (Directional Movements) ────────────
            .with_columns([
                (pl.col("high") - pl.col("high").shift(1)).alias("_up_move"),
                (pl.col("low").shift(1) - pl.col("low")).alias("_down_move"),
            ])
            .with_columns([
                pl.when(
                    (pl.col("_up_move") > pl.col("_down_move")) & (pl.col("_up_move") > 0)
                ).then(pl.col("_up_move")).otherwise(0.0).alias("_plus_dm"),
                pl.when(
                    (pl.col("_down_move") > pl.col("_up_move")) & (pl.col("_down_move") > 0)
                ).then(pl.col("_down_move")).otherwise(0.0).alias("_minus_dm"),
            ])
            # ── Wilder RMA ile Yumuşatma ─────────────────────────────
            .with_columns([
                pl.col("_tr").ewm_mean(alpha=alpha, adjust=False).alias("_atr_raw"),
                pl.col("_plus_dm").ewm_mean(alpha=alpha, adjust=False).alias("_sm_plus_dm"),
                pl.col("_minus_dm").ewm_mean(alpha=alpha, adjust=False).alias("_sm_minus_dm"),
            ])
            # ── Yönlü Endeksler (Directional Indices) ────────────────
            .with_columns([
                (100.0 * pl.col("_sm_plus_dm") / (pl.col("_atr_raw") + 1e-10)).alias("di_plus"),
                (100.0 * pl.col("_sm_minus_dm") / (pl.col("_atr_raw") + 1e-10)).alias("di_minus"),
            ])
            # ── ADX ─────────────────────────────────────────────────
            .with_columns(
                (
                    100.0
                    * (pl.col("di_plus") - pl.col("di_minus")).abs()
                    / (pl.col("di_plus") + pl.col("di_minus") + 1e-10)
                ).alias("_dx")
            )
            .with_columns(
                pl.col("_dx").ewm_mean(alpha=alpha, adjust=False).alias("adx")
            )
            .drop(["_tr1", "_tr2", "_tr3", "_tr", "_up_move", "_down_move",
                   "_plus_dm", "_minus_dm", "_atr_raw", "_sm_plus_dm", "_sm_minus_dm", "_dx"])
        )

        logger.debug("adx_computed", period=self.period)
        return df


class EMAIndicator(BaseIndicator):
    """
    Exponential Moving Average (EMA) — Çoklu periyot destekli.

    Çıktı sütunları: ema_{period} (her verilen periyot için ayrı sütun)
    Örn: ema_20, ema_50, ema_200
    """

    NAME = "EMA"
    REQUIRED_COLUMNS = ["close"]
    MIN_ROWS = 5

    def __init__(self, periods: list[int] = None):
        # Varsayılan: Hızlı (20), Yavaş (50), Trend (200)
        self.periods = periods or [20, 50, 200]

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        self.validate(df)

        expressions = [
            pl.col("close").ewm_mean(span=p, adjust=False).alias(f"ema_{p}")
            for p in self.periods
        ]
        df = df.with_columns(expressions)

        logger.debug("ema_computed", periods=self.periods)
        return df
