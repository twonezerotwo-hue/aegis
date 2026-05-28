"""
AEGIS v7.0 — Attribution Engine

Calculates per-module PnL attribution when a trade closes.

Algorithm:
  1. Compute score delta per module: exit_score - entry_score
  2. Direction-correct deltas so positive = "contributed to the outcome"
  3. Normalize to contribution percentage (sum of abs deltas = 100%)
  4. Classify winning_modules (positive delta) vs losing_modules
  5. Persist to PostgreSQL attribution_logs table (non-blocking failure)

Design rules:
- Never raises to the caller — any error returns a safe fallback dict
- DB write failure is logged and swallowed; attribution_ref is still returned
- psycopg2-binary is used (present in requirements.txt)
- Table is created on first connection attempt if absent (idempotent)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

MODULES = ("touche", "fundamental", "news", "sentinel", "quantum")

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://aegis:aegis_secure_pass@postgres:5432/aegis",
)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS attribution_logs (
    id                  SERIAL PRIMARY KEY,
    attribution_ref     TEXT        NOT NULL,
    symbol              TEXT        NOT NULL DEFAULT 'UNKNOWN',
    trade_pnl           DOUBLE PRECISION NOT NULL,
    holding_period_h    DOUBLE PRECISION NOT NULL DEFAULT 0,
    touche_contrib      DOUBLE PRECISION NOT NULL DEFAULT 0,
    fundamental_contrib DOUBLE PRECISION NOT NULL DEFAULT 0,
    news_contrib        DOUBLE PRECISION NOT NULL DEFAULT 0,
    sentinel_contrib    DOUBLE PRECISION NOT NULL DEFAULT 0,
    quantum_contrib     DOUBLE PRECISION NOT NULL DEFAULT 0,
    winning_modules     TEXT,
    losing_modules      TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_INSERT_SQL = """
INSERT INTO attribution_logs
    (attribution_ref, symbol, trade_pnl, holding_period_h,
     touche_contrib, fundamental_contrib, news_contrib,
     sentinel_contrib, quantum_contrib,
     winning_modules, losing_modules)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def _try_ensure_table() -> None:
    """Create table if absent. Silent on any connection/query failure."""
    try:
        import psycopg2  # noqa: PLC0415
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=3)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(_CREATE_TABLE_SQL)
        conn.close()
        logger.info("[Attribution] attribution_logs table verified/created.")
    except Exception as exc:
        logger.warning(
            "[Attribution] Could not verify/create table (DB may be unreachable "
            "during container init): %r",
            exc,
        )


class AttributionEngine:
    """
    Computes per-module contribution percentages for a closed trade and
    optionally persists them to PostgreSQL.
    """

    def __init__(self) -> None:
        _try_ensure_table()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calculate(
        self,
        trade_pnl: float,
        entry_scores: Dict[str, float],
        exit_scores: Dict[str, float],
        holding_period: float = 0.0,
        symbol: str = "UNKNOWN",
    ) -> Dict:
        """
        Parameters
        ----------
        trade_pnl       : Realized PnL (positive = win, negative = loss).
        entry_scores    : Module scores 0–100 at trade entry.
                          Keys: touche, fundamental, news, sentinel, quantum.
        exit_scores     : Module scores 0–100 at trade exit.
        holding_period  : Hours the trade was open.
        symbol          : Instrument traded.

        Returns
        -------
        dict with keys:
            attribution_ref    : Unique reference string
            winning_modules    : list[str]
            losing_modules     : list[str]
            contribution_pct   : dict[str, float]  — values in [-1, 1]
        """
        try:
            return self._compute(
                trade_pnl, entry_scores, exit_scores, holding_period, symbol
            )
        except Exception as exc:
            logger.error("[Attribution] calculate() failed: %s", exc)
            ref = f"attr_ERR_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            return {
                "attribution_ref": ref,
                "winning_modules": [],
                "losing_modules": [],
                "contribution_pct": {m: 0.0 for m in MODULES},
                "error": str(exc),
            }

    # ------------------------------------------------------------------
    # Internal logic
    # ------------------------------------------------------------------

    def _compute(
        self,
        trade_pnl: float,
        entry_scores: Dict[str, float],
        exit_scores: Dict[str, float],
        holding_period: float,
        symbol: str,
    ) -> Dict:
        direction = 1.0 if trade_pnl >= 0.0 else -1.0

        # Raw delta per module: positive → "moved in the right direction"
        deltas: Dict[str, float] = {}
        for mod in MODULES:
            entry_s = float(entry_scores.get(mod, 50.0))
            exit_s = float(exit_scores.get(mod, 50.0))
            deltas[mod] = (exit_s - entry_s) * direction

        # Normalize to contribution percentage
        total_abs = sum(abs(v) for v in deltas.values())
        if total_abs > 0.0:
            contribution_pct = {
                m: round(v / total_abs, 4) for m, v in deltas.items()
            }
        else:
            # All deltas are 0 → equal attribution
            contribution_pct = {m: round(1.0 / len(MODULES), 4) for m in MODULES}

        # Classify by delta sign (direction-adjusted)
        if trade_pnl >= 0.0:
            winning_modules = [m for m, v in deltas.items() if v >= 0.0]
            losing_modules = [m for m, v in deltas.items() if v < 0.0]
        else:
            # For a losing trade the "guilty" modules are those whose score
            # moved against the position; swap semantics accordingly
            winning_modules = [m for m, v in deltas.items() if v < 0.0]
            losing_modules = [m for m, v in deltas.items() if v >= 0.0]

        # Ensure no empty lists
        if not winning_modules:
            winning_modules = list(MODULES[:1])
        if not losing_modules:
            losing_modules = []

        ref = (
            f"attr_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}"
            f"_{symbol.replace('/', '_')}"
        )

        self._write_db(
            ref, symbol, trade_pnl, holding_period,
            contribution_pct, winning_modules, losing_modules,
        )

        return {
            "attribution_ref": ref,
            "winning_modules": winning_modules,
            "losing_modules": losing_modules,
            "contribution_pct": contribution_pct,
        }

    def _write_db(
        self,
        ref: str,
        symbol: str,
        trade_pnl: float,
        holding_period: float,
        contribution_pct: Dict[str, float],
        winning_modules: List[str],
        losing_modules: List[str],
    ) -> None:
        """Persist to PostgreSQL. Logs and swallows any failure."""
        try:
            import psycopg2  # noqa: PLC0415
            conn = psycopg2.connect(DATABASE_URL, connect_timeout=3)
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    _INSERT_SQL,
                    (
                        ref,
                        symbol,
                        trade_pnl,
                        holding_period,
                        contribution_pct.get("touche", 0.0),
                        contribution_pct.get("fundamental", 0.0),
                        contribution_pct.get("news", 0.0),
                        contribution_pct.get("sentinel", 0.0),
                        contribution_pct.get("quantum", 0.0),
                        ",".join(winning_modules),
                        ",".join(losing_modules),
                    ),
                )
            conn.close()
            logger.info("[Attribution] Persisted: %s", ref)
        except Exception as exc:
            logger.warning(
                "[Attribution] DB write failed (non-critical) ref=%s: %r", ref, exc
            )
