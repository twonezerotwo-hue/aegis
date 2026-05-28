from datetime import timezone
"""
News AI Limited - Admin/Config Endpoints
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from ..logging.logger_config import get_logger
from ..data_sources.source_registry import SourceRegistry

logger = get_logger(__name__)

router = APIRouter(tags=["admin"], prefix="/config")

# Shared registry instance — set by main.py after startup
_registry: SourceRegistry | None = None


def set_registry(registry: SourceRegistry) -> None:
    """Called by main.py to inject the live SourceRegistry instance."""
    global _registry
    _registry = registry


class ConfigUpdate(BaseModel):
    """Model for POST /config"""
    enabled_sources: Optional[List[str]] = None
    sentiment_model: Optional[str] = None
    update_frequency_minutes: Optional[int] = None


@router.post("")
async def update_config(request: ConfigUpdate):
    """
    Update module configuration at runtime

    Allows enabling/disabling news sources, switching sentiment models, and adjusting update frequency.
    """
    try:
        logger.info(
            "config_updated",
            enabled_sources=request.enabled_sources,
            sentiment_model=request.sentiment_model,
        )

        # TODO: Apply configuration changes

        return {
            "status": "updated",
            "timestamp": __import__("datetime").datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"config_update_error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/dedup/stats")
async def get_dedup_stats():
    """
    Deduplication istatistiklerini döndürür.

    - memory_stats: süreç yeniden başlatıncaya kadar geçerli sayaçlar
    - redis_stats : Redis'ten çekilen kalıcı sayaçlar
    - thresholds  : motor yapılandırması
    """
    if _registry is None:
        return {"error": "registry_not_initialized"}
    return _registry.dedup_engine.get_stats()


@router.delete("/dedup/cache/memory")
async def clear_dedup_memory_cache():
    """
    In-memory dedup önbelleğini temizler.
    Redis'teki kalıcı hash kayıtlarına dokunmaz.
    Kullanım alanı: geliştirme/test ortamında önbelleği sıfırlamak.
    """
    if _registry is None:
        raise HTTPException(status_code=503, detail="registry_not_initialized")
    result = _registry.dedup_engine.clear_memory_cache()
    logger.warning("dedup_memory_cache_cleared_via_api result=%s", result)
    return {"status": "cleared", **result}


@router.delete("/dedup/cache/redis")
async def clear_dedup_redis_cache():
    """
    Redis'teki tüm dedup hash kayıtlarını siler.
    UYARI: Benzersizlik geçmişi sıfırlanır — sadece bakım/acil durumlarda kullanın.
    """
    if _registry is None:
        raise HTTPException(status_code=503, detail="registry_not_initialized")
    result = _registry.dedup_engine.clear_redis_cache()
    logger.warning("dedup_redis_cache_cleared_via_api result=%s", result)
    return {"status": "cleared", **result}


@router.get("/sources")
async def list_sources():
    """Tüm kayıtlı haber kaynaklarının durumunu döndürür."""
    if _registry is None:
        return {"error": "registry_not_initialized"}
    return {
        "sources": _registry.get_all_sources_status(),
        "total": len(_registry.sources),
        "enabled": sum(1 for s in _registry.sources.values() if s.is_enabled),
    }
