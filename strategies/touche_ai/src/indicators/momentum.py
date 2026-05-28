"""
Touche AI Limited — Momentum İndikatörleri
RSI, StochRSI, MACD
"""
import polars as pl
import structlog

from .base import BaseIndicator

logger = structlog.get_logger(__name__)


class RSIIndicator(BaseIndicator):
    """
    Relative Strength Index (RSI) — Wilder'ın Yumuşatma Yöntemiyle.

    Hesaplama:
    - delta = close.diff()
    - gain = delta.clip(lower=0)   |   loss = (-delta).clip(lower=0)
    - avg_gain / avg_loss = Wilder RMA (alpha = 1/period)
    - RSI = 100 - (100 / (1 + RS))

    Çıktı sütunları: rsi_{period}
    """

    NAME = "RSI"
    REQUIRED_COLUMNS = ["close"]
    MIN_ROWS = 15

    def __init__(self, period: int = 14):
        self.period = period

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        self.validate(df)

        alpha = 1.0 / self.period

        df = (
            df.with_columns(
                pl.col("close").diff(1).alias("_delta")
            )
            .with_columns([
                pl.col("_delta").clip(lower_bound=0.0).alias("_gain"),
                (-pl.col("_delta")).clip(lower_bound=0.0).alias("_loss"),
            ])
            .with_columns([
                pl.col("_gain").ewm_mean(alpha=alpha, adjust=False).alias("_avg_gain"),
                pl.col("_loss").ewm_mean(alpha=alpha, adjust=False).alias("_avg_loss"),
            ])
            .with_columns(
                (
                    100.0
                    - (100.0 / (1.0 + pl.col("_avg_gain") / (pl.col("_avg_loss") + 1e-10)))
                ).alias(f"rsi_{self.period}")
            )
            .drop(["_delta", "_gain", "_loss", "_avg_gain", "_avg_loss"])
        )

        logger.debug("rsi_computed", period=self.period, rows=len(df))
        return df


class StochRSIIndicator(BaseIndicator):
    """
    Stochastic RSI — RSI'nın Stochastic Osilatörü.

    Hesaplama:
    1. RSI hesapla
    2. RSI'nın stoch_period periyotluk min/max'ını bul
    3. %K = (RSI - min) / (max - min + ε) × 100
    4. smooth_k periyotluk MA → %K smoothed
    5. smooth_d periyotluk MA(%K) → %D (sinyal hattı)

    Çıktı sütunları: stochrsi_k, stochrsi_d
    """

    NAME = "StochRSI"
    REQUIRED_COLUMNS = ["close"]
    MIN_ROWS = 30

    def __init__(
        self,
        rsi_period: int = 14,
        stoch_period: int = 14,
        smooth_k: int = 3,
        smooth_d: int = 3,
    ):
        self.rsi_period = rsi_period
        self.stoch_period = stoch_period
        self.smooth_k = smooth_k
        self.smooth_d = smooth_d

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        self.validate(df)

        # RSI'yı hesapla (geçici olarak ekle)
        rsi_ind = RSIIndicator(self.rsi_period)
        df = rsi_ind.compute(df)
        rsi_col = f"rsi_{self.rsi_period}"

        df = (
            df.with_columns([
                pl.col(rsi_col).rolling_min(window_size=self.stoch_period).alias("_rsi_min"),
                pl.col(rsi_col).rolling_max(window_size=self.stoch_period).alias("_rsi_max"),
            ])
            .with_columns(
                (
                    100.0
                    * (pl.col(rsi_col) - pl.col("_rsi_min"))
                    / (pl.col("_rsi_max") - pl.col("_rsi_min") + 1e-10)
                ).alias("_raw_k")
            )
            .with_columns(
                pl.col("_raw_k").rolling_mean(window_size=self.smooth_k).alias("_k")
            )
            .with_columns(
                pl.col("_k").rolling_mean(window_size=self.smooth_d).alias("stochrsi_d")
            )
            .rename({"_k": "stochrsi_k"})
            .drop(["_rsi_min", "_rsi_max", "_raw_k"])
        )

        logger.debug("stochrsi_computed", rsi_period=self.rsi_period, stoch_period=self.stoch_period)
        return df


class MACDIndicator(BaseIndicator):
    """
    Moving Average Convergence Divergence (MACD).

    Hesaplama:
    - EMA_fast(fast) − EMA_slow(slow)  → MACD hattı
    - EMA(MACD, signal)                → Sinyal hattı
    - MACD − Sinyal                    → Histogram

    Çıktı sütunları: macd, macd_signal, macd_hist
    """

    NAME = "MACD"
    REQUIRED_COLUMNS = ["close"]
    MIN_ROWS = 35

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        self.fast = fast
        self.slow = slow
        self.signal = signal

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        self.validate(df)

        df = (
            df.with_columns([
                pl.col("close").ewm_mean(span=self.fast, adjust=False).alias("_ema_fast"),
                pl.col("close").ewm_mean(span=self.slow, adjust=False).alias("_ema_slow"),
            ])
            .with_columns(
                (pl.col("_ema_fast") - pl.col("_ema_slow")).alias("macd")
            )
            .with_columns(
                pl.col("macd").ewm_mean(span=self.signal, adjust=False).alias("macd_signal")
            )
            .with_columns(
                (pl.col("macd") - pl.col("macd_signal")).alias("macd_hist")
            )
            .drop(["_ema_fast", "_ema_slow"])
        )

        logger.debug("macd_computed", fast=self.fast, slow=self.slow, signal=self.signal)
        return df
