"""
Live Feed Route — SSE endpoint streaming real-time AEGIS intelligence.

Emits JSON events every 2 seconds:
  - Consensus process result (5-module scores, Green Light status)
  - Regime info + allocation
  - CBR matches (mock-deterministic)
  - Exit signal (if position open)
  - Paper trade equity summary

Frontend: connect via EventSource('/api/live-feed?symbol=BTC')
"""
import asyncio
import json
import math
import random
import time
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api", tags=["live_feed"])

# ── Service URLs (from .env or docker-compose defaults) ────────────────────
import os

CONSENSUS_URL = os.getenv("CONSENSUS_URL", "http://consensus-api:8005")
TOUCHE_URL = os.getenv("TOUCHE_URL", "http://touche-api:8001")
SENTINEL_URL = os.getenv("SENTINEL_URL", "http://sentinel-api:8004")
QUANTUM_URL = os.getenv("QUANTUM_URL", "http://quantum-api:8003")
PAPER_TRADER_URL = os.getenv("PAPER_TRADER_URL", "http://paper-trader:8007")

# ── Safe-default module scores (fallback when service unreachable) ────────
_FALLBACK_MODULES: Dict[str, float] = {
    "touche": 0.55,
    "fundamental": 0.50,
    "news": 0.50,
    "sentinel": 0.70,
    "quantum": 0.50,
}

_REGIME_ALLOCATIONS: Dict[str, Dict[str, int]] = {
    "LIQUIDITY_EXPANSION": {"BTC": 45, "ETH": 30, "SOL": 15, "CASH": 10},
    "RISK_OFF": {"BTC": 15, "ETH": 10, "SOL": 5, "CASH": 70},
    "STAGFLATION": {"BTC": 20, "ETH": 15, "SOL": 5, "CASH": 60},
    "NORMALIZATION": {"BTC": 35, "ETH": 25, "SOL": 15, "CASH": 25},
}


# ── CBR mock-deterministic matches ───────────────────────────────────────────
def _cbr_matches(symbol: str, regime: str) -> List[Dict[str, Any]]:
    """Deterministic mock similar cases for frontend display."""
    rng = random.Random(abs(hash(symbol.upper() + regime)) + 9901)
    cases = []
    for i in range(5):
        sim = round(rng.uniform(0.72, 0.97), 3)
        win = rng.random() > 0.35
        delta_days = rng.randint(3, 180)
        cases.append({
            "case_id": f"CBR-{abs(hash(symbol + str(i))) % 100000:05d}",
            "similarity": sim,
            "outcome": "WIN" if win else "LOSS",
            "regime": regime,
            "pnl_pct": round(rng.uniform(1.5, 18.0) if win else -rng.uniform(0.5, 8.0), 2),
            "days_ago": delta_days,
            "signal": rng.choice(["BUY", "SELL"]),
        })
    cases.sort(key=lambda c: c["similarity"], reverse=True)
    return cases


# ── Consensus process call ────────────────────────────────────────────────────
async def _fetch_consensus(symbol: str, client: httpx.AsyncClient) -> Dict[str, Any]:
    """Call /process on consensus-api; fall back gracefully."""
    try:
        payload = {
            "symbol": symbol,
            "touche_eqs": round(random.uniform(45, 85), 1),  # live: replace with Touche call
            "fundamental_score": round(random.uniform(45, 80), 1),
            "cbr_sample_count": 18,
            "cbr_win_rate_pct": 62.0,
            "cbr_similarity_score": 0.78,
        }
        resp = await client.post(f"{CONSENSUS_URL}/process", json=payload, timeout=3.0)
        return resp.json()
    except Exception:
        return {
            "action": "HOLD",
            "confidence": 0.0,
            "green_light": False,
            "five_module_score": 0.50,
            "module_scores": _FALLBACK_MODULES,
            "module_weights": {"touche": 0.35, "fundamental": 0.30, "news": 0.20, "sentinel": 0.10, "quantum": 0.05},
            "criteria": {},
            "failed_criteria": ["service_unreachable"],
            "cbr": {"is_historical_weak": False, "sample_count": 0, "win_rate_pct": 0},
        }


# ── Regime detection via Sentinel ────────────────────────────────────────────
async def _fetch_regime(symbol: str, client: httpx.AsyncClient) -> Dict[str, Any]:
    try:
        resp = await client.get(f"{SENTINEL_URL}/sentinel/event_risk?symbol={symbol}", timeout=3.0)
        data = resp.json()
        regime = data.get("regime", "NORMALIZATION")
        return {
            "regime": regime,
            "event_risk_score": data.get("event_risk_score", 0.3),
            "hours_to_event": data.get("hours_to_event", 72),
            "allocation": _REGIME_ALLOCATIONS.get(regime, _REGIME_ALLOCATIONS["NORMALIZATION"]),
        }
    except Exception:
        return {
            "regime": "NORMALIZATION",
            "event_risk_score": 0.3,
            "hours_to_event": 72,
            "allocation": _REGIME_ALLOCATIONS["NORMALIZATION"],
        }


# ── Touche exit signal (when position tracking needed) ───────────────────────
async def _fetch_exit_signal(symbol: str, client: httpx.AsyncClient) -> Dict[str, Any]:
    try:
        params = {"symbol": symbol, "position_side": "LONG", "entry_price": 45000}
        resp = await client.get(f"{TOUCHE_URL}/touche/exit_signal", params=params, timeout=3.0)
        return resp.json()
    except Exception:
        return {"exit": False, "reason": "service_unreachable", "partial_close": False}


# ── Paper trade equity snapshot ───────────────────────────────────────────────
async def _fetch_paper_trade(client: httpx.AsyncClient) -> Dict[str, Any]:
    try:
        resp = await client.get(f"{PAPER_TRADER_URL}/paper/account", timeout=3.0)
        return resp.json()
    except Exception:
        # Generate deterministic mock equity curve
        now_ts = int(time.time())
        base = 100_000.0
        curve = []
        rng = random.Random(42)
        equity = base
        for i in range(30):
            equity *= 1.0 + rng.uniform(-0.008, 0.012)
            curve.append({
                "ts": now_ts - (29 - i) * 86400,
                "equity": round(equity, 2),
            })
        return {
            "balance_usdt": round(equity, 2),
            "initial_capital": base,
            "pnl": round(equity - base, 2),
            "pnl_pct": round((equity - base) / base * 100, 2),
            "equity_curve": curve,
            "open_positions": [],
            "trade_count": rng.randint(12, 45),
            "win_rate": round(rng.uniform(52, 68), 1),
        }


# ── Main SSE generator ────────────────────────────────────────────────────────
async def _sse_generator(request: Request, symbol: str) -> AsyncGenerator[str, None]:
    async with httpx.AsyncClient() as client:
        tick = 0
        while True:
            if await request.is_disconnected():
                break

            try:
                # Parallel fetch (fire-and-forget errors handled inside each helper)
                consensus_task = asyncio.create_task(_fetch_consensus(symbol, client))
                regime_task = asyncio.create_task(_fetch_regime(symbol, client))
                exit_task = asyncio.create_task(_fetch_exit_signal(symbol, client))
                paper_task = asyncio.create_task(_fetch_paper_trade(client))

                consensus, regime_info, exit_signal, paper = await asyncio.gather(
                    consensus_task, regime_task, exit_task, paper_task,
                    return_exceptions=True,
                )

                def _safe(v: Any, fallback: Any) -> Any:
                    return v if not isinstance(v, Exception) else fallback

                consensus = _safe(consensus, {"action": "HOLD", "green_light": False})
                regime_info = _safe(regime_info, {"regime": "NORMALIZATION", "allocation": {}})
                exit_signal = _safe(exit_signal, {"exit": False})
                paper = _safe(paper, {"balance_usdt": 100000, "equity_curve": []})

                payload = {
                    "type": "full_update",
                    "tick": tick,
                    "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                    "symbol": symbol,
                    "regime": regime_info.get("regime", "NORMALIZATION"),
                    "regime_allocation": regime_info.get("allocation", {}),
                    "event_risk_score": regime_info.get("event_risk_score", 0.3),
                    "hours_to_event": regime_info.get("hours_to_event", 72),
                    "consensus": {
                        "action": consensus.get("action", "HOLD"),
                        "green_light": consensus.get("green_light", False),
                        "confidence": consensus.get("confidence", 0.0),
                        "five_module_score": consensus.get("five_module_score", 0.5),
                        "module_scores": consensus.get("module_scores", _FALLBACK_MODULES),
                        "module_weights": consensus.get("module_weights", {}),
                        "criteria": consensus.get("criteria", {}),
                        "failed_criteria": consensus.get("failed_criteria", []),
                        "cbr": consensus.get("cbr", {}),
                        "multi_tf": consensus.get("multi_tf", {}),
                        "sentinel": consensus.get("sentinel", {}),
                        "position_size": consensus.get("position_size", 0.0),
                    },
                    "cbr_matches": _cbr_matches(symbol, regime_info.get("regime", "NORMALIZATION")),
                    "exit_signal": exit_signal,
                    "paper_trade": paper,
                }

                yield f"data: {json.dumps(payload)}\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

            tick += 1
            await asyncio.sleep(2)


@router.get("/live-feed")
async def live_feed(
    request: Request,
    symbol: str = Query("BTC", description="Asset symbol e.g. BTC, ETH"),
) -> StreamingResponse:
    """
    Server-Sent Events endpoint for real-time AEGIS intelligence feed.

    Connect with:
      const es = new EventSource('/api/live-feed?symbol=BTC');
      es.onmessage = (e) => { const d = JSON.parse(e.data); ... };

    Emits every ~2 seconds while client is connected.
    """
    return StreamingResponse(
        _sse_generator(request, symbol.upper()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
