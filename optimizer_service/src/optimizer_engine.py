"""
Optimizer Service - Optuna Optimization Engine
TPE sampler + Median pruner, walk-forward validation, safety constraints.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import optuna
import yaml
from prometheus_client import Counter, Gauge

from src.backtest_engine import BacktestEngine, WalkForwardResult

logger = logging.getLogger(__name__)
optuna.logging.set_verbosity(optuna.logging.WARNING)

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------
_OPT_TRIALS = Counter(
    "optimizer_trials_total",
    "Completed Optuna trials",
    ["study_id"],
)
_OPT_BEST_SCORE = Gauge(
    "optimizer_best_score",
    "Best Optuna score",
    ["metric"],
)
_LIVE_WINRATE = Gauge(
    "optimizer_current_winrate",
    "Live win-rate estimate",
    ["window"],
)
_BT_SHARPE = Gauge(
    "backtest_sharpe_ratio",
    "Backtest Sharpe per symbol",
    ["symbol"],
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_MAX_WEIGHT_DELTA = 0.20   # no single weight may shift more than 20pp
_SENTINEL_RISKOFF_MIN = 0.15   # conservative mode floor

CONFIGS_DIR = Path(os.getenv("OPTIMIZER_CONFIGS_DIR", "/app/optimizer_service/configs"))
TRIALS_DIR = Path(os.getenv("OPTIMIZER_TRIALS_DIR", "/app/optimizer_service/trials"))


# ---------------------------------------------------------------------------
# Study store (in-memory, no Optuna Storage dependency for simplicity)
# ---------------------------------------------------------------------------

class StudyStore:
    """Thread-safe in-memory store for active/completed studies."""

    def __init__(self) -> None:
        self._studies: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def create(self, study_id: str, meta: Dict) -> None:
        async with self._lock:
            self._studies[study_id] = meta

    async def get(self, study_id: str) -> Optional[Dict]:
        return self._studies.get(study_id)

    async def update(self, study_id: str, **kwargs: Any) -> None:
        async with self._lock:
            if study_id in self._studies:
                self._studies[study_id].update(kwargs)

    async def list_ids(self) -> List[str]:
        return list(self._studies.keys())


# Module-level singleton
study_store = StudyStore()


# ---------------------------------------------------------------------------
# Parameter constraints
# ---------------------------------------------------------------------------

def _normalize_weights(trial_vals: Dict[str, float]) -> Tuple[float, float, float, float, float]:
    """Normalize 5 module weights to sum to 1.0."""
    keys = ["touche_weight", "fundamental_weight", "news_weight", "sentinel_weight", "quantum_weight"]
    raw = [trial_vals[k] for k in keys]
    total = sum(raw)
    if total <= 0:
        total = 1.0
    return tuple(w / total for w in raw)  # type: ignore[return-value]


def _enforce_safety(params: Dict[str, Any], current_weights: Dict[str, float]) -> Dict[str, Any]:
    """
    Apply safety constraints:
    - No weight may change by more than _MAX_WEIGHT_DELTA (20pp)
    - sentiment_weight >= _SENTINEL_RISKOFF_MIN in conservative mode
    """
    safe = dict(params)
    weight_map = {
        "touche": "touche_weight",
        "fundamental": "fundamental_weight",
        "news": "news_weight",
        "sentinel": "sentinel_weight",
        "quantum": "quantum_weight",
    }
    for module, key in weight_map.items():
        old = current_weights.get(module, 0.0)
        new = safe.get(key, old)
        # Clamp change
        safe[key] = float(np.clip(new, old - _MAX_WEIGHT_DELTA, old + _MAX_WEIGHT_DELTA))

    # Conservative mode: sentinel floor
    if safe.get("sentinel_weight", 0) < _SENTINEL_RISKOFF_MIN:
        safe["sentinel_weight"] = _SENTINEL_RISKOFF_MIN
        # Re-normalize
        total = sum(safe[k] for k in weight_map.values())
        for k in weight_map.values():
            safe[k] = safe[k] / total

    return safe


# ---------------------------------------------------------------------------
# Optuna objective
# ---------------------------------------------------------------------------

def _build_objective(
    engine: BacktestEngine,
    start: datetime,
    end: datetime,
    objective_metric: str,
    current_weights: Dict[str, float],
    study_id: str,
    loop: asyncio.AbstractEventLoop,
):
    """Return a callable Optuna objective function."""

    def objective(trial: optuna.Trial) -> float:
        # --- Sample parameter space ---
        t_w = trial.suggest_float("touche_weight", 0.20, 0.50)
        f_w = trial.suggest_float("fundamental_weight", 0.15, 0.40)
        n_w = trial.suggest_float("news_weight", 0.10, 0.30)
        s_w = trial.suggest_float("sentinel_weight", 0.05, 0.25)
        q_w = trial.suggest_float("quantum_weight", 0.00, 0.15)

        raw_vals = {
            "touche_weight": t_w,
            "fundamental_weight": f_w,
            "news_weight": n_w,
            "sentinel_weight": s_w,
            "quantum_weight": q_w,
        }
        t_w, f_w, n_w, s_w, q_w = _normalize_weights(raw_vals)

        params = {
            "touche_weight": t_w,
            "fundamental_weight": f_w,
            "news_weight": n_w,
            "sentinel_weight": s_w,
            "quantum_weight": q_w,
            "buy_threshold": trial.suggest_float("buy_threshold", 48.0, 58.0),
            "sell_threshold": trial.suggest_float("sell_threshold", 42.0, 52.0),
            "cbr_min_samples": trial.suggest_int("cbr_min_samples", 10, 25),
            "cbr_min_winrate": trial.suggest_float("cbr_min_winrate", 0.45, 0.65),
            "base_position_size": trial.suggest_float("base_position_size", 0.005, 0.03),
            "kelly_cap": trial.suggest_float("kelly_cap", 0.15, 0.50),
            "vol_adjust_factor": trial.suggest_float("vol_adjust_factor", 0.5, 1.5),
        }

        # Safety: buy_threshold must be > sell_threshold
        if params["buy_threshold"] <= params["sell_threshold"]:
            raise optuna.exceptions.TrialPruned()

        # Run backtest in event loop
        metrics = asyncio.run_coroutine_threadsafe(
            engine.run_simple(params, start, end), loop
        ).result(timeout=30)

        # --- Constraint checks (prune bad trials early) ---
        if metrics.max_drawdown < -0.35:
            raise optuna.exceptions.TrialPruned()
        if metrics.win_rate < 0.40:
            raise optuna.exceptions.TrialPruned()

        # --- Report intermediate step for MedianPruner ---
        trial.report(metrics.sharpe_ratio, step=metrics.total_trades)
        if trial.should_prune():
            raise optuna.exceptions.TrialPruned()

        # --- Prometheus ---
        _OPT_TRIALS.labels(study_id=study_id).inc()
        if metrics.sharpe_ratio > _OPT_BEST_SCORE.labels(metric="sharpe")._value.get():
            _OPT_BEST_SCORE.labels(metric="sharpe").set(metrics.sharpe_ratio)

        # --- Log trial to disk ---
        _log_trial(study_id, trial.number, params, metrics)

        # --- Select objective ---
        if objective_metric == "sharpe":
            return metrics.sharpe_ratio
        if objective_metric == "win_rate":
            return metrics.win_rate
        if objective_metric == "sortino":
            return metrics.sortino_ratio
        return metrics.sharpe_ratio  # default

    return objective


def _log_trial(study_id: str, trial_no: int, params: Dict, metrics: Any) -> None:
    """Persist trial JSON to disk."""
    TRIALS_DIR.mkdir(parents=True, exist_ok=True)
    path = TRIALS_DIR / f"{study_id}_trial_{trial_no:04d}.json"
    try:
        with path.open("w") as f:
            json.dump(
                {
                    "study_id": study_id,
                    "trial": trial_no,
                    "params": params,
                    "metrics": {
                        "win_rate": metrics.win_rate,
                        "sharpe": metrics.sharpe_ratio,
                        "sortino": metrics.sortino_ratio,
                        "max_drawdown": metrics.max_drawdown,
                        "profit_factor": metrics.profit_factor,
                    },
                    "ts": datetime.now(timezone.utc).isoformat(),
                },
                f,
                indent=2,
            )
    except Exception as exc:
        logger.debug("Trial log write failed: %s", exc)


# ---------------------------------------------------------------------------
# Main Optimizer
# ---------------------------------------------------------------------------

class OptimizerEngine:
    """
    Manages Optuna study lifecycle: creation, async execution, result apply.
    """

    N_TRIALS: int = 100

    def __init__(self, backtest_engine: BacktestEngine) -> None:
        self._bt = backtest_engine

    async def run_study(
        self,
        study_id: str,
        timeframe_days: int,
        symbols: List[str],
        objective_metric: str,
        current_weights: Dict[str, float],
    ) -> None:
        """
        Run full Optuna optimization in a thread pool (non-blocking).
        Updates study_store throughout.
        """
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=timeframe_days)

        await study_store.update(
            study_id,
            status="running",
            started_at=datetime.now(timezone.utc).isoformat(),
            progress=0.0,
            trials_completed=0,
            best_score=None,
            best_params=None,
        )

        loop = asyncio.get_event_loop()

        def _run() -> None:
            sampler = optuna.samplers.TPESampler(
                multivariate=True, constant_liar=True, seed=2026
            )
            pruner = optuna.pruners.MedianPruner(n_startup_trials=10, n_warmup_steps=5)

            study = optuna.create_study(
                direction="maximize",
                sampler=sampler,
                pruner=pruner,
                study_name=study_id,
            )

            objective_fn = _build_objective(
                self._bt, start, end, objective_metric, current_weights, study_id, loop
            )

            def _callback(study: optuna.Study, trial: optuna.Trial) -> None:
                progress = (trial.number + 1) / self.N_TRIALS
                best = study.best_value if study.best_trials else None
                best_p = study.best_params if study.best_trials else None
                asyncio.run_coroutine_threadsafe(
                    study_store.update(
                        study_id,
                        progress=round(progress, 3),
                        trials_completed=trial.number + 1,
                        best_score=round(best, 4) if best is not None else None,
                        best_params=best_p,
                    ),
                    loop,
                ).result()

            study.optimize(
                objective_fn,
                n_trials=self.N_TRIALS,
                n_jobs=1,        # 1 in async context; parallelism is at service level
                callbacks=[_callback],
                show_progress_bar=False,
            )

            # Walk-forward validation with best params
            best_params = study.best_params if study.best_trials else {}
            # Normalize weights
            raw = {k: best_params.get(k, 0.1) for k in [
                "touche_weight", "fundamental_weight", "news_weight",
                "sentinel_weight", "quantum_weight",
            ]}
            t_w, f_w, n_w, s_w, q_w = _normalize_weights(raw)
            best_params.update({
                "touche_weight": t_w, "fundamental_weight": f_w,
                "news_weight": n_w, "sentinel_weight": s_w, "quantum_weight": q_w,
            })
            best_params = _enforce_safety(best_params, current_weights)

            wf_result_future = asyncio.run_coroutine_threadsafe(
                self._bt.run(best_params, start, end), loop
            )
            wf_result = wf_result_future.result(timeout=60)

            _BT_SHARPE.labels(symbol="BTC").set(wf_result.test_metrics.sharpe_ratio)
            _LIVE_WINRATE.labels(window="7d").set(wf_result.test_metrics.win_rate)

            asyncio.run_coroutine_threadsafe(
                study_store.update(
                    study_id,
                    status="completed",
                    progress=1.0,
                    best_params=best_params,
                    best_score=round(wf_result.test_metrics.sharpe_ratio, 4),
                    walk_forward=_wf_to_dict(wf_result),
                    completed_at=datetime.now(timezone.utc).isoformat(),
                ),
                loop,
            ).result()

            # Persist recommended config
            _save_config(study_id, best_params, wf_result, current_weights)

        try:
            await asyncio.get_event_loop().run_in_executor(None, _run)
        except Exception as exc:
            logger.error("Optimizer study %s failed: %s", study_id, exc)
            await study_store.update(study_id, status="failed", error=str(exc))

    async def apply_config(
        self,
        study_id: str,
        confirm: bool,
        rollback_after_hours: int,
        consensus_config_path: str,
    ) -> Dict[str, Any]:
        """
        Apply best params from study to consensus_weights.yaml.
        Backs up current config first.
        """
        if not confirm:
            return {"status": "not_applied", "reason": "confirm=false"}

        study = await study_store.get(study_id)
        if not study or study.get("status") != "completed":
            return {"status": "error", "reason": "study not completed or not found"}

        best_params = study.get("best_params", {})
        if not best_params:
            return {"status": "error", "reason": "no best_params in study"}

        # Backup current config
        config_path = Path(consensus_config_path)
        backup_name = f"config_{study_id}_pre_apply.yaml"
        backup_path = CONFIGS_DIR / "archive" / backup_name
        CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
        (CONFIGS_DIR / "archive").mkdir(parents=True, exist_ok=True)

        if config_path.exists():
            with config_path.open() as f:
                current_cfg = yaml.safe_load(f) or {}
            with backup_path.open("w") as f:
                yaml.dump(current_cfg, f)
        else:
            backup_name = "none"

        # Write new config
        new_cfg = {
            "current_phase": "optuna_optimized",
            "study_id": study_id,
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "rollback_after_hours": rollback_after_hours,
            "weights": {
                "touche": best_params.get("touche_weight", 0.35),
                "fundamental": best_params.get("fundamental_weight", 0.30),
                "news": best_params.get("news_weight", 0.20),
                "sentinel": best_params.get("sentinel_weight", 0.10),
                "quantum": best_params.get("quantum_weight", 0.05),
            },
            "green_light_thresholds": {
                "buy_gt": best_params.get("buy_threshold", 52.0),
                "sell_lt": best_params.get("sell_threshold", 48.0),
            },
            "position": {
                "base_size": best_params.get("base_position_size", 0.01),
                "kelly_cap": best_params.get("kelly_cap", 0.25),
                "vol_adjust_factor": best_params.get("vol_adjust_factor", 1.0),
            },
        }

        with config_path.open("w") as f:
            yaml.dump(new_cfg, f, default_flow_style=False)

        # Append to changelog
        _append_changelog(study_id, best_params, study)

        return {
            "status": "applied",
            "previous_config_backup": backup_name,
            "new_config": new_cfg,
            "rollback_after_hours": rollback_after_hours,
        }

    async def rollback(self, config_version: str, consensus_config_path: str) -> Dict[str, Any]:
        """Restore a backed-up config version."""
        backup_path = CONFIGS_DIR / "archive" / config_version
        if not backup_path.exists():
            return {"status": "error", "reason": f"Backup {config_version} not found"}

        config_path = Path(consensus_config_path)
        # Save current as emergency backup
        if config_path.exists():
            with config_path.open() as f:
                current = yaml.safe_load(f)
            emerg = CONFIGS_DIR / "archive" / f"emergency_backup_{int(time.time())}.yaml"
            with emerg.open("w") as f:
                yaml.dump(current, f)

        with backup_path.open() as f:
            restored = yaml.safe_load(f)
        with config_path.open("w") as f:
            yaml.dump(restored, f)

        return {"status": "rolled_back", "restored_from": config_version}


# ---------------------------------------------------------------------------
# Config persistence helpers
# ---------------------------------------------------------------------------

def _wf_to_dict(wf: WalkForwardResult) -> Dict:
    def _m(m: Any) -> Dict:
        return {
            "win_rate": m.win_rate,
            "sharpe_ratio": m.sharpe_ratio,
            "sortino_ratio": m.sortino_ratio,
            "max_drawdown": m.max_drawdown,
            "profit_factor": m.profit_factor,
            "total_trades": m.total_trades,
        }
    return {
        "train": _m(wf.train_metrics),
        "validation": _m(wf.validation_metrics),
        "test": _m(wf.test_metrics),
        "overfitting_warning": wf.overfitting_warning,
        "overfitting_detail": wf.overfitting_detail,
    }


def _save_config(
    study_id: str,
    params: Dict[str, Any],
    wf: WalkForwardResult,
    prev_weights: Dict[str, float],
) -> None:
    CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    path = CONFIGS_DIR / f"{study_id}_recommended.yaml"
    doc = {
        "study_id": study_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "params": params,
        "walk_forward": _wf_to_dict(wf),
        "weight_deltas": {
            k: round(params.get(f"{k}_weight", 0) - prev_weights.get(k, 0), 4)
            for k in ["touche", "fundamental", "news", "sentinel", "quantum"]
        },
    }
    with path.open("w") as f:
        yaml.dump(doc, f, default_flow_style=False)
    logger.info("Saved recommended config: %s", path)


def _append_changelog(study_id: str, params: Dict, study: Dict) -> None:
    CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    path = CONFIGS_DIR / "changelog.md"
    try:
        with path.open("a") as f:
            f.write(f"\n## {study_id} – {datetime.now(timezone.utc).isoformat()}\n")
            f.write(f"- Sharpe: {study.get('best_score')}\n")
            f.write(f"- walk_forward: {json.dumps(study.get('walk_forward', {}), indent=2)}\n")
            for k, v in params.items():
                f.write(f"- {k}: {v}\n")
    except Exception as exc:
        logger.debug("Changelog write failed: %s", exc)
