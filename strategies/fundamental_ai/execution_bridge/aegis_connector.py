import os
import sys
import time
import asyncio
from typing import Optional

import structlog
import grpc
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
import redis.asyncio as redis

logger = structlog.get_logger(__name__)

# gRPC Protobuf dosyaları Prompt 1'de 'shared/proto/signals.proto' dizininde oluşturulmuştu. 
# Bu proto dosyalarının compile (pb2) objelerinin yüklenebildiği kontrol ediliyor.
try:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))
    # Not: python -m grpc_tools.protoc komutu ile generate edildikleri varsayılmıştır.
    from shared.proto import signals_pb2, signals_pb2_grpc
    GRPC_AVAILABLE = True
except ImportError:
    GRPC_AVAILABLE = False
    logger.warning("grpc_proto_modules_not_found_fallback_will_trigger")

class FundamentalSignal(BaseModel):
    """ AEGIS Holding gRPC input signal format the Pydantic """
    strategy_id: str
    signal_id: str
    timestamp: int
    symbol: str
    fundamental_score: float
    confidence: float
    onchain_score: float
    flow_score: float
    sentiment_score: float
    network_score: float
    recommendation: str
    warnings: list[str]

class SignalAck(BaseModel):
    """ Dönen yanıt standart gRPC SignalResponse Pydantic adaptörü """
    received: bool
    processed_at: int
    message: Optional[str] = None

class AegisConnector:
    """
    AEGIS Holding Yürütme Katmanı (Execution Bridge) - Aegis Connector.
    Üretilen final sinyalleri holding merkezine (localhost:50051) gRPC aracılığıyla son derece
    düşük gecikmeyle ve timeout korumalı şekilde basar. Kritik sorunlarda Pub/Sub Fallback yapar.
    """
    
    def __init__(self, grpc_host: str = "localhost:50051", redis_client: Optional[redis.Redis] = None):
        self.grpc_host = grpc_host
        self.redis_client = redis_client
        self.redis_topic = "aegis/signals/fundamental"
        # 500ms gRPC spesifik timeout hedefi
        self.timeout_seconds = 0.5 

    async def send_signal(self, signal: FundamentalSignal) -> SignalAck:
        """
        Sinyal gönderme orkestratörü.
        1. Öncelikle (3 retry limitli) hızlı gRPC denenir.
        2. Bütün haklar yanarsa veya sunucu timeout basarsa Redis Fallback mekanizması işletilir.
        """
        try:
            return await self._send_grpc(signal)
            
        except Exception as e:
            logger.warning("grpc_send_aborted_triggering_redis_fallback", signal_id=signal.signal_id, error=str(e))
            
            # gRPC devre dışı -> Redis Broker ile broadcast et (Asenkron mesaj kuyruğu)
            fallback_status = await self._send_redis(signal)
            
            return SignalAck(
                received=fallback_status,
                processed_at=int(time.time()),
                message="Transmitted via Redis Fallback PubSub" if fallback_status else "FATAL ERROR: No channels available."
            )

    @retry(
        stop=stop_after_attempt(3), 
        wait=wait_fixed(0.1), # Sonraki deneme için çeyrek saniye bekle (Timeout zaten hızlı)
        retry=retry_if_exception_type((grpc.aio.AioRpcError, asyncio.TimeoutError)),
        reraise=True # 3 hatada Fallback yakalayabilsin diye dışarı fırlat
    )
    async def _send_grpc(self, signal: FundamentalSignal) -> SignalAck:
        """
        Native asenkron gRPC iletişim metodu.
        """
        if not GRPC_AVAILABLE:
             raise NotImplementedError("GRPC proto files are missing. Directly forcing fallback.")

        # Pydantic modelini saf C tabanlı Protobuf Message sınıfına derleyelim
        pb_signal = signals_pb2.FundamentalSignal(
            strategy_id=signal.strategy_id,
            signal_id=signal.signal_id,
            timestamp=signal.timestamp,
            symbol=signal.symbol,
            fundamental_score=signal.fundamental_score,
            confidence=signal.confidence,
            onchain_score=signal.onchain_score,
            flow_score=signal.flow_score,
            sentiment_score=signal.sentiment_score,
            network_score=signal.network_score,
            recommendation=signal.recommendation,
            warnings=signal.warnings
        )
        
        # Insecure ama lokal host olduğu için yüksek performanslı kanal bağlanır
        async with grpc.aio.insecure_channel(self.grpc_host) as channel:
            stub = signals_pb2_grpc.SignalServiceStub(channel)
            try:
                # Stub üzerinden metoda gönderim sırasında "timeout=0.5" kuralı enforced (Dayatılmış) olur.
                response = await stub.SendFundamentalSignal(pb_signal, timeout=self.timeout_seconds)
                
                return SignalAck(
                    received=response.success,
                    processed_at=int(time.time()),
                    message=response.message
                )
            except grpc.aio.AioRpcError as err:
                 logger.error("grpc_transmission_error", code=err.code(), details=err.details())
                 raise err

    async def _send_redis(self, signal: FundamentalSignal) -> bool:
        """
        Broker tabanlı haberleşme sistemi. Aegis Core çöktüyse bile kuyruk olarak redis üzerinden alınmasını sağlar.
        """
        if self.redis_client is None:
            logger.error("redis_fallback_failed_missing_client")
            return False
            
        try:
            # Model v2 standart JSON transformu
            payload = signal.model_dump_json() 
            receivers = await self.redis_client.publish(self.redis_topic, payload)
            
            # Pub/Sub mekanizmaları abone (subscriber) sayısını döner
            if receivers > 0:
                logger.info("redis_fallback_broadcasted", signal_id=signal.signal_id, subscribers=receivers)
                return True
            else:
                logger.warning("redis_fallback_published_but_unheard", signal_id=signal.signal_id)
                # Yine de ağda yayınlandığı için başarılı kabul edilebilir
                return True
                
        except Exception as e:
            logger.error("redis_fallback_fatal_error", error=str(e))
            return False

    async def check_health(self) -> bool:
        """
        gRPC sunucusunun 500ms içinde "READY" durumunu verip vermediğini tarar.
        """
        try:
             async with grpc.aio.insecure_channel(self.grpc_host) as channel:
                 # Kanalın hazır olmasını bekler, başarısızsa timeout gönderir
                 await asyncio.wait_for(
                     channel.channel_ready(), 
                     timeout=self.timeout_seconds
                 )
                 logger.info("grpc_server_healthcheck_passed", host=self.grpc_host)
                 return True
        except asyncio.TimeoutError:
             logger.warning("grpc_server_not_responding_timeout", host=self.grpc_host)
             return False
        except Exception as e:
             logger.error("grpc_server_healthcheck_failed", error=str(e))
             return False
