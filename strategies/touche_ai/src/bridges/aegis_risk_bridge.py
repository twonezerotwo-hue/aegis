"""
Touche AI Limited — AEGIS Risk Bridge

Fundamental AI modülünden güncel makro skoru asenkron olarak çeker.
Timeout veya hata durumunda None döner — Faz7 bu durumu tolere eder.

Holding içi iletişim: Redis Pub/Sub (öncelikli) veya HTTP (fallback).
"""
import asyncio
import json
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

_DEFAULT_TIMEOUT = 2.0       # 2 saniye — Faz7 timeout eşiği
_REDIS_CHANNEL   = "aegis/signals/fundamental"
_HTTP_ENDPOINT   = "http://localhost:8001/api/v1/fundamental/latest"


class AegisRiskBridge:
    """
    Touche AI → Fundamental AI iletişim köprüsü.

    Öncelik Sırası:
    1. Redis Pub/Sub son sinyal cache'i
    2. HTTP REST endpoint (fallback)
    3. None (tüm kanallar erişilemez)

    Kullanım:
        bridge = AegisRiskBridge(redis_client=redis_conn)
        score = await bridge.get_fundamental_score("BTCUSDT")
    """

    def __init__(
        self,
        redis_client=None,
        http_timeout: float = _DEFAULT_TIMEOUT,
    ):
        self.redis_client = redis_client
        self.http_timeout = http_timeout
        self._cache_key = "touche:fundamental_score_cache"

    async def get_fundamental_score(self, symbol: str) -> Optional[float]:
        """
        Belirtilen sembol için güncel Fundamental AI skorunu getirir.
        Zaman aşımında veya hata durumunda None döner (Faz7 bunu tolere eder).
        """
        try:
            return await asyncio.wait_for(
                self._fetch_score(symbol),
                timeout=self.http_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("aegis_bridge_timeout", symbol=symbol, timeout=self.http_timeout)
            return None
        except Exception as e:
            logger.error("aegis_bridge_error", symbol=symbol, error=str(e))
            return None

    async def _fetch_score(self, symbol: str) -> Optional[float]:
        """Önce Redis cache, sonra HTTP fallback ile skor getirir."""

        # 1. Redis Cache Kontrolü
        if self.redis_client is not None:
            cached = await self._get_from_redis(symbol)
            if cached is not None:
                logger.debug("aegis_bridge_redis_hit", symbol=symbol, score=cached)
                return cached

        # 2. HTTP Fallback
        score = await self._get_from_http(symbol)
        if score is not None and self.redis_client is not None:
            # Başarılı sonucu 60 saniye cache'e yaz
            await self._set_redis_cache(symbol, score, ttl=60)
        return score

    async def _get_from_redis(self, symbol: str) -> Optional[float]:
        """Redis'te son sinyal cache'ini kontrol eder."""
        try:
            key = f"{self._cache_key}:{symbol}"
            raw = await self.redis_client.get(key)
            if raw:
                data = json.loads(raw)
                return float(data.get("fundamental_score", 0.0))
        except Exception as e:
            logger.warning("aegis_bridge_redis_read_error", error=str(e))
        return None

    async def _set_redis_cache(self, symbol: str, score: float, ttl: int = 60) -> None:
        """Fundamental skoru Redis'e yazar."""
        try:
            key = f"{self._cache_key}:{symbol}"
            payload = json.dumps({"fundamental_score": score, "symbol": symbol})
            await self.redis_client.set(key, payload, ex=ttl)
        except Exception as e:
            logger.warning("aegis_bridge_redis_write_error", error=str(e))

    async def _get_from_http(self, symbol: str) -> Optional[float]:
        """Fundamental AI REST API'sinden skor çeker."""
        try:
            import aiohttp
            url = f"{_HTTP_ENDPOINT}?symbol={symbol}"
            timeout = aiohttp.ClientTimeout(total=self.http_timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        score = float(data.get("fundamental_score", 50.0))
                        logger.debug("aegis_bridge_http_hit", symbol=symbol, score=score)
                        return score
                    else:
                        logger.warning("aegis_bridge_http_bad_status",
                                       symbol=symbol, status=resp.status)
                        return None
        except ImportError:
            logger.warning("aegis_bridge_aiohttp_not_installed")
            return None
        except Exception as e:
            logger.warning("aegis_bridge_http_error", symbol=symbol, error=str(e))
            return None

    async def publish_touche_signal(self, symbol: str, signal_data: dict) -> bool:
        """
        Touche sinyalini Consensus Engine'e Redis Pub/Sub üzerinden yayınlar.
        AegisConnector benzeri geri besleme kanalı.
        """
        if self.redis_client is None:
            logger.warning("aegis_bridge_no_redis_for_publish")
            return False
        try:
            channel = f"aegis/signals/touche/{symbol}"
            payload = json.dumps(signal_data)
            receivers = await self.redis_client.publish(channel, payload)
            logger.info("aegis_bridge_signal_published", channel=channel, subscribers=receivers)
            return True
        except Exception as e:
            logger.error("aegis_bridge_publish_error", error=str(e))
            return False
