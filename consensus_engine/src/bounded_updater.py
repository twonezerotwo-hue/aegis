"""
AEGIS v7.0 — Bounded Updater

Applies post-trade module weight adjustments with safety guards:

  +WEIGHT_STEP_WIN  per winning module
  -WEIGHT_STEP_LOSE per losing module
  Clamp   : each weight stays in [MIN_WEIGHT, MAX_WEIGHT]
  Normalize: Σ always = 1.0 after each update

Guards:
  Drift Guard  — if weekly cumulative |Δ| ≥ MAX_WEEKLY_DRIFT → freeze
  DD Guard     — if current_dd_pct < DD_ROLLBACK_THRESHOLD   → rollback

Safety rules:
  - All YAML I/O is atomic (backup before any write)
  - Never raises to caller
  - Drift log is persisted to drift_log.yaml alongside consensus_weights.yaml
"""
from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timezone
from typing import Dict, List

import yaml

logger = logging.getLogger(__name__)

# ── Tunable constants ────────────────────────────────────────────────────────
WEIGHT_STEP_WIN: float = 0.01      # +1 % for each winning module
WEIGHT_STEP_LOSE: float = 0.005    # −0.5 % for each losing module
MIN_WEIGHT: float = 0.03           # floor: 3 %
MAX_WEIGHT: float = 0.50           # ceiling: 50 %
MAX_WEEKLY_DRIFT: float = 0.15     # freeze guard: 15 % total weekly movement
DD_ROLLBACK_THRESHOLD: float = -0.15  # −15 % drawdown → rollback

MODULES = ("touche", "fundamental", "news", "sentinel", "quantum")

# ── File paths (resolved relative to this file) ──────────────────────────────
_HERE = os.path.dirname(__file__)
_CONFIG_PATH = os.path.join(_HERE, "../config/consensus_weights.yaml")
_BACKUP_PATH = os.path.join(_HERE, "../config/consensus_weights_backup.yaml")
_DRIFT_LOG_PATH = os.path.join(_HERE, "../config/drift_log.yaml")


# ── Internal YAML helpers ────────────────────────────────────────────────────

def _load_weights() -> Dict[str, float]:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    modules = raw.get("modules", {})
    return {
        "touche":       float(modules.get("touche_weight",       0.35)),
        "fundamental":  float(modules.get("fundamental_weight",  0.30)),
        "news":         float(modules.get("news_weight",         0.20)),
        "sentinel":     float(modules.get("sentinel_weight",     0.10)),
        "quantum":      float(modules.get("quantum_weight",      0.05)),
    }


def _save_weights(weights: Dict[str, float]) -> None:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if "modules" not in raw:
        raw["modules"] = {}
    raw["modules"]["touche_weight"]       = round(weights["touche"],       6)
    raw["modules"]["fundamental_weight"]  = round(weights["fundamental"],  6)
    raw["modules"]["news_weight"]         = round(weights["news"],         6)
    raw["modules"]["sentinel_weight"]     = round(weights["sentinel"],     6)
    raw["modules"]["quantum_weight"]      = round(weights["quantum"],      6)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as fh:
        yaml.dump(raw, fh, allow_unicode=True, default_flow_style=False)


def _backup_now() -> None:
    shutil.copy2(_CONFIG_PATH, _BACKUP_PATH)
    logger.info("[BoundedUpdater] Weights backed up → %s", _BACKUP_PATH)


def _ensure_backup_exists() -> None:
    """Write a first-time backup if none is present yet."""
    if not os.path.exists(_BACKUP_PATH):
        _backup_now()


def _load_drift_log() -> Dict:
    if not os.path.exists(_DRIFT_LOG_PATH):
        return _empty_drift_log()
    try:
        with open(_DRIFT_LOG_PATH, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
            if not isinstance(data, dict):
                return _empty_drift_log()
            return data
    except Exception:
        return _empty_drift_log()


def _empty_drift_log() -> Dict:
    return {
        "weekly_deltas": [],
        "week_start": datetime.now(timezone.utc).isoformat(),
    }


def _save_drift_log(log: Dict) -> None:
    try:
        with open(_DRIFT_LOG_PATH, "w", encoding="utf-8") as fh:
            yaml.dump(log, fh, allow_unicode=True, default_flow_style=False)
    except Exception as exc:
        logger.warning("[BoundedUpdater] Drift log save failed: %s", exc)


def _weekly_drift(log: Dict) -> float:
    return sum(abs(d) for d in log.get("weekly_deltas", []))


# ── Normalization helpers ─────────────────────────────────────────────────────

def _clamp(weights: Dict[str, float]) -> Dict[str, float]:
    return {k: max(MIN_WEIGHT, min(MAX_WEIGHT, v)) for k, v in weights.items()}


def _normalize(weights: Dict[str, float]) -> Dict[str, float]:
    total = sum(weights.values())
    if total <= 0.0:
        equal = round(1.0 / len(MODULES), 6)
        return {m: equal for m in MODULES}
    return {k: round(v / total, 6) for k, v in weights.items()}


# ── Public class ─────────────────────────────────────────────────────────────

class BoundedUpdater:
    """
    Thread-safety note: All file I/O on the YAML config is done inside this
    class. In a multi-worker deployment the caller should acquire a file lock
    before calling update(); for single-worker (Uvicorn default) this is safe.
    """

    def __init__(self) -> None:
        _ensure_backup_exists()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(
        self,
        winning_modules: List[str],
        losing_modules: List[str],
        current_dd_pct: float = 0.0,
    ) -> Dict:
        """
        Apply weight adjustments after trade attribution.

        Parameters
        ----------
        winning_modules : Modules that contributed positively to the trade.
        losing_modules  : Modules that contributed negatively.
        current_dd_pct  : Current drawdown from recent equity peak (e.g. -0.032).
                          Negative value means the portfolio is in drawdown.

        Returns
        -------
        dict with keys:
            status        : "updated" | "frozen" | "rollback" | "rollback_failed"
            weights       : active weight dict after operation
            drift_total   : cumulative weekly drift so far
            message       : human-readable description
        """
        try:
            return self._apply(winning_modules, losing_modules, current_dd_pct)
        except Exception as exc:
            logger.error("[BoundedUpdater] update() failed: %s", exc)
            try:
                current = _load_weights()
            except Exception:
                current = {m: round(1.0 / len(MODULES), 4) for m in MODULES}
            return {
                "status": "error",
                "weights": current,
                "drift_total": 0.0,
                "message": f"BoundedUpdater internal error: {exc}",
            }

    # ------------------------------------------------------------------
    # Internal logic
    # ------------------------------------------------------------------

    def _apply(
        self,
        winning_modules: List[str],
        losing_modules: List[str],
        current_dd_pct: float,
    ) -> Dict:

        # ── DD Guard ──────────────────────────────────────────────────
        if current_dd_pct < DD_ROLLBACK_THRESHOLD:
            return self._rollback(
                f"DD guard: drawdown={current_dd_pct:.2%} < {DD_ROLLBACK_THRESHOLD:.0%}"
            )

        drift_log = _load_drift_log()
        current_drift = _weekly_drift(drift_log)

        # ── Drift Guard ───────────────────────────────────────────────
        if current_drift >= MAX_WEEKLY_DRIFT:
            logger.warning(
                "[BoundedUpdater] Drift=%.3f ≥ %.2f → update frozen.",
                current_drift, MAX_WEEKLY_DRIFT,
            )
            return {
                "status": "frozen",
                "weights": _load_weights(),
                "drift_total": round(current_drift, 4),
                "message": (
                    f"Weekly drift limit reached "
                    f"({current_drift:.1%} ≥ {MAX_WEEKLY_DRIFT:.0%})"
                ),
            }

        # ── Compute new weights ───────────────────────────────────────
        current_weights = _load_weights()
        new_weights = dict(current_weights)
        this_update_delta = 0.0

        for mod in winning_modules:
            if mod in new_weights:
                new_weights[mod] += WEIGHT_STEP_WIN
                this_update_delta += WEIGHT_STEP_WIN

        for mod in losing_modules:
            if mod in new_weights:
                # Clamp floor before accumulating delta
                raw = new_weights[mod] - WEIGHT_STEP_LOSE
                new_weights[mod] = max(MIN_WEIGHT, raw)
                this_update_delta += WEIGHT_STEP_LOSE

        projected_drift = current_drift + this_update_delta

        # ── Projected drift guard ─────────────────────────────────────
        if projected_drift > MAX_WEEKLY_DRIFT:
            logger.warning(
                "[BoundedUpdater] Projected drift=%.3f would exceed limit — frozen.",
                projected_drift,
            )
            return {
                "status": "frozen",
                "weights": current_weights,
                "drift_total": round(current_drift, 4),
                "message": (
                    "Projected drift would exceed weekly limit "
                    f"({projected_drift:.1%} > {MAX_WEEKLY_DRIFT:.0%}) — skipped"
                ),
            }

        # Clamp then normalize
        new_weights = _clamp(new_weights)
        new_weights = _normalize(new_weights)

        # ── Atomic write ──────────────────────────────────────────────
        _backup_now()
        _save_weights(new_weights)

        drift_log["weekly_deltas"].append(this_update_delta)
        _save_drift_log(drift_log)

        logger.info(
            "[BoundedUpdater] Updated. winners=%s losers=%s drift=%.3f",
            winning_modules, losing_modules, projected_drift,
        )

        return {
            "status": "updated",
            "weights": new_weights,
            "drift_total": round(projected_drift, 4),
            "message": (
                f"Updated: +{WEIGHT_STEP_WIN:.0%} winners, "
                f"-{WEIGHT_STEP_LOSE:.0%} losers. "
                f"Weekly drift now {projected_drift:.1%}."
            ),
        }

    def _rollback(self, reason: str) -> Dict:
        """Restore from backup YAML and reset drift log."""
        if not os.path.exists(_BACKUP_PATH):
            logger.error("[BoundedUpdater] No backup found for rollback!")
            try:
                weights = _load_weights()
            except Exception:
                weights = {m: round(1.0 / len(MODULES), 4) for m in MODULES}
            return {
                "status": "rollback_failed",
                "weights": weights,
                "drift_total": 0.0,
                "message": f"Rollback attempted but no backup exists. Reason: {reason}",
            }

        shutil.copy2(_BACKUP_PATH, _CONFIG_PATH)
        weights = _load_weights()
        _save_drift_log(_empty_drift_log())  # Reset drift counter after rollback
        logger.warning("[BoundedUpdater] ROLLBACK executed. Reason: %s", reason)

        return {
            "status": "rollback",
            "weights": weights,
            "drift_total": 0.0,
            "message": f"Rolled back to backup weights. Reason: {reason}",
        }

    # ------------------------------------------------------------------
    # Utility: expose current state without modifying anything
    # ------------------------------------------------------------------

    def get_status(self) -> Dict:
        """Return current weights, drift total, and guard states."""
        try:
            weights = _load_weights()
            log = _load_drift_log()
            drift = _weekly_drift(log)
            return {
                "weights": weights,
                "drift_total": round(drift, 4),
                "drift_limit": MAX_WEEKLY_DRIFT,
                "drift_frozen": drift >= MAX_WEEKLY_DRIFT,
                "backup_exists": os.path.exists(_BACKUP_PATH),
                "week_start": log.get("week_start", ""),
            }
        except Exception as exc:
            return {"error": str(exc)}
