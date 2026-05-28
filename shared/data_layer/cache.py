import json
import zlib
from typing import Any, List, Dict, Optional, Union

import structlog
from redis.asyncio.cluster import RedisCluster
from prometheus_client import Counter

logger = structlog.get_logger(__name__)

# Cache Hit/Miss Metrikleri (Prometheus)
CACHE_HITS = Counter("cache_hits_total", "Total number of cache hits")
CACHE_MISSES = Counter("cache_misses_total", "Total number of cache misses")
CACHE_ERRORS = Counter("cache_errors_total", "Total number of cache errors")

# Boyutu 1KB'ı geçen payload'lar zlib ile sıkıştırılacak
COMPRESSION_THRESHOLD = 1024  

class CacheManager:
    """
    Redis Cluster tabanlı Önbellek Yönetim Sınıfı (Cache Manager).
    
    Özellikleri:
    - Redis Cluster Desteği (redis.asyncio.cluster)
    - Otomatik TTL yönetimi
    - Asenkron işlem yürütme (Async/Await)
    - Büyük veriler için 'zlib' ile Compression (Sıkıştırma)
    - 'prometheus_client' ile Cache Hit/Miss/Error metrikleri
    """

    def __init__(self, startup_nodes: List[Dict[str, Union[str, int]]]):
        """
        Örnek startup_nodes: [{"host": "127.0.0.1", "port": "7000"}, ...]
        """
        # Node verilerini string değerlere parse edip uyarlayalım
        formatted_nodes = [{"host": n["host"], "port": str(n["port"])} for n in startup_nodes]
        
        self.client = RedisCluster(
            startup_nodes=formatted_nodes,
            # Sıkıştırma kullandığımız için ham byte düzeyinde manipülasyona 
            # ihtiyacımız var, bu yüzden decode_responses'ı False bırakıyoruz.
            decode_responses=False
        )
        logger.info("cache_manager_initialized", node_count=len(formatted_nodes))

    async def get(self, key: str) -> Optional[Any]:
        """
        Verilen key ile cache'ten değer okur. 
        Prometheus Hit/Miss metriklerini günceller.
        Sıkıştırılmış ise decompress yapar, ardında JSON parse edip döner.
        """
        try:
            raw_data = await self.client.get(key)
            
            if raw_data is None:
                CACHE_MISSES.inc()
                return None
                
            CACHE_HITS.inc()
            
            # Veriyi açma (Decompression)
            try:
                # Önce zlib decompress denenir
                decompressed_data = zlib.decompress(raw_data)
                json_str = decompressed_data.decode('utf-8')
            except zlib.error:
                # Veri sıkıştırılmamışsa, ham string olarak utf-8 formatında okunur
                json_str = raw_data.decode('utf-8')
                
            return json.loads(json_str)

        except Exception as e:
            CACHE_ERRORS.inc()
            logger.error("cache_get_error", key=key, error=str(e))
            return None

    async def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """
        Gelen payload'ı JSON dizgisine çevirir. 
        Kritik eşiğin üstündeyse 'zlib' ile sıkıştırır ve TTL süresi atayarak 
        Redis Cluster'a ekler.
        """
        try:
            json_str = json.dumps(value)
            payload = json_str.encode('utf-8')
            
            if len(payload) > COMPRESSION_THRESHOLD:
                payload = zlib.compress(payload)
                
            await self.client.set(key, payload, ex=ttl)
            return True
            
        except Exception as e:
            CACHE_ERRORS.inc()
            logger.error("cache_set_error", key=key, error=str(e))
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """
        Scan Iterator kullanarak sağlanan pattern'e eşleşen tüm key'leri siler.
        Büyük Redis Cluster kümelerinde doğrudan keys() kullanmak sakıncalı 
        olduğu için scan_iter asenkron loop'u ile yürütülür.
        """
        deleted_count = 0
        try:
            # Cluster modunda cross-slot deletion genelde desteklenmediği için iteratif bir yol izlenir
            async for key in self.client.scan_iter(match=pattern):
                await self.client.delete(key)
                deleted_count += 1
                
            return deleted_count
        except Exception as e:
            CACHE_ERRORS.inc()
            logger.error("cache_delete_pattern_error", pattern=pattern, error=str(e))
            return deleted_count

    def get_metrics(self) -> Dict[str, float]:
        """
        Anlık hit, miss ve error metriklerinin snapshot formatını döndürür.
        """
        # _value.get() prometheus mantığında sayaçları okumak için kullanılır
        return {
            "hits": CACHE_HITS._value.get(),
            "misses": CACHE_MISSES._value.get(),
            "errors": CACHE_ERRORS._value.get(),
        }
