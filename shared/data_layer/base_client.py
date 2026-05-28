import abc
import asyncio
import json
import time
from typing import Any, Dict, Optional, Type, TypeVar

import aiohttp
import structlog
from pydantic import BaseModel, ValidationError
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
import redis.asyncio as redis

logger = structlog.get_logger(__name__)

T = TypeVar('T', bound=BaseModel)

class APIClientError(Exception):
    """Base exception for API Client errors."""
    pass

class CircuitBreakerOpenException(APIClientError):
    """Raised when the circuit breaker is open."""
    pass

class SimpleCircuitBreaker:
    """
    Şart koşulan Circuit Breaker (Devre Kesici) uygulaması:
    Peş peşe gelen 5 hatadan sonra devre 'OPEN' (açık) durumuna geçer,
    60 saniye bekledikten sonra tekrar 'HALF_OPEN' durumuna esneklik gösterir.
    """
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = "CLOSED"  # Durumlar: CLOSED, OPEN, HALF_OPEN
        
    def check(self):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
                logger.info("circuit_breaker_half_open")
            else:
                raise CircuitBreakerOpenException(f"Circuit breaker is OPEN. Retry after {self.recovery_timeout}s.")
                
    def record_success(self):
        if self.state in ("OPEN", "HALF_OPEN"):
            logger.info("circuit_breaker_closed")
        self.state = "CLOSED"
        self.failure_count = 0
        
    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold and self.state != "OPEN":
            self.state = "OPEN"
            logger.error("circuit_breaker_open", 
                         threshold=self.failure_threshold, 
                         timeout=self.recovery_timeout)


class BaseAPIClient(abc.ABC):
    """
    Tüm API Client'lar için Abstract Base Class (Temel Sınıf).
    
    Özellikleri:
    - Async HTTP İstekleri Yönetimi (aiohttp)
    - Redis Caching (Önbellekleme, TTL yönetimi)
    - Yanıt validasyonu (Pydantic)
    - Yapılandırılmış Loglama (structlog)
    """

    def __init__(
        self, 
        base_url: str, 
        redis_client: redis.Redis,
        response_model: Type[T]
    ):
        self.base_url = base_url.rstrip("/")
        self.redis_client = redis_client
        self.response_model = response_model
        
        # Gereksinim: 5 başarısız istekte 60 saniye boyunca devreyi kes
        self.circuit_breaker = SimpleCircuitBreaker(failure_threshold=5, recovery_timeout=60)

    def _get_cache_key(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> str:
        """Redis için tutarlı bir önbellek anahtarı oluşturur."""
        key_parts = [self.__class__.__name__, self.base_url, endpoint]
        if params:
            key_parts.append(json.dumps(params, sort_keys=True))
        return "api_cache:" + ":".join(key_parts)

    async def fetch(self, endpoint: str, params: Optional[Dict[str, Any]] = None, cache_ttl: int = 0) -> BaseModel:
        """
        Dışarıya açık veri çekme metodumuz.
        Sırasıyla aşağıdaki işlemleri yapar:
        1. TTL değeri sağlanmışsa Redis önbelleğini kontrol eder.
        2. _call_api fonksiyonunu kullanarak Circuit Breaker ve Retry mekanizmasıyla API'yi çağırır.
        3. Dönen ham JSON yanıtını Pydantic ile validate eder.
        4. Validate edilen veriyi Redis hedefine kaydeder.
        """
        cache_key = self._get_cache_key(endpoint, params)
        
        # 1. Redis Cache Kontrolü
        if cache_ttl > 0:
            try:
                cached_data = await self.redis_client.get(cache_key)
                if cached_data:
                    logger.debug("cache_hit", endpoint=endpoint)
                    parsed_data = json.loads(cached_data)
                    return self._validate_response(parsed_data)
            except Exception as e:
                logger.warning("redis_cache_get_error", error=str(e), endpoint=endpoint)

        # 2. Circuit Breaker Kontrolü & API Çağrısı
        self.circuit_breaker.check()
        
        try:
            raw_data = await self._call_api(endpoint, params)
            self.circuit_breaker.record_success()
        except Exception as e:
            self.circuit_breaker.record_failure()
            logger.error("api_fetch_failed", endpoint=endpoint, error=str(e))
            raise APIClientError(f"Failed to fetch data from {endpoint}: {str(e)}") from e

        # 3. Pydantic ile Doğrulama (Validation)
        validated_data = self._validate_response(raw_data)

        # 4. JSON Formatında Redis'e Kaydetme
        if cache_ttl > 0 and validated_data:
            try:
                # Pydantic v2 (model_dump_json) ve v1 (json) desteği
                if hasattr(validated_data, 'model_dump_json'):
                    data_to_cache = validated_data.model_dump_json()
                else:
                    data_to_cache = validated_data.json()
                    
                await self.redis_client.set(cache_key, data_to_cache, ex=cache_ttl)
                logger.debug("cache_set", endpoint=endpoint, ttl=cache_ttl)
            except Exception as e:
                logger.warning("redis_cache_set_error", error=str(e), endpoint=endpoint)

        return validated_data

    # Gereksinim: Tenacity ile max 3 kez yeniden dene (sadece aiohttp ve timeout hatalarında geçerli),
    # denemeler arasında 2 saniye bekle.
    @retry(
        stop=stop_after_attempt(3), 
        wait=wait_fixed(2),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        reraise=True
    )
    async def _call_api(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """
        Tenacity kılıfı ile korunan güvenli iç metod (Internal API caller).
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        logger.info("calling_api", url=url, params=params)
        
        timeout = aiohttp.ClientTimeout(total=10) # Deneme başına 10s varsayılan timeout
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as response:
                response.raise_for_status()
                # API yanıtının JSON olarak beklendiği varsayılır (normalize edilmiş JSON yanıtı)
                return await response.json()

    def _validate_response(self, data: Any) -> BaseModel:
        """
        Alınan ham veriyi, başlatılırken belirtilen Pydantic Modeli ile doğrular.
        """
        try:
            # Pydantic v2 ve v1 geriye dönük uyumluluğu
            if hasattr(self.response_model, 'model_validate'):
                return self.response_model.model_validate(data)
            else:
                return self.response_model.parse_obj(data)
        except ValidationError as e:
            logger.error("response_validation_error", errors=e.errors(), raw_data=data)
            raise APIClientError("Data format validation failed") from e
