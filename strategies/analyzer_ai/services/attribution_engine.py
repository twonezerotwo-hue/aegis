import json
import logging
import os
import time
from typing import Any

import psycopg2
import psycopg2.extras
from redis import Redis

try:
    from models.attribution import ExitAttributionResponse, ModuleAttributionStats
except ModuleNotFoundError:
    from strategies.analyzer_ai.models.attribution import ExitAttributionResponse, ModuleAttributionStats

logger = logging.getLogger(__name__)


class ExitAttributionEngine:
    """Compute module-level exit attribution from closed trade journal rows."""

    CACHE_TTL_SECONDS = 300

    def __init__(self) -> None:
        self.database_url = os.getenv(
            "DATABASE_URL", "postgresql://aegis:aegis_secure_pass@postgres:5432/aegis"
        )
        self.redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        self._in_memory_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._redis_client = self._init_redis()

    def _init_redis(self) -> Redis | None:
        try:
            client = Redis.from_url(self.redis_url, decode_responses=True)
            client.ping()
            return client
        except Exception as exc:
            logger.warning("[exit_attribution] Redis unavailable, using in-memory cache: %s", exc)
            return None

    def _cache_get(self, key: str) -> dict[str, Any] | None:
        if self._redis_client is not None:
            try:
                payload = self._redis_client.get(key)
                if payload:
                    return json.loads(payload)
            except Exception as exc:
                logger.warning("[exit_attribution] Redis cache get failed: %s", exc)

        entry = self._in_memory_cache.get(key)
        if entry is None:
            return None
        expiry_ts, payload = entry
        if time.time() >= expiry_ts:
            self._in_memory_cache.pop(key, None)
            return None
        return payload

    def _cache_set(self, key: str, payload: dict[str, Any]) -> None:
        if self._redis_client is not None:
            try:
                self._redis_client.setex(key, self.CACHE_TTL_SECONDS, json.dumps(payload))
                return
            except Exception as exc:
                logger.warning("[exit_attribution] Redis cache set failed: %s", exc)
        self._in_memory_cache[key] = (time.time() + self.CACHE_TTL_SECONDS, payload)

    def _period_filter_sql(self, period: str) -> str:
        normalized = (period or "7d").strip().lower()
        if normalized == "30d":
            return "AND COALESCE(closed_at, updated_at, created_at) >= NOW() - INTERVAL '30 days'"
        if normalized == "7d":
            return "AND COALESCE(closed_at, updated_at, created_at) >= NOW() - INTERVAL '7 days'"
        return ""

    def _fetch_trade_rows(self, period: str) -> list[dict[str, Any]]:
        where_period = self._period_filter_sql(period)
        queries = [
            f"""
            SELECT
                entry_reason,
                exit_reason,
                exit_price,
                pnl_pct,
                closed_at
            FROM trade_journal
            WHERE exit_reason IS NOT NULL
            {where_period}
            ORDER BY COALESCE(closed_at, updated_at, created_at) DESC
            """,
            f"""
            SELECT
                entry_reason,
                exit_reason,
                exit_price,
                pnl_pct,
                created_at AS closed_at
            FROM trade_journal
            WHERE exit_reason IS NOT NULL
            {where_period.replace('COALESCE(closed_at, updated_at, created_at)', 'created_at')}
            ORDER BY created_at DESC
            """,
        ]

        for query in queries:
            try:
                with psycopg2.connect(self.database_url) as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                        cur.execute(query)
                        result = cur.fetchall()
                        return [dict(r) for r in result]
            except Exception as exc:
                logger.warning("[exit_attribution] trade_journal query variant failed: %s", exc)

        return []

    @staticmethod
    def _role_from_score(module_key: str, score: float) -> str:
        if module_key == "sentinel_ai" and score > 0:
            return "Risk Saver"
        if score >= 1.5:
            return "Profit Driver"
        if score <= -1.0:
            return "False Alarm"
        if score > 0:
            return "Supportive"
        return "Neutral"

    @staticmethod
    def _safe_text(value: Any) -> str:
        return str(value or "").strip().lower()

    def _classify_trade(self, entry_reason: str, exit_reason: str, pnl_pct: float) -> list[tuple[str, float]]:
        entry_txt = self._safe_text(entry_reason)
        exit_txt = self._safe_text(exit_reason)

        # Scenario 5: Structural conflict - Fundamental gave early warning.
        if "conflict" in exit_txt and "fundamental" in exit_txt:
            return [("fundamental_ai", 0.2)]

        # Scenario 2: Macro protection by Sentinel (risk-off / VIX / DXY triggers early exit).
        if any(token in exit_txt for token in ("risk-off", "risk_off", "vix", "dxy", "sentinel")):
            return [("sentinel_ai", 0.5)]

        # Scenario 3: Liquidity stress handled by Quantum.
        if any(token in exit_txt for token in ("liquidity", "spread", "depth", "quantum")):
            return [("quantum_ai", -0.5)]

        # Scenario 1: Stop loss indicates technical failure by Touche.
        if any(token in exit_txt for token in ("stoploss", "stop_loss", "sl", "higher low broke")):
            return [("touche_ai", -1.0)]

        # Scenario 4: Take-profit hit indicates successful technical execution by Touche.
        if any(token in exit_txt for token in ("takeprofit", "take_profit", "tp", "target hit")):
            return [("touche_ai", 1.0)]

        # Fallback bias: if no explicit exit label, infer with pnl sign and technical entry marker.
        if "touche" in entry_txt or "eqs" in entry_txt:
            return [("touche_ai", 1.0 if pnl_pct > 0 else -1.0)]

        return []

    def compute(self, period: str = "7d") -> ExitAttributionResponse:
        normalized_period = (period or "7d").strip().lower()
        if normalized_period not in {"7d", "30d", "all"}:
            normalized_period = "7d"

        cache_key = f"exit_attribution:{normalized_period}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return ExitAttributionResponse.model_validate(cached)

        rows = self._fetch_trade_rows(normalized_period)

        if not rows:
            result = ExitAttributionResponse(period=normalized_period, modules={})
            self._cache_set(cache_key, result.model_dump())
            return result

        modules: dict[str, dict[str, float]] = {
            "touche_ai": {"total_trades": 0, "wins": 0, "score": 0.0},
            "sentinel_ai": {"total_trades": 0, "wins": 0, "score": 0.0},
            "fundamental_ai": {"total_trades": 0, "wins": 0, "score": 0.0},
            "quantum_ai": {"total_trades": 0, "wins": 0, "score": 0.0},
        }

        for row in rows:
            entry_reason = str(row.get("entry_reason") or "")
            exit_reason = str(row.get("exit_reason") or "")
            pnl_pct = float(row.get("pnl_pct") or 0.0)

            contributions = self._classify_trade(entry_reason, exit_reason, pnl_pct)
            for module_key, delta in contributions:
                modules[module_key]["total_trades"] += 1
                modules[module_key]["score"] += float(delta)
                if pnl_pct > 0:
                    modules[module_key]["wins"] += 1

        response_modules: dict[str, ModuleAttributionStats] = {}
        for module_key, agg in modules.items():
            total = int(agg["total_trades"])
            wins = int(agg["wins"])
            score = round(float(agg["score"]), 4)
            win_rate = round((wins / total), 4) if total > 0 else 0.0
            response_modules[module_key] = ModuleAttributionStats(
                total_trades=total,
                win_rate=win_rate,
                attribution_score=score,
                role=self._role_from_score(module_key, score),
            )

        result = ExitAttributionResponse(period=normalized_period, modules=response_modules)
        payload = result.model_dump()
        self._cache_set(cache_key, payload)
        return result
