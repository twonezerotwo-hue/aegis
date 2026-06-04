"""
Uyarı/Bildirim endpoint'leri.

GET  /api/alerts          → son uyarılar (sinyal, hata, kill-switch)
GET  /api/alerts/status   → bildirim durumu (Telegram yapılandırıldı mı)
POST /api/alerts/test     → test uyarısı gönder (Telegram doğrulama)
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, Body, Query
from typing import Any, Dict, Optional

from services.notifier import get_alerts, status as notifier_status, notify

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
async def list_alerts(limit: int = Query(50, ge=1, le=200), category: Optional[str] = None) -> Dict[str, Any]:
    return {"alerts": get_alerts(limit=limit, category=category)}


@router.get("/status")
async def alerts_status() -> Dict[str, Any]:
    return notifier_status()


@router.post("/test")
async def alerts_test(body: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    msg = body.get("message", "AEGIS test bildirimi — sistem çalışıyor.")
    alert = notify("system", msg, level="success")
    return {"sent": alert, "telegram_sent": alert.get("telegram_sent")}
