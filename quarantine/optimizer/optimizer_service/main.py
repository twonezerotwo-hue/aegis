"""
AEGIS Optimizer Service – FastAPI application
Endpoints: /optimizer/run, /optimizer/status/{id}, /optimizer/results/{id},
           /optimizer/apply/{id}, /backtest/analyze
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import yaml
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from prometheus_client import REGISTRY, generate_latest
from pydantic import BaseModel, Field
from starlette.responses import Response

from src.backtest_engine import BacktestEngine
from src.optimizer_engine import OptimizerEngine, study_store

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(title="AEGIS Optimizer Service", version="1.0.0", docs_url="/docs")

backtest_engine = BacktestEngine()
optimizer_engine = OptimizerEngine(backtest_engine)

CONSENSUS_CONFIG_PATH = os.getenv(
    "CONSENSUS_CONFIG_PATH",
    "/app/consensus_engine/config/consensus_weights.yaml",
)


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

def _current_weights() -> Dict[str, float]:
    """Load current consensus module weights from YAML."""
    try:
        with open(CONSENSUS_CONFIG_PATH) as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get("weights", {
            "touche": 0.35, "fundamental": 0.30,
            "news": 0.20, "sentinel": 0.10, "quantum": 0.05,
        })
    except Exception:
        return {"touche": 0.35, "fundamental": 0.30, "news": 0.20, "sentinel": 0.10, "quantum": 0.05}


def _study_id_from_now() -> str:
    now = datetime.now(timezone.utc)
    week = now.isocalendar()[1]
    return f"opt_{now.year}w{week:02d}"


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class OptimizeRequest(BaseModel):
    study_id: Optional[str] = None
    timeframe_days: int = Field(default=90, ge=30, le=365)
    symbols: List[str] = Field(default=["BTCUSDT"])
    objective: str = Field(default="sharpe", pattern="^(sharpe|win_rate|sortino)$")
    n_trials: int = Field(default=100, ge=10, le=500)


class BacktestRequest(BaseModel):
    start_date: Optional[str] = None   # ISO 8601
    end_date: Optional[str] = None
    symbols: List[str] = Field(default=["BTCUSDT"])
    params: Optional[Dict[str, Any]] = None


class ApplyRequest(BaseModel):
    confirm: bool = False
    rollback_after_hours: int = Field(default=24, ge=1, le=168)


# ---------------------------------------------------------------------------
# Startup / Shutdown
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup() -> None:
    logger.info("Optimizer service started")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> Dict:
    studies = await study_store.list_ids()
    return {
        "status": "ok",
        "service": "optimizer",
        "version": "1.0.0",
        "active_studies": len(studies),
        "consensus_config": CONSENSUS_CONFIG_PATH,
    }


@app.get("/metrics")
async def prometheus_metrics() -> Response:
    return Response(generate_latest(REGISTRY), media_type="text/plain; charset=utf-8")


# ---------------------------------------------------------------------------
# POST /optimizer/run  – launch optimization in background
# ---------------------------------------------------------------------------

@app.post("/optimizer/run")
async def run_optimizer(
    req: OptimizeRequest,
    background_tasks: BackgroundTasks,
) -> Dict:
    study_id = req.study_id or _study_id_from_now()

    # Prevent duplicate running studies
    existing = await study_store.get(study_id)
    if existing and existing.get("status") in ("running", "completed"):
        return {
            "study_id": study_id,
            "status": existing.get("status"),
            "message": "Study already exists. Use a different study_id to start fresh.",
        }

    optimizer_engine.N_TRIALS = req.n_trials
    current_weights = _current_weights()

    await study_store.create(
        study_id,
        {
            "study_id": study_id,
            "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "timeframe_days": req.timeframe_days,
            "symbols": req.symbols,
            "objective": req.objective,
            "n_trials": req.n_trials,
            "progress": 0.0,
            "trials_completed": 0,
            "best_score": None,
            "best_params": None,
        },
    )

    background_tasks.add_task(
        optimizer_engine.run_study,
        study_id=study_id,
        timeframe_days=req.timeframe_days,
        symbols=req.symbols,
        objective_metric=req.objective,
        current_weights=current_weights,
    )

    estimated_seconds = req.n_trials * 1.5
    return {
        "study_id": study_id,
        "status": "queued",
        "n_trials": req.n_trials,
        "objective": req.objective,
        "estimated_completion": (
            datetime.now(timezone.utc) + timedelta(seconds=estimated_seconds)
        ).isoformat(),
    }


# ---------------------------------------------------------------------------
# GET /optimizer/status/{study_id}
# ---------------------------------------------------------------------------

@app.get("/optimizer/status/{study_id}")
async def optimizer_status(study_id: str) -> Dict:
    study = await study_store.get(study_id)
    if not study:
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")

    return {
        "study_id": study_id,
        "status": study.get("status"),
        "progress": study.get("progress", 0.0),
        "trials_completed": study.get("trials_completed", 0),
        "n_trials": study.get("n_trials"),
        "best_score": study.get("best_score"),
        "best_params": study.get("best_params"),
    }


# ---------------------------------------------------------------------------
# GET /optimizer/results/{study_id}
# ---------------------------------------------------------------------------

@app.get("/optimizer/results/{study_id}")
async def optimizer_results(study_id: str) -> Dict:
    study = await study_store.get(study_id)
    if not study:
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")
    if study.get("status") != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Study '{study_id}' is not completed (status={study.get('status')})",
        )

    best_params = study.get("best_params", {})
    wf = study.get("walk_forward", {})
    test_m = wf.get("test", {})

    # Build recommendations
    meets_criteria = (
        test_m.get("win_rate", 0) >= 0.60
        and test_m.get("max_drawdown", -99) >= -0.20
        and test_m.get("profit_factor", 0) >= 1.8
        and test_m.get("sharpe_ratio", 0) >= study.get("best_score", 0)
    )

    return {
        "study_id": study_id,
        "status": "completed",
        "completed_at": study.get("completed_at"),
        "best_score": study.get("best_score"),
        "recommended_weights": {
            k.replace("_weight", ""): v
            for k, v in best_params.items()
            if k.endswith("_weight")
        },
        "recommended_thresholds": {
            "buy_threshold": best_params.get("buy_threshold"),
            "sell_threshold": best_params.get("sell_threshold"),
        },
        "recommended_position": {
            "base_position_size": best_params.get("base_position_size"),
            "kelly_cap": best_params.get("kelly_cap"),
            "vol_adjust_factor": best_params.get("vol_adjust_factor"),
        },
        "walk_forward": wf,
        "meets_success_criteria": meets_criteria,
        "overfitting_warning": wf.get("overfitting_warning", False),
        "overfitting_detail": wf.get("overfitting_detail", ""),
    }


# ---------------------------------------------------------------------------
# POST /optimizer/apply/{study_id}
# ---------------------------------------------------------------------------

@app.post("/optimizer/apply/{study_id}")
async def optimizer_apply(study_id: str, req: ApplyRequest) -> Dict:
    if not req.confirm:
        raise HTTPException(
            status_code=400,
            detail="Set confirm=true to apply. This will overwrite consensus_weights.yaml.",
        )

    result = await optimizer_engine.apply_config(
        study_id=study_id,
        confirm=req.confirm,
        rollback_after_hours=req.rollback_after_hours,
        consensus_config_path=CONSENSUS_CONFIG_PATH,
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=422, detail=result.get("reason"))

    return result


# ---------------------------------------------------------------------------
# POST /optimizer/rollback
# ---------------------------------------------------------------------------

@app.post("/optimizer/rollback")
async def optimizer_rollback(
    config_version: str = Query(..., description="Filename in configs/archive/"),
) -> Dict:
    result = await optimizer_engine.rollback(
        config_version=config_version,
        consensus_config_path=CONSENSUS_CONFIG_PATH,
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result.get("reason"))
    return result


# ---------------------------------------------------------------------------
# GET /backtest/analyze
# ---------------------------------------------------------------------------

@app.get("/backtest/analyze")
async def backtest_analyze(
    start_date: Optional[str] = Query(
        default=None,
        description="ISO 8601 start. Defaults to 90 days ago.",
    ),
    end_date: Optional[str] = Query(
        default=None,
        description="ISO 8601 end. Defaults to now.",
    ),
    symbol: str = Query(default="BTCUSDT"),
) -> Dict:
    end = (
        datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        if end_date
        else datetime.now(timezone.utc)
    )
    start = (
        datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        if start_date
        else end - timedelta(days=90)
    )

    current_params = {
        "buy_threshold": 52.0,
        "sell_threshold": 48.0,
        "base_position_size": 0.01,
        "kelly_cap": 0.25,
        "vol_adjust_factor": 1.0,
        **{f"{k}_weight": v for k, v in _current_weights().items()},
    }

    wf = await backtest_engine.run(current_params, start, end)

    def _m(m: Any) -> Dict:
        return {
            "win_rate": m.win_rate,
            "sharpe_ratio": m.sharpe_ratio,
            "sortino_ratio": m.sortino_ratio,
            "max_drawdown": m.max_drawdown,
            "profit_factor": m.profit_factor,
            "expectancy": m.expectancy,
            "calmar_ratio": m.calmar_ratio,
            "var_95": m.var_95,
            "total_trades": m.total_trades,
            "net_return": m.net_return,
            "trade_frequency_daily": m.trade_frequency_daily,
            "max_consecutive_losses": m.max_consecutive_losses,
            "equity_curve": m.equity_curve[:100],  # for bandwidth
        }

    return {
        "symbol": symbol,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "walk_forward": {
            "train": _m(wf.train_metrics),
            "validation": _m(wf.validation_metrics),
            "test": _m(wf.test_metrics),
        },
        "overfitting_warning": wf.overfitting_warning,
        "overfitting_detail": wf.overfitting_detail,
        "current_params": current_params,
    }


# ---------------------------------------------------------------------------
# Dev entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8008, reload=True)
