"""
AEGIS Agent kontrol endpoint'leri.

GET  /api/agent/status        → agent durumu (çalışıyor mu, config, heartbeat)
GET  /api/agent/journal       → son kararlar (karar günlüğü)
POST /api/agent/start         → otonom döngüyü başlat
POST /api/agent/stop          → döngüyü durdur
POST /api/agent/run_once      → tek döngü çalıştır (test)
POST /api/agent/config        → çalışma zamanı config güncelle (interval, semboller, eşikler)

GÜVENLİK: agent gerçek emir göndermez. Start etmek bile DRY_RUN modunda
yalnızca karar günlüğü üretir. Gerçek para için EXECUTION_MODE=MANUAL_APPROVAL
gerekir ve her sinyal insan onayı bekler.
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, Body, Query
from typing import Any, Dict

from services.agent_loop import get_agent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("/status")
async def agent_status() -> Dict[str, Any]:
    """Agent yaşam döngüsü + config + heartbeat."""
    return get_agent().status()


@router.get("/journal")
async def agent_journal(limit: int = Query(50, ge=1, le=250)) -> Dict[str, Any]:
    """Son kararlar (en yeni önce)."""
    agent = get_agent()
    return {
        "decisions": agent.recent_journal(limit=limit),
        "total_in_memory": len(agent.journal),
    }


@router.get("/research/summary")
async def agent_research_summary(limit: int = Query(500, ge=1, le=5000)) -> Dict[str, Any]:
    """Research-only candidate summary. Does not change runtime config."""
    from aegis_research.data_adapters import adapter_inventory
    from aegis_research.metrics import optional_dependency_status
    from aegis_research.outcomes import get_default_store

    return {
        "summary": get_default_store().summarize(limit=limit),
        "optional_metrics": optional_dependency_status(),
        "data_adapters": adapter_inventory(),
        "safe_mode": "RESEARCH_ONLY_NO_EXECUTION",
    }


@router.get("/research/suggestions")
async def agent_research_suggestions(limit: int = Query(500, ge=1, le=5000)) -> Dict[str, Any]:
    """Shadow-only threshold suggestions. Owner approval is required separately."""
    from aegis_research.calibration import suggest_thresholds
    from aegis_research.metrics import calculate_metric_summary
    from aegis_research.outcomes import get_default_store

    records = list(get_default_store().iter_candidates(limit=limit))
    return {
        "metrics": calculate_metric_summary(records).to_dict(),
        "thresholds": suggest_thresholds(records).to_dict(),
        "safe_mode": "SHADOW_ONLY_NO_CONFIG_WRITE",
    }


@router.post("/start")
async def agent_start() -> Dict[str, Any]:
    """Otonom karar döngüsünü başlat (güvenli — moda göre yönlendirir)."""
    return await get_agent().start()


@router.post("/stop")
async def agent_stop() -> Dict[str, Any]:
    """Otonom döngüyü durdur."""
    return await get_agent().stop()


@router.post("/run_once")
async def agent_run_once() -> Dict[str, Any]:
    """Tek döngü çalıştır — agent kapalıyken test için."""
    return await get_agent().run_once()


@router.post("/config")
async def agent_config(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Çalışma zamanı config güncelle. Değişebilen alanlar:
      interval_sec, watch_symbols (liste veya virgüllü), timeframe, horizon,
      min_confidence, min_score_edge, max_signals_per_day

    EXECUTION_MODE buradan DEĞİŞTİRİLEMEZ (env ile sabit — güvenlik).
    """
    agent = get_agent()
    cfg = agent.config
    changed = {}

    if "interval_sec" in body:
        cfg.interval_sec = max(30, int(body["interval_sec"]))
        changed["interval_sec"] = cfg.interval_sec
    if "watch_symbols" in body:
        syms = body["watch_symbols"]
        if isinstance(syms, str):
            syms = [s.strip() for s in syms.split(",")]
        cfg.watch_symbols = [s for s in syms if s]
        changed["watch_symbols"] = cfg.watch_symbols
    if "timeframe" in body:
        cfg.timeframe = str(body["timeframe"])
        changed["timeframe"] = cfg.timeframe
    if "horizon" in body:
        cfg.horizon = str(body["horizon"])
        changed["horizon"] = cfg.horizon
    if "min_confidence" in body:
        cfg.min_confidence = max(0.0, min(1.0, float(body["min_confidence"])))
        changed["min_confidence"] = cfg.min_confidence
    if "min_score_edge" in body:
        cfg.min_score_edge = max(0.0, min(0.5, float(body["min_score_edge"])))
        changed["min_score_edge"] = cfg.min_score_edge
    if "max_signals_per_day" in body:
        cfg.max_signals_per_day = max(1, int(body["max_signals_per_day"]))
        changed["max_signals_per_day"] = cfg.max_signals_per_day

    logger.info("Agent config updated: %s", changed)
    return {"status": "updated", "changed": changed, "config": cfg.to_dict()}
