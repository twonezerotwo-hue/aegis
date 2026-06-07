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
import time
from fastapi import APIRouter, Body, Query
from typing import Any, Dict

from services.agent_audit import agent_audit_stats, get_recent_agent_audit, record_agent_audit
from services.agent_guard import guard_agent_response
from services.agent_loop import get_agent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("/status")
async def agent_status() -> Dict[str, Any]:
    """Agent yaşam döngüsü + config + heartbeat."""
    return guard_agent_response(get_agent().status(), source="agent.status")


@router.get("/journal")
async def agent_journal(limit: int = Query(50, ge=1, le=250)) -> Dict[str, Any]:
    """Son kararlar (en yeni önce)."""
    agent = get_agent()
    return guard_agent_response({
        "decisions": agent.recent_journal(limit=limit),
        "total_in_memory": len(agent.journal),
    }, source="agent.journal")


@router.get("/audit/recent")
async def agent_audit_recent(
    limit: int = Query(50, ge=1, le=500),
    endpoint: str | None = Query(None),
) -> Dict[str, Any]:
    """Recent agent audit entries."""
    items = get_recent_agent_audit(limit=limit, endpoint=endpoint)
    return guard_agent_response({
        "status": "ok",
        "count": len(items),
        "items": items,
    }, source="agent.audit.recent")


@router.get("/audit/stats")
async def agent_audit_stats_route() -> Dict[str, Any]:
    """Agent audit ring-buffer stats."""
    return guard_agent_response({"status": "ok", **agent_audit_stats()}, source="agent.audit.stats")


@router.get("/research/summary")
async def agent_research_summary(limit: int = Query(500, ge=1, le=5000)) -> Dict[str, Any]:
    """Research-only candidate summary. Does not change runtime config."""
    from aegis_research.data_adapters import adapter_inventory
    from aegis_research.metrics import optional_dependency_status
    from aegis_research.outcomes import get_default_store

    return guard_agent_response({
        "summary": get_default_store().summarize(limit=limit),
        "optional_metrics": optional_dependency_status(),
        "data_adapters": adapter_inventory(),
        "safe_mode": "RESEARCH_ONLY_NO_EXECUTION",
    }, source="agent.research.summary")


@router.get("/research/suggestions")
async def agent_research_suggestions(limit: int = Query(500, ge=1, le=5000)) -> Dict[str, Any]:
    """Shadow-only threshold suggestions. Owner approval is required separately."""
    from aegis_research.calibration import suggest_thresholds
    from aegis_research.metrics import calculate_metric_summary
    from aegis_research.outcomes import get_default_store

    records = list(get_default_store().iter_candidates(limit=limit))
    return guard_agent_response({
        "metrics": calculate_metric_summary(records).to_dict(),
        "thresholds": suggest_thresholds(records).to_dict(),
        "safe_mode": "SHADOW_ONLY_NO_CONFIG_WRITE",
    }, source="agent.research.suggestions")


@router.post("/start")
async def agent_start() -> Dict[str, Any]:
    """Otonom karar döngüsünü başlat (güvenli — moda göre yönlendirir)."""
    started_at = time.monotonic()
    response = guard_agent_response(await get_agent().start(), source="agent.start")
    record_agent_audit(
        endpoint="agent.start",
        output_payload=response,
        duration_ms=(time.monotonic() - started_at) * 1000.0,
    )
    return response


@router.post("/stop")
async def agent_stop() -> Dict[str, Any]:
    """Otonom döngüyü durdur."""
    started_at = time.monotonic()
    response = guard_agent_response(await get_agent().stop(), source="agent.stop")
    record_agent_audit(
        endpoint="agent.stop",
        output_payload=response,
        duration_ms=(time.monotonic() - started_at) * 1000.0,
    )
    return response


@router.post("/run_once")
async def agent_run_once() -> Dict[str, Any]:
    """Tek döngü çalıştır — agent kapalıyken test için."""
    started_at = time.monotonic()
    response = guard_agent_response(await get_agent().run_once(), source="agent.run_once")
    record_agent_audit(
        endpoint="agent.run_once",
        output_payload=response,
        duration_ms=(time.monotonic() - started_at) * 1000.0,
        extra={"new_decisions": len(response.get("new_decisions", []))},
    )
    return response


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
    if "candidate_timeframes" in body:
        from services.agent_loop import _normalize_agent_timeframes

        cfg.candidate_timeframes = _normalize_agent_timeframes(
            body["candidate_timeframes"],
            fallback=[cfg.timeframe],
        )
        changed["candidate_timeframes"] = cfg.candidate_timeframes
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
    response = guard_agent_response(
        {"status": "updated", "changed": changed, "config": cfg.to_dict()},
        source="agent.config",
    )
    record_agent_audit(
        endpoint="agent.config",
        input_payload=body,
        output_payload=response,
        extra={"changed": sorted(changed.keys())},
    )
    return response
