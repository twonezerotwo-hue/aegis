"""
Otonom Paper Trader endpoint'leri — agent config'ini gerçek zamanlı, parasız test.

POST /api/paper_auto/start   → başlat (agent'ın uyguladığı config ile)
POST /api/paper_auto/stop    → durdur
POST /api/paper_auto/reset   → sıfırla + yeniden başlat
GET  /api/paper_auto/status  → canlı durum (pozisyon, equity, işlemler)
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, Body
from typing import Any, Dict

from services.paper_autotrader import get_paper_trader

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/paper_auto", tags=["paper_auto"])


@router.post("/start")
async def paper_start(body: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    return await get_paper_trader().start(reset=bool(body.get("reset", False)))


@router.post("/stop")
async def paper_stop() -> Dict[str, Any]:
    return await get_paper_trader().stop()


@router.post("/reset")
async def paper_reset() -> Dict[str, Any]:
    t = get_paper_trader()
    await t.stop()
    return await t.start(reset=True)


@router.get("/status")
async def paper_status() -> Dict[str, Any]:
    return get_paper_trader().status()
