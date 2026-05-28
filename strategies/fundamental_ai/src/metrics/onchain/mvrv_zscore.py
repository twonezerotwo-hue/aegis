import os
import sys
from typing import Optional
import structlog
from pydantic import BaseModel

# PYTHONPATH root fallback
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../..")))

from strategies.fundamental_ai.src.clients.glassnode_client import GlassnodeClient
from strategies.fundamental_ai.src.metrics.normalizers import Normalizer

logger = structlog.get_logger(__name__)

class MVRVResult(BaseModel):
    """
    MVRV Z-Score değerlendirme sonucunu tutan obje.
    """
    symbol: str
    raw_mvrv: float
    normalized_score: float
    signal: str

class MVRVZscoreMetric:
    """
    AEGIS Holding - MVRV Z-Score Metrik Servisi
    (AI Modeli spesifik kurallara hizmet eder)
    
    Kurallar:
    - MVRV < 1.0 -> Oversold piyasa (Satış baskısı). Tersine çevrilerek Alış Fırsatı (BULLISH) puanı alır.
    - MVRV > 3.0 -> Overvalued piyasa (Aşırı değerleme). Tersine çevrilerek Satış Riski (BEARISH) puanı alır.
    - Normalizasyon: Doğrusal Min-Max scaling [1.0, 3.0] takiben Ters (Inverse) fonksiyonu çağırılır.
    """

    def __init__(self, glassnode_client: GlassnodeClient):
        self.client = glassnode_client

    async def evaluate(self, symbol: str) -> Optional[MVRVResult]:
        """
        Belirtilen Symbol için Glassnode'dan raw veriyi okur,
        Strateji konfigürasyonuna göre normalize eder ve Sinyal döner.
        """
        try:
            # Genel Client'ın default normalize davranışını pas geçmek için
            # metriklerin doğrudan ham halleri (fetch komutuyla) tabandan çekiliyor.
            metric_id = "mvrv_zscore"
            
            if metric_id not in self.client.METRIC_ENDPOINTS:
                logger.error("missing_metric_endpoint_in_client", metric=metric_id)
                return None
                
            endpoint = self.client.METRIC_ENDPOINTS[metric_id]
            params = {
                "a": symbol.upper(),
                "api_key": self.client.api_key,
                "i": self.client.timeframe
            }
            
            async with self.client.rate_limiter:
                # Raw veriyi Pydantic MetricResponseSchema paketi olarak dönecektir.
                response = await self.client.fetch(endpoint, params=params, cache_ttl=self.client.CACHE_TTL)
                
            if response is None:
                logger.warning("empty_glassnode_mvrv_response", symbol=symbol)
                return None
                
            raw_val = getattr(response, "value", None)
            
            # Fallback dict parsing for robust architecture
            if raw_val is None and hasattr(response, "model_dump"):
                raw_val = response.model_dump().get("value")
                
            if raw_val is None:
                logger.error("mvrv_raw_value_missing")
                return None
                
            raw_val = float(raw_val)
            
            # --- NORMALİZASYON BORUHATTI (PIPELINE) ---
            # 1. Bounded Linear (Sektör referans sınırı: 1.0 - 3.0)
            linear_val = Normalizer.process(raw_val, method="bounded_linear", min_val=1.0, max_val=3.0)
            
            # 2. Inverse Çevrimi (Oversold -> BULLISH %100, Overvalued -> BEARISH %0 konsepti)
            final_normalized = Normalizer.process(linear_val, method="inverse")
            
            # 3. Sinyal Etiketleme
            signal = self._interpret_signal(final_normalized)
            
            logger.info(
                "mvrv_evaluation_success", 
                symbol=symbol, 
                raw=raw_val, 
                score=final_normalized, 
                signal=signal
            )
            
            return MVRVResult(
                symbol=symbol.upper(),
                raw_mvrv=raw_val,
                normalized_score=final_normalized,
                signal=signal
            )

        except Exception as e:
            logger.error("mvrv_evaluation_failed", symbol=symbol, error=str(e))
            return None

    def _interpret_signal(self, score: float) -> str:
        """
        Bütün stratejilerle entegre biçimde final normal skora (0-100) göre Sinyal dilimleri:
        >= 70 -> BULLISH (Al)
        <= 30 -> BEARISH (Sat)
        Geri Kalan -> NEUTRAL (Koru)
        """
        if score >= 70.0:
            return "BULLISH"
        elif score <= 30.0:
            return "BEARISH"
        return "NEUTRAL"
