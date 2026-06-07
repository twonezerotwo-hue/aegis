"""Best-effort audit trail for AEGIS agent API calls."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DATA_DIR = Path(os.getenv("AGENT_DATA_DIR", "/app/data"))
_AUDIT_PATH = _DATA_DIR / "agent_audit.jsonl"
_RING: deque[dict[str, Any]] = deque(maxlen=500)
_LOCK = threading.Lock()
_COUNTER = 0


def _stable_hash(payload: Any) -> str | None:
    if payload is None:
        return None
    try:
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        raw = repr(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _slim_output(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    keep = {
        "status",
        "running",
        "cycle",
        "changed",
        "signals_today",
        "journal_size",
        "decision_permission",
        "safety_mode",
    }
    slim: dict[str, Any] = {}
    for key in keep:
        if key not in payload:
            continue
        value = payload[key]
        if isinstance(value, (str, int, float, bool)) or value is None:
            slim[key] = value
        elif isinstance(value, (list, dict)):
            slim[key] = len(value)
    if "new_decisions" in payload and isinstance(payload["new_decisions"], list):
        slim["new_decisions"] = len(payload["new_decisions"])
    return slim or None


def record_agent_audit(
    *,
    endpoint: str,
    input_payload: Any = None,
    output_payload: Any = None,
    duration_ms: float | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record an audit entry without breaking the caller on failure."""
    global _COUNTER
    try:
        entry = {
            "id": None,
            "uid": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "endpoint": endpoint,
            "input_hash": _stable_hash(input_payload),
            "output_hash": _stable_hash(output_payload),
            "output_payload": _slim_output(output_payload),
            "duration_ms": round(duration_ms, 1) if duration_ms is not None else None,
            "extra": extra or {},
        }
        with _LOCK:
            _COUNTER += 1
            entry["id"] = _COUNTER
            _RING.append(entry)

        try:
            _AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
            with _AUDIT_PATH.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass
        return entry
    except Exception:
        return {"id": None, "endpoint": endpoint, "error": "audit_failed"}


def get_recent_agent_audit(limit: int = 50, endpoint: str | None = None) -> list[dict[str, Any]]:
    with _LOCK:
        items = list(_RING)
    items.reverse()
    if endpoint:
        items = [item for item in items if item.get("endpoint") == endpoint]
    return items[: max(1, min(limit, 500))]


def agent_audit_stats() -> dict[str, Any]:
    with _LOCK:
        items = list(_RING)
    by_endpoint: dict[str, int] = {}
    for item in items:
        endpoint = str(item.get("endpoint", "unknown"))
        by_endpoint[endpoint] = by_endpoint.get(endpoint, 0) + 1
    return {
        "total": len(items),
        "by_endpoint": by_endpoint,
        "ring_max": _RING.maxlen,
        "log_file": str(_AUDIT_PATH),
    }


__all__ = [
    "agent_audit_stats",
    "get_recent_agent_audit",
    "record_agent_audit",
]
