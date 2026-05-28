"""
strategies/cbr_engine/clickhouse_writer.py
AEGIS v7.2 — Async ClickHouse batch writer for trade analytics.

Writes trade logs to ClickHouse as an analytic sink via the HTTP interface.
PostgreSQL trade_journal remains the primary source of truth.
Any ClickHouse error triggers a warning log and is silently skipped —
the main trading pipeline is never interrupted.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "clickhouse")
_CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_HTTP_PORT", "8123"))
_CLICKHOUSE_DB   = os.getenv("CLICKHOUSE_DB", "aegis")
_CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
_CLICKHOUSE_PASS = os.getenv("CLICKHOUSE_PASSWORD", "clickhouse_pass")
_BASE_URL        = f"http://{_CLICKHOUSE_HOST}:{_CLICKHOUSE_PORT}"

# Column order must match the target ClickHouse table schema
_INSERT_COLUMNS = (
    "trade_id",
    "symbol",
    "action",
    "confidence",
    "five_module_score",
    "regime",
    "horizon",
    "entry_price",
    "position_size",
    "kelly_fraction",
    "created_at",
)

_CREATE_TABLE_DDL = f"""
CREATE TABLE IF NOT EXISTS {_CLICKHOUSE_DB}.trade_logs (
    trade_id        String,
    symbol          String,
    action          String,
    confidence      Float32,
    five_module_score Float32,
    regime          String,
    horizon         String,
    entry_price     Float64,
    position_size   Float64,
    kelly_fraction  Float32,
    created_at      DateTime64(3, 'UTC')
) ENGINE = MergeTree()
ORDER BY (symbol, created_at)
PARTITION BY toYYYYMM(created_at);
""".strip()


# ── Low-level HTTP helpers ──────────────────────────────────────────────────

def _auth_params() -> dict[str, str]:
    return {"user": _CLICKHOUSE_USER, "password": _CLICKHOUSE_PASS}


async def _ping(client: httpx.AsyncClient) -> bool:
    try:
        resp = await client.get(f"{_BASE_URL}/ping", params=_auth_params(), timeout=4.0)
        return resp.status_code == 200 and resp.text.strip() == "Ok."
    except Exception as exc:  # noqa: BLE001
        logger.warning("CLICKHOUSE_FALLBACK: ping failed — %s", exc)
        return False


async def _execute(client: httpx.AsyncClient, sql: str) -> bool:
    try:
        resp = await client.post(
            _BASE_URL,
            params=_auth_params(),
            content=sql.encode(),
            timeout=10.0,
        )
        if resp.status_code != 200:
            logger.warning("CLICKHOUSE_FALLBACK: query error %d — %s", resp.status_code, resp.text[:200])
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("CLICKHOUSE_FALLBACK: Skipping async write — %s", exc)
        return False


# ── Table bootstrap ─────────────────────────────────────────────────────────

async def ensure_table() -> bool:
    """Create trade_logs table if it does not exist. Soft-fail."""
    async with httpx.AsyncClient() as client:
        if not await _ping(client):
            return False
        return await _execute(client, _CREATE_TABLE_DDL)


# ── Batch writer ────────────────────────────────────────────────────────────

class ClickHouseBatchWriter:
    """
    Accumulates trade records in memory and flushes them to ClickHouse
    in a single INSERT when flush() is called (or when the queue overflows).

    Usage::

        writer = ClickHouseBatchWriter()
        await writer.enqueue(record_dict)
        await writer.flush()
    """

    _MAX_QUEUE = 500

    def __init__(self) -> None:
        self._queue: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()

    async def enqueue(self, record: dict[str, Any]) -> None:
        """Add a trade record to the batch queue. Auto-flushes on overflow."""
        async with self._lock:
            self._queue.append(record)
            if len(self._queue) >= self._MAX_QUEUE:
                await self._flush_locked()

    async def flush(self) -> int:
        """Flush pending records to ClickHouse. Returns number of rows written."""
        async with self._lock:
            return await self._flush_locked()

    async def _flush_locked(self) -> int:
        if not self._queue:
            return 0
        batch = self._queue[:]
        self._queue.clear()

        rows = _build_tsv(batch)
        sql = (
            f"INSERT INTO {_CLICKHOUSE_DB}.trade_logs"
            f" ({', '.join(_INSERT_COLUMNS)}) FORMAT TSV\n{rows}"
        )
        async with httpx.AsyncClient() as client:
            ok = await _execute(client, sql)

        if ok:
            logger.debug("CLICKHOUSE: flushed %d rows", len(batch))
            return len(batch)

        logger.warning(
            "CLICKHOUSE_FALLBACK: Skipping async write — %d rows dropped", len(batch)
        )
        return 0


def _build_tsv(records: list[dict[str, Any]]) -> str:
    """Serialise a list of record dicts to ClickHouse TSV rows."""
    lines: list[str] = []
    for r in records:
        created_at = r.get("created_at", datetime.now(timezone.utc))
        if isinstance(created_at, datetime):
            created_at = created_at.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        row = "\t".join([
            str(r.get("trade_id", "")),
            str(r.get("symbol", "")),
            str(r.get("action", "")),
            str(float(r.get("confidence", 0.0))),
            str(float(r.get("five_module_score", 0.0))),
            str(r.get("regime", "")),
            str(r.get("horizon", "")),
            str(float(r.get("entry_price", 0.0))),
            str(float(r.get("position_size", 0.0))),
            str(float(r.get("kelly_fraction", 0.0))),
            str(created_at),
        ])
        lines.append(row)
    return "\n".join(lines)


# ── Module-level singleton ──────────────────────────────────────────────────

_writer = ClickHouseBatchWriter()


async def log_trade(record: dict[str, Any]) -> None:
    """Convenience wrapper — enqueue a single trade record."""
    await _writer.enqueue(record)


async def flush_trades() -> int:
    """Flush all pending records. Returns rows written."""
    return await _writer.flush()


# ── Health check helper ─────────────────────────────────────────────────────

async def health_check() -> dict[str, Any]:
    """
    Returns a health dict suitable for a FastAPI /health/clickhouse endpoint.

    Never raises — on any error returns status="unavailable".
    """
    async with httpx.AsyncClient() as client:
        try:
            reachable = await _ping(client)
            if not reachable:
                return {"status": "unavailable", "host": _CLICKHOUSE_HOST, "detail": "ping failed"}

            resp = await client.get(
                _BASE_URL,
                params={**_auth_params(), "query": "SELECT 1"},
                timeout=4.0,
            )
            if resp.status_code == 200:
                return {
                    "status": "ok",
                    "host": _CLICKHOUSE_HOST,
                    "port": _CLICKHOUSE_PORT,
                    "db": _CLICKHOUSE_DB,
                }
            return {
                "status": "degraded",
                "host": _CLICKHOUSE_HOST,
                "detail": f"SELECT 1 returned HTTP {resp.status_code}",
            }
        except Exception as exc:  # noqa: BLE001
            return {"status": "unavailable", "host": _CLICKHOUSE_HOST, "detail": str(exc)}
