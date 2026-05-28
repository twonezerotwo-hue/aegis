import os
import sys
from typing import Any, Optional

import structlog
from pydantic import BaseModel
import redis.asyncio as redis
from aiolimiter import AsyncLimiter

# Kurulum yolları (PYTHONPATH yapılandırması)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))
from strategies.fundamental_ai.src.clients.base_metric_client import BaseMetricClient

logger = structlog.get_logger(__name__)

def get_vault_secret(secret_name: str) -> str:
    """
    Güvenli depolama (Vault) Entegrasyonu:
    Burada Hashicorp Vault, AWS Secrets Manager veya benzeri bir gizlilik sağlayıcısından 
    API Key'in okunduğunu sümüle eden bir mock metot bulunmaktadır.
    """
    # Örnek kullanım: return secret_client.get(secret_name)
    return os.environ.get(secret_name, "DUMMY_GLASSNODE_API_KEY")


class GlassnodeClient(BaseMetricClient):
    """
    On-chain veri ve analiz veritabanı platformu Glassnode için istemci (Client).
    - BaseMetricClient'tan kalıtır (Cache, Redis, Rate Limits yapılarını alır)
    - Rate Limit: Püskürtmeli 30 request / 60 saniye uygulanır
    - Glassnode Array JSON formatını standardize ederek Pydantic'e uygular.
    """

    # TTL 1 Saat (3600 Saniye)
    CACHE_TTL = 3600  

    METRIC_ENDPOINTS = {
        "mvrv_zscore": "/v1/metrics/market/mvrv_z_score",
        "puell_multiple": "/v1/metrics/indicators/puell_multiple",
        "stock_to_flow": "/v1/metrics/indicators/stock_to_flow_ratio",
        "realized_price": "/v1/metrics/market/price_realized_usd",
        "pi_cycle_top": "/v1/metrics/indicators/pi_cycle_top_indicator",
        "hashrate": "/v1/metrics/mining/hash_rate_mean"
    }

    def __init__(
        self, 
        base_url: str = "https://api.glassnode.com", 
        redis_client: Optional[redis.Redis] = None,
        timeframe: str = "24h"
    ):
        super().__init__(base_url=base_url, redis_client=redis_client, timeframe=timeframe)
        
        # API anahtarını güvenli kasadan alan kısım
        self.api_key = get_vault_secret("GLASSNODE_API_KEY")
        
        # aiolimiter ile dakikada maximum 30 istek atma kuralı
        self.rate_limiter = AsyncLimiter(max_rate=30, time_period=60)
        
        # Hangi metriği çağırdığımızı arka planda (normalize işlemi için) tutan değişken
        self._current_metric: Optional[str] = None

    async def fetch_metric(self, symbol: str, metric_name: str = "mvrv_zscore") -> Optional[float]:
        """
        Standart fetch_metric fonksiyonu kalıtımdan Override edilip metric_name ile genişletildi.
        Belirlenen symbol (Örn: 'BTC') on-chain metriğini çağırıp normalize edilmiş değerini döndürür.
        """
        if metric_name not in self.METRIC_ENDPOINTS:
            raise ValueError(f"Desteklenmeyen Glassnode metriği çağırıldı: {metric_name}")

        self._current_metric = metric_name
        endpoint = self.METRIC_ENDPOINTS[metric_name]
        
        # Glassnode API Parametreleri (a=asset, i=interval, api_key=key)
        params = {
            "a": symbol.upper(),
            "api_key": self.api_key,
            "i": self.timeframe
        }

        try:
            # Yapılandırılmış Rate Limiting kordunu
            async with self.rate_limiter:
                # _validate_response yardımıyla Glassnode'un Array JSON yapısı MetricResponseSchema ile matchlenecektir.
                response_data = await self.fetch(endpoint=endpoint, params=params, cache_ttl=self.CACHE_TTL)

            if response_data is None:
                return None
                
            # Modele başarıyla yerleşmiş 'value' alanını yakalıyoruz
            raw_value = getattr(response_data, "value", None)
            
            if raw_value is None:
                return None
            
            # Subclassın kendi normalize mantığıyla işleyip 0-100 arası saf final değeri oluşturur
            return self.normalize(raw_value)
            
        except Exception as e:
            logger.error("glassnode_fetch_failed", symbol=symbol, metric=metric_name, error=str(e))
            return None

    def _validate_response(self, data: Any) -> BaseModel:
        """
        Polimorfik Override;
        Glassnode API genelde veriyi [{ "t": 1630454, "v": 12.35 }, ...] dizisiyle döner.
        Oysa bizim BaseAPIClient mimarimiz JSON Dict (BaseModel) şeması beklentisindedir.
        Ortadaki uyuşmazlığı giderip, son veriyi bulup varsayılan MetricResponseSchema objesine uyarlarız.
        """
        if isinstance(data, list) and len(data) > 0:
            last_entry = data[-1]
            if "v" in last_entry:
                try:
                    val = float(last_entry["v"])
                    return self.response_model(value=val, metadata={"t": last_entry.get("t")})
                except (ValueError, TypeError):
                    logger.warning("glassnode_value_cast_error", data=last_entry)
        
        # Beklenmedik formatta klasik Base validasyon mekanizmasını yardıma çağırır
        return super()._validate_response(data)

    def normalize(self, raw_value: Any) -> float:
        """
        Eldeki ham pür değeri, Glassnode'un sağladığı spesifik limitlerle %0 ile %100 arasına
        konumlandıran (min-max skalerleme) adaptasyon aracıdır.
        """
        metric = self._current_metric
        val = float(raw_value)

        # Referans kalibrasyon sınırları (Sektörel/Tarihsel min-max)
        limits = {
            "mvrv_zscore": {"min": -1.0, "max": 7.0},
            "puell_multiple": {"min": 0.3, "max": 5.0},
            "stock_to_flow": {"min": 0.0, "max": 100.0},
            "realized_price": {"min": 0.0, "max": 100000.0},
            "pi_cycle_top": {"min": 0.0, "max": 10.0},
            "hashrate": {"min": 0.0, "max": 500e18} 
        }

        # Bilinmeyen metriğin normalize ağırlığı neutre'e (50) eşitlenir
        if metric not in limits:
            return 50.0 
            
        range_min = limits[metric]["min"]
        range_max = limits[metric]["max"]
        
        # Clamp Values 
        if val <= range_min:
            return 0.0
        elif val >= range_max:
            return 100.0
            
        # Standard Min-Max Transformation to 0-100%
        normalized = ((val - range_min) / (range_max - range_min)) * 100.0
        return round(normalized, 2)
