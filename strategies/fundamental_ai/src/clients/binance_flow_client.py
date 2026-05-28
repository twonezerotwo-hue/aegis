import os
import sys
import asyncio
import json
from typing import Any, Optional

import structlog
from pydantic import BaseModel
import websockets
import redis.asyncio as redis
from aiolimiter import AsyncLimiter

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))
from strategies.fundamental_ai.src.clients.base_metric_client import BaseMetricClient

logger = structlog.get_logger(__name__)

class BinanceFlowClient(BaseMetricClient):
    """
    Binance Futures Public API İstemcisi.
    Kısa vadeli likidite akış (Flow) verilerini, yani Funding Rate,
    Open Interest (Açık Pozisyonlar) ve Long/Short oranlarını takip eder.
    
    Özellikleri:
    - Auth (API_KEY) gerektirmez.
    - Saniyede 20 request limite takılmaz (aiolimiter ile limitlenir).
    - TTL Cache: Dinamik market için 1 dakika çok idealdir.
    - REST isteği Limitlendiğinde/Sustuğunda WebSocket Stream Fallback çalışır.
    """
    
    # Sık değişen piyasa koşulları sebebiyle 60 saniyelik agresif TTL
    CACHE_TTL = 60

    METRIC_ENDPOINTS = {
        "funding_rate": "/fapi/v1/premiumIndex", 
        "open_interest": "/fapi/v1/openInterest",
        "long_short_ratio": "/futures/data/globalLongShortAccountRatio"
    }

    # REST Endpoint'ten dönen spesifik JSON key'inin standartlaştırılması için harita eşleştirmesi
    KEY_MAP = {
        "funding_rate": "lastFundingRate",
        "open_interest": "openInterest",
        "long_short_ratio": "longShortRatio"  # /globalLongShortAccountRatio array döner
    }

    def __init__(
        self, 
        base_url: str = "https://fapi.binance.com", 
        redis_client: Optional[redis.Redis] = None,
        timeframe: str = "15m"
    ):
        super().__init__(base_url=base_url, redis_client=redis_client, timeframe=timeframe)
        
        # Rate limit: 20 istek / 1 saniye kısıtlaması
        self.rate_limiter = AsyncLimiter(max_rate=20, time_period=1)
        self._current_metric: Optional[str] = None
        
        # WebSocket adresi Fallback mekanizması için
        self.ws_url = "wss://fstream.binance.com/ws"

    async def fetch_metric(self, symbol: str, metric_name: str = "funding_rate") -> Optional[float]:
        """
        Binance Futures'dan symbol (Örn: BTCUSDT) için metrik çeker.
        Eğer fail olursa WS stream tabanlı veri denemesi yapılır.
        """
        if metric_name not in self.METRIC_ENDPOINTS:
            raise ValueError(f"Desteklenmeyen Binance metriği çağırıldı: {metric_name}")

        self._current_metric = metric_name
        endpoint = self.METRIC_ENDPOINTS[metric_name]
        
        # Symbol query olarak zorunludur
        params = {"symbol": symbol.upper()}
        # Long/Short hesabı için API periyot ister (örn: '5m', '15m' vb)
        if metric_name == "long_short_ratio":
            params["period"] = self.timeframe
            
        try:
            # Saniyelik istek kısıtlamalarını bekletir (Async Wait)
            async with self.rate_limiter:
                # _validate_response metodu dönen json'u parseleyip MetricResponseSchema şekline getirecektir.
                response_data = await self.fetch(endpoint=endpoint, params=params, cache_ttl=self.CACHE_TTL)

            if response_data is None:
                raise Exception("Empty REST response structure")
                
            raw_value = getattr(response_data, "value", None)
            
            if raw_value is None:
                raise Exception("Missing 'value' parameter mapped recursively")
            
            # Normalizer üzerinden 0-100 Skalasına indirge
            return self.normalize(raw_value)
            
        except Exception as e:
            logger.warning("binance_rest_failed_fallback_ws", symbol=symbol, metric=metric_name, error=str(e))
            # REST APIden response başarısız olduğunda WebSocket (WS) streamine Fallback dene.
            fallback_val = await self._fetch_via_websocket(symbol, metric_name)
            if fallback_val is not None:
                return self.normalize(fallback_val)
            return None

    def _validate_response(self, data: Any) -> BaseModel:
        """
        Binance API formatını Generic MetricResponseSchema'ya çevirir.
        """
        metric = self._current_metric
        target_key = self.KEY_MAP.get(metric)

        # Rate Endpointleri için Array/JSON dict check listesi
        if isinstance(data, list) and len(data) > 0:
            last_entry = data[-1]
            if target_key in last_entry:
                try:
                    val = float(last_entry[target_key])
                    return self.response_model(value=val)
                except (ValueError, TypeError):
                    pass
        elif isinstance(data, dict):
            if target_key in data:
                try:
                    val = float(data[target_key])
                    return self.response_model(value=val)
                except (ValueError, TypeError):
                    pass

        # Beklenmedik formatlara fallback standart adaptasyonu
        return super()._validate_response(data)

    async def _fetch_via_websocket(self, symbol: str, metric_name: str) -> Optional[float]:
        """
        REST API limitlendiğinde (Banned IP veya Timeout)
        WebSocket streaminden güncel bir snap value okur.
        """
        sym_lower = symbol.lower()
        ws_endpoint = ""
        target_key = ""

        # WS Endpoint ve map adımları
        if metric_name == "funding_rate":
            ws_endpoint = f"/{sym_lower}@markPrice"
            target_key = "r" # funding rate socket key'i 'r' formatındadır
        else:
            # (Diğer metrikler için doğrudan stream kanalı public değilse fallback yoktur)
            logger.debug("ws_fallback_not_available_for_metric", metric=metric_name)
            return None

        full_url = f"{self.ws_url}{ws_endpoint}"
        
        try:
            # Sadece tek frame bekleyerek okuyup kapatır
            async with websockets.connect(full_url, ping_interval=None) as websocket:
                # Maksimum bekleme süresi 5 sn
                message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                json_data = json.loads(message)
                if target_key in json_data:
                    return float(json_data[target_key])
        except Exception as e:
            logger.error("binance_ws_fallback_failed", symbol=symbol, error=str(e))
        
        return None

    def normalize(self, raw_value: Any) -> float:
        """
        Min-Max yöntemi ile metrik hedeflerini 0-100 Skalasına oturtur.
        """
        metric = self._current_metric
        val = float(raw_value)

        # Referans kalibrasyon sınırları
        # Notlar: Funding rate genel volatilitesi %0.2 üzerinden
        # Open interest Limitsiz artabilir fakat ortalama nominal değer uydurması.
        limits = {
            "funding_rate": {"min": -0.002, "max": 0.002},
            "open_interest": {"min": 0.0, "max": 100000.0}, # BTC cinsinden nominal 100K BTC OI
            "long_short_ratio": {"min": 0.5, "max": 3.0} 
        }

        # Bilinmeyen metriğin oranı %50 (nötr) kabul edilir.
        if metric not in limits:
            return 50.0 
            
        range_min = limits[metric]["min"]
        range_max = limits[metric]["max"]
        
        # Clamp Values 
        if val <= range_min:
            return 0.0
        elif val >= range_max:
            return 100.0
            
        # Min-Max Scaling Formülü
        normalized = ((val - range_min) / (range_max - range_min)) * 100.0
        return round(normalized, 2)
