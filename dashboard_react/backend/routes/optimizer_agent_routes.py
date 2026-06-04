"""
Optimizasyon Agent kontrol endpoint'leri.

POST /api/optimizer/run     → tüm uzayı taramaya başla (arka plan)
POST /api/optimizer/stop    → durdur
GET  /api/optimizer/status  → ilerleme + en iyi + uygulanan
GET  /api/optimizer/results → OOS-doğrulanmış sıralı sonuçlar
GET  /api/optimizer/applied → şu an sisteme uygulanan config
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, Body, Query
from typing import Any, Dict

from services.optimizer_agent import get_optimizer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/optimizer", tags=["optimizer"])


@router.post("/run")
async def optimizer_run(body: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    """
    Optimizasyonu başlat. Opsiyonel override:
      { "timeframes": ["4h","1d"], "n_candidates_per_tf": 80,
        "start_date": "2022-10-01", "end_date": "2025-09-28" }
    """
    return await get_optimizer().start(overrides=body or None)


@router.post("/stop")
async def optimizer_stop() -> Dict[str, Any]:
    return await get_optimizer().stop()


@router.post("/auto/start")
async def optimizer_auto_start(body: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    """
    OTONOM mod: agent periyodik kendi tarar + en SAĞLAM config'i otomatik uygular.
    Opsiyonel: { "auto_interval_hours": 24, "timeframes": ["4h","1d"],
                 "n_candidates_per_tf": 80, "min_profit_factor": 1.05 }
    """
    return await get_optimizer().start_auto(overrides=body or None)


@router.post("/auto/stop")
async def optimizer_auto_stop() -> Dict[str, Any]:
    return await get_optimizer().stop_auto()


@router.get("/status")
async def optimizer_status() -> Dict[str, Any]:
    return get_optimizer().status()


@router.get("/results")
async def optimizer_results(limit: int = Query(15, ge=1, le=50)) -> Dict[str, Any]:
    return get_optimizer().results(limit=limit)


@router.get("/applied")
async def optimizer_applied() -> Dict[str, Any]:
    applied = get_optimizer().get_applied()
    return {"applied": applied, "active": applied is not None}
