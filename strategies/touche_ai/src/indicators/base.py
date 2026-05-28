import abc
from typing import ClassVar, List

import polars as pl
import structlog

logger = structlog.get_logger(__name__)


class BaseIndicator(abc.ABC):
    """
    Touche AI Limited — Tüm teknik indikatörler için Abstract Base Class.

    Özellikler:
    - Polars DataFrame üzerinde çalışır (Pandas yerine Polars: daha hızlı, tip güvenli)
    - Her indikatör yeni sütun(lar) eklenmiş DataFrame'i döndürür
    - İç tutarlılık için validate() zorunludur
    - Tüm geçici sütunlar "_" önekiyle oluşturulup işlem sonunda silinir
    """

    NAME: ClassVar[str] = ""
    REQUIRED_COLUMNS: ClassVar[List[str]] = ["open", "high", "low", "close", "volume"]
    MIN_ROWS: ClassVar[int] = 2

    @abc.abstractmethod
    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        İndikatörü hesaplar ve yeni sütunlar eklenmiş DataFrame'i döndürür.
        Alt sınıflar bu metodu mutlaka override etmelidir.
        """
        pass

    def validate(self, df: pl.DataFrame) -> None:
        """Giriş DataFrame'inin minimum gereksinimlerini kontrol eder."""
        missing = [c for c in self.REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"{self.NAME}: Eksik sütunlar: {missing}")
        if len(df) < self.MIN_ROWS:
            raise ValueError(
                f"{self.NAME}: En az {self.MIN_ROWS} satır gerekli, {len(df)} var."
            )

    def latest(self, df: pl.DataFrame, col: str) -> float:
        """Belirtilen sütunun en son (güncel) değerini float olarak döndürür."""
        return float(df[col][-1])

    def latest_n(self, df: pl.DataFrame, col: str, n: int) -> List[float]:
        """Belirtilen sütunun son N değerini liste olarak döndürür."""
        return df[col].tail(n).to_list()
