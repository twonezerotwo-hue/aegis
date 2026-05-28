import abc
import os
import sys
from typing import Any, Dict, Optional, Type

import structlog
from pydantic import BaseModel
import redis.asyncio as redis

# `shared` paketine erişmek amacıyla PYTHONPATH için path patch (istenirse direkt ortam path'ine de bırakılabilir)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))
from shared.data_layer.base_client import BaseAPIClient

logger = structlog.get_logger(__name__)

class MetricResponseSchema(BaseModel):
    """
    Metrik servisi API'lerinden dönecek varsayılan veri şeması.
    """
    value: float
    metadata: Optional[Dict[str, Any]] = None

class BaseMetricClient(BaseAPIClient, abc.ABC):
    """
    Stratejiye özel tüm metrik API istemcileri (fundamental vb.) için Abstract Base Class.
    
    Özellikleri:
    - BaseAPIClient (`shared.data_layer.base_client`) sınıfından kalıtım alır.
    - Metriğin doğasına uygun özelleştirilebilir (abstract) Normalization barındırır.
    - Sadece metrikler düzeyinde kullanılabilecek Cache TTL üzerine yazılabilirlik eklendi.
    - API erişilebilirlik sağlığı (Health Check endpoint) sunar.
    """

    # Bu değer Class bazında override edilebilir. 
    # Spesifik metriklerin kendi TTL stratejisi böylece belirlenebilir.
    CACHE_TTL = 3600  

    def __init__(
        self, 
        base_url: str, 
        redis_client: redis.Redis,
        timeframe: str = "1d",
        response_model: Type[BaseModel] = MetricResponseSchema
    ):
        """
        Girdi:
        - `base_url`: Harici metrik API adresi
        - `redis_client`: Paylaşılan Redis objesi
        - `timeframe`: Metriğin analiz zaman aralığını (1d, 1h vs) tanımlar
        """
        super().__init__(base_url=base_url, redis_client=redis_client, response_model=response_model)
        self.timeframe = timeframe

    async def fetch_metric(self, symbol: str) -> Optional[float]:
        """
        BaseAPIClient içerisinden sağlanan güvenli (circuit_breaker, redis, retry özellikli) fetch metodunu kullanarak
        belirtilen aralık (timeframe) ve sembol için metriği çeker; 
        ardından normalize edilmiş halde döndürür. (Beklenen: 0-100)
        """
        endpoint = f"/{symbol}/metric"
        params = {"timeframe": self.timeframe}
        
        try:
            # BaseClient'in fetch fonksiyonunu kullanıyoruz (Cache TTL özel olarak geçilir)
            response_data = await self.fetch(endpoint=endpoint, params=params, cache_ttl=self.CACHE_TTL)
            
            if response_data is None:
                return None
                
            # Dönüş modelinden raw değeri (value) ayıklayalım
            raw_value = getattr(response_data, "value", None)
            
            # Pydantic Model dictionary çevirim uyumluluğu desteği
            if raw_value is None and hasattr(response_data, "model_dump"):
                raw_value = response_data.model_dump().get("value")
                
            if raw_value is None:
                logger.error("metric_missing_value", symbol=symbol, response=str(response_data))
                return None

            # Metriği Alt Sınıfın kurallarıyla 0-100 aralığına normalize et
            return self.normalize(raw_value)
            
        except Exception as e:
            logger.error("metric_fetch_error", symbol=symbol, error=str(e))
            return None

    @abc.abstractmethod
    def normalize(self, raw_value: Any) -> float:
        """
        Alt sınıfların (Subclass) mutlaka ezmesi (override etmesi) gereken bölüm.
        Gelen ham veri, metriğin özelliğine göre (min-max scaling, z-score vs.) analiz edilip,
        hedef 0-100 değer skalası arasında normalize edilmiş bir float olarak dönmelidir.
        """
        pass

    def get_signal(self, normalized_value: float) -> str:
        """
        0 ile 100 arasında normalize edilmiş skoru, standart yatırım sinyallerine dönüştürür.
        """
        # Scope sınırları güvenliği için min/max clamp
        if not (0 <= normalized_value <= 100):
            logger.warning("out_of_bounds_normalized_metric", value=normalized_value)
            normalized_value = max(0, min(100, normalized_value))

        if normalized_value >= 70:
            return "BULLISH"
        elif normalized_value <= 30:
            return "BEARISH"
        else:
            return "NEUTRAL"

    async def check_health(self) -> bool:
        """
        Metrik sağlayıcı API'nin ayakta olup olmadığını kontrol eden health check fonksiyonu.
        """
        try:
            # _call_api BaseClient'ten gelen ve doğrudan http isteği atan tenacity korumalı bir metottur
            await self._call_api(endpoint="/health")
            logger.info("api_health_check_passed", base_url=self.base_url)
            return True
        except Exception as e:
            logger.error("api_health_check_failed", base_url=self.base_url, error=str(e))
            return False
