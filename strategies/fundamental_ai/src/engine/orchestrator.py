import asyncio
import structlog
from typing import Dict, Any, List

logger = structlog.get_logger(__name__)

class MetricOrchestrator:
    """
    AEGIS Holding - Fundamental AI Engine (Motor Sınıfı)
    Farklı sağlayıcılardan (Binance, Glassnode vs.) gelen on-chain ve off-chain 
    istekleri paralel biçimde toplayarak ana algoritmanın beklediği global haritayı çıkarır.
    """

    def __init__(self, clients_config: List[Dict[str, Any]]):
        """
        Birden çok (Örn. 5 farklı metrik sağlayan) client konfigürasyon paketi alır.
        
        Yapı:
        [
            {
                "name": "mvrv",                 # Çıktıdaki anahtar isimlendirme
                "client": glassnode_client,     # Somut oluşturulmuş client objesi
                "method": "fetch_metric",       # Çağırılacak fonksiyon ismi
                "kwargs": {"metric_name": "mvrv_zscore"} # Fonksiyona ek parametreler
            },
            ...
        ]
        """
        self.clients_config = clients_config
        # Bütün API çağrıları için agresif global timeout sınırı
        self.timeout_seconds = 2.0

    async def _fetch_with_timeout(self, client: Any, method: str, symbol: str, **kwargs) -> Any:
        """
        Parametrede iletilen Client ve metot ismini dinamik bulup 2 saniye kısıtlaması ile çalıştırır.
        Sınırsız (blocking) beklemeleri keser, bir hata gördüğünde Null (None) döner ve yayılmasına engel olur.
        Client içerisindeki Cache denetimleri bu çağrı üzerinden metot içeriğinde işler.
        """
        try:
            # Obje (Örn. glassnode_client) üzerinden metodunu bul (örn. fetch_metric)
            func = getattr(client, method)
            
            # Asenkron Coroutine objesini çalıştırtıp hazırlatıyoruz
            coro = func(symbol, **kwargs)
            
            # asyncio kalkanı ile Max 2s müddet veriyoruz
            result = await asyncio.wait_for(coro, timeout=self.timeout_seconds)
            return result
            
        except asyncio.TimeoutError:
            logger.error("orchestrator_client_timeout", method=method, symbol=symbol, time_limit=f"{self.timeout_seconds}s")
            return None
        except Exception as e:
            logger.error("orchestrator_client_corrupted", method=method, symbol=symbol, error=str(e))
            return None

    async def fetch_all_metrics(self, symbol: str) -> Dict[str, Any]:
        """
        Kayıtlı metrik görevlerini 'asyncio.gather' aracılığıyla aynı anda başlatıp, asenkron verimli ağaç kurar.
        Client'lardan birinin hataya düşmesi (veya Timeout yemesi) diğerinin çalışmasını bozmaz (None olarak toplanır).
        """
        # Temiz Symbol okuması (örn: BTC/USDT formatı geldiyse BTCUSDT yapar)
        # Client tabanlı uyumluluk arayüzü ayarı için.
        formatted_symbol = symbol.replace("/", "").replace("-", "")
        
        logger.info("orchestrator_parallel_task_start", symbol=formatted_symbol, target=len(self.clients_config))

        tasks = []
        keys = []
        
        for config in self.clients_config:
            metric_key = config.get("name", "unknown")
            client = config.get("client")
            method = config.get("method", "fetch_metric")
            kwargs = config.get("kwargs", {})
            
            # Timeout sınırlayıcı wrappera istekleri gömüp Task (Görev) havuzuna paslıyoruz 
            task = self._fetch_with_timeout(client, method, formatted_symbol, **kwargs)
            tasks.append(task)
            keys.append(metric_key)

        # Temel asenkron Paralel işlem yürütme kanalı
        # return_exceptions=True: Görmezden gelinmeyi başarısız gather ları çökertmeden yutturmayı sağlar.
        results = await asyncio.gather(*tasks, return_exceptions=True)

        payload_metrics = {}
        successful_connections = 0

        for key, res in zip(keys, results):
            # Ekstra güvenlik: asyncio en kötü senaryoda task patlarsa exception dönebilir.
            if isinstance(res, Exception):
                logger.error("orchestrator_critical_task_exception", component=key, error=str(res))
                payload_metrics[key] = None
            else:
                payload_metrics[key] = res
                if res is not None:
                    successful_connections += 1
                    
        # Özet Loglama
        logger.info(
            "orchestrator_execution_synced", 
            symbol=formatted_symbol, 
            reliability=f"{successful_connections}/{len(keys)}"
        )
        
        return payload_metrics

FundamentalOrchestrator = MetricOrchestrator
