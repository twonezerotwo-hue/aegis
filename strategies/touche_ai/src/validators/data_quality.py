"""
Touche AI Limited — OHLCV Veri Kalite Doğrulayıcı

Pipeline'a girmeden önce veri bütünlüğünü kontrol eder.
Sorunlu barlar → uyarı. Kritik sorunlar → geçersiz (is_valid=False).
"""
from dataclasses import dataclass, field
from typing import List

import polars as pl
import structlog

logger = structlog.get_logger(__name__)

_REQUIRED_COLS = ["open", "high", "low", "close", "volume"]
_MIN_ROWS_ABSOLUTE = 70          # MACD(26) + signal(9) + warmup
_MAX_ZERO_VOL_PCT  = 0.10        # %10 üzeri sıfır-hacim → şüpheli veri
_SPIKE_ATR_MULT    = 10.0        # ATR'nin X katı hareket → fiyat spike
_MAX_GAP_ATR_MULT  = 15.0        # Ardışık bar arası boşluk (gap) eşiği


@dataclass
class DataQualityReport:
    is_valid: bool
    warnings: List[str] = field(default_factory=list)
    errors: List[str]   = field(default_factory=list)
    stats: dict         = field(default_factory=dict)

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    def summary(self) -> str:
        parts = []
        if self.errors:
            parts.append(f"HATALAR({len(self.errors)}): {'; '.join(self.errors)}")
        if self.warnings:
            parts.append(f"UYARILAR({len(self.warnings)}): {'; '.join(self.warnings)}")
        if not parts:
            return "OK — veri kalitesi iyi"
        return " | ".join(parts)


class DataQualityValidator:
    """
    OHLCV DataFrame'i pipeline'a girmeden önce doğrular.

    Kullanım:
        validator = DataQualityValidator()
        report = validator.validate(df)
        if not report.is_valid:
            return neutral_result(report.summary())
    """

    def __init__(
        self,
        min_rows:         int   = _MIN_ROWS_ABSOLUTE,
        max_zero_vol_pct: float = _MAX_ZERO_VOL_PCT,
        spike_atr_mult:   float = _SPIKE_ATR_MULT,
        max_gap_atr_mult: float = _MAX_GAP_ATR_MULT,
    ):
        self.min_rows         = min_rows
        self.max_zero_vol_pct = max_zero_vol_pct
        self.spike_atr_mult   = spike_atr_mult
        self.max_gap_atr_mult = max_gap_atr_mult

    def validate(self, df: pl.DataFrame) -> DataQualityReport:
        errors: List[str]   = []
        warnings: List[str] = []
        stats: dict         = {"rows": len(df)}

        # ── 1. Gerekli sütunlar ─────────────────────────────────────────────
        missing = [c for c in _REQUIRED_COLS if c not in df.columns]
        if missing:
            errors.append(f"Eksik sütunlar: {missing}")
            return DataQualityReport(is_valid=False, errors=errors, stats=stats)

        # ── 2. Minimum satır sayısı ─────────────────────────────────────────
        if len(df) < self.min_rows:
            errors.append(
                f"Yetersiz bar: {len(df)} < {self.min_rows} (MACD warmup için minimum)"
            )

        # ── 3. Fiyat tutarsızlığı (low > high veya negatif) ─────────────────
        invalid_candles = df.filter(
            (pl.col("low") > pl.col("high")) |
            (pl.col("close") <= 0) |
            (pl.col("open") <= 0)
        )
        n_invalid = len(invalid_candles)
        stats["invalid_candles"] = n_invalid
        if n_invalid > 0:
            errors.append(f"{n_invalid} geçersiz bar (low>high veya sıfır fiyat)")

        # ── 4. Sıfır / düşük hacim ──────────────────────────────────────────
        zero_vol = df.filter(pl.col("volume") == 0)
        zero_vol_pct = len(zero_vol) / max(len(df), 1)
        stats["zero_volume_pct"] = round(zero_vol_pct, 4)
        if zero_vol_pct > self.max_zero_vol_pct:
            warnings.append(
                f"Yüksek sıfır-hacim oranı: %{zero_vol_pct*100:.1f} "
                f"(>{self.max_zero_vol_pct*100:.0f}% — sahte bar riski)"
            )

        # ── 5. Fiyat spike tespiti (ATR tabanlı) ────────────────────────────
        # Basit ATR proxy: (high-low) için 20-bar ortalama
        try:
            range_col = (df["high"] - df["low"])
            atr_proxy = float(range_col.rolling_mean(window_size=20, min_periods=5)[-1])
            if atr_proxy > 1e-10:
                spike_mask = range_col > (self.spike_atr_mult * atr_proxy)
                n_spikes = int(spike_mask.sum())
                stats["price_spikes"] = n_spikes
                if n_spikes > 0:
                    warnings.append(
                        f"{n_spikes} fiyat spike'ı tespit edildi "
                        f"(>{self.spike_atr_mult}x ATR)"
                    )
        except Exception:
            pass

        # ── 6. Fiyat timestamp boşlukları (büyük atlama) ─────────────────────
        if "timestamp" in df.columns:
            try:
                ts = df["timestamp"].cast(pl.Int64).to_list()
                if len(ts) >= 2:
                    diffs = [ts[i+1] - ts[i] for i in range(len(ts)-1)]
                    median_diff = sorted(diffs)[len(diffs)//2]
                    if median_diff > 0:
                        large_gaps = sum(1 for d in diffs if d > 5 * median_diff)
                        stats["timestamp_gaps"] = large_gaps
                        if large_gaps > 0:
                            warnings.append(
                                f"{large_gaps} büyük zaman boşluğu "
                                f"(>5x median aralık) — veri eksikliği olabilir"
                            )
            except Exception:
                pass

        # ── 7. Stale data kontrolü (son bar çok eski mi?) ───────────────────
        # Son bar timestamp ile şu an arasındaki fark (varsa)
        # Not: Bu kontrol opsiyonel — gerçek-zamanlı sistemlerde kullanılır

        is_valid = len(errors) == 0
        report = DataQualityReport(
            is_valid=is_valid,
            warnings=warnings,
            errors=errors,
            stats=stats,
        )

        if not is_valid:
            logger.error("data_quality_failed", errors=errors, rows=len(df))
        elif warnings:
            logger.warning("data_quality_warnings", warnings=warnings, rows=len(df))
        else:
            logger.debug("data_quality_ok", rows=len(df))

        return report
