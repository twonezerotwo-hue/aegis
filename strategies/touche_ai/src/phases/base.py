"""
Touche AI Limited — Faz Sistemi: Temel Sınıflar ve Veri Modelleri
"""
import abc
from typing import Any, Dict, List, Optional

import polars as pl
import structlog
from pydantic import BaseModel, ConfigDict

logger = structlog.get_logger(__name__)

# ─── Veri Modelleri ───────────────────────────────────────────────────────────

class PhaseResult(BaseModel):
    """
    Her fazın döndürdüğü standart sonuç nesnesi.

    Alanlar:
    - phase_id    : Faz numarası (1-7)
    - phase_name  : İnsan okunabilir faz adı
    - score       : Faz skoru (0-100); EQS hesabına girer
    - signal      : BULLISH | BEARISH | NEUTRAL
    - passed      : Faz filtresinden geçti mi? (False = HOLD'a zorlar)
    - reason      : Kısa açıklama (loglama ve debug için)
    - metadata    : Ekstra veriler (sl, tp, confluences vs.)
    """
    phase_id: int
    phase_name: str
    score: float
    signal: str
    passed: bool
    reason: str
    metadata: Dict[str, Any] = {}

    @property
    def is_bullish(self) -> bool:
        return self.signal == "BULLISH"

    @property
    def is_bearish(self) -> bool:
        return self.signal == "BEARISH"


class PhaseContext(BaseModel):
    """
    Her faza taşınan ortak bağlam nesnesi.

    Tüm indikatörler ve OHLCV verisi bu nesne üzerinden iletilir.
    Faz bağımsızlığını korur: her faz sadece ihtiyaç duyduğu sütunlara erişir.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    symbol: str
    timeframe: str
    df: pl.DataFrame                          # OHLCV + tüm indikatör sütunları
    config: Dict[str, Any]                    # strategy_params.yaml içeriği
    atr: float                                # Güncel ATR değeri (risk hesabı için)
    fundamental_score: Optional[float] = None # Faz 7 için Fundamental AI skoru
    direction_hint: str = "NEUTRAL"           # Önceki fazlardan gelen yönsel ipucu


# ─── Abstract Base Phase ─────────────────────────────────────────────────────

class BasePhase(abc.ABC):
    """
    Touche AI Limited — Tüm fazlar için Abstract Base Class.

    Gereksinimler:
    - Her faz async olmalıdır (non-blocking pipeline)
    - PhaseContext alır, PhaseResult döndürür
    - Hata durumunda çökmek yerine NEUTRAL/passed=False döner
    - Tüm kritik kararlar structlog ile loglanır
    """

    PHASE_ID: int = 0
    PHASE_NAME: str = "BasePhase"

    @abc.abstractmethod
    async def run(self, ctx: PhaseContext) -> PhaseResult:
        """
        Fazı çalıştırır. Alt sınıflar bu metodu mutlaka override etmelidir.
        """
        pass

    def _neutral_result(self, reason: str, metadata: Dict[str, Any] = None) -> PhaseResult:
        """Hata veya yetersiz veri durumunda güvenli NEUTRAL sonuç döndürür."""
        if metadata is None:
            metadata = {}
        return PhaseResult(
            phase_id=self.PHASE_ID,
            phase_name=self.PHASE_NAME,
            score=50.0,
            signal="NEUTRAL",
            passed=True,
            reason=reason,
            metadata=metadata,
        )

    def _safe_float(self, series: pl.Series, index: int = -1) -> float:
        """Null-safe son değer erişimi. Polars Series'ten scalar al."""
        try:
            val = series[index]
            if val is None:
                return 0.0
            # Polars Series'ten scalar al
            if hasattr(val, 'item'):
                return float(val.item())
            return float(val)
        except Exception:
            return 0.0

    def _last_n_non_null(self, df: pl.DataFrame, col: str, n: int) -> List[float]:
        """Sütunun son N null-olmayan değerini döndürür."""
        return (
            df[col]
            .drop_nulls()
            .tail(n)
            .to_list()
        )
