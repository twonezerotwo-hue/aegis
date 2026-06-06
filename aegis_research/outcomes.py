from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import SignalCandidate


DEFAULT_RESEARCH_DIR = Path(os.getenv("AEGIS_RESEARCH_DIR", os.getenv("AGENT_DATA_DIR", "/app/data"))) / "aegis_research"
DEFAULT_CANDIDATES_PATH = DEFAULT_RESEARCH_DIR / "signal_candidates.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:
        return default
    return number


class JsonlOutcomeStore:
    """Append-only research store for signal candidates.

    This store records evidence for calibration. It never writes production
    config and never stores execution fields.
    """

    def __init__(self, path: Path | str = DEFAULT_CANDIDATES_PATH):
        self.path = Path(path)

    def record_candidate(self, candidate: SignalCandidate) -> dict[str, Any]:
        payload = candidate.to_dict()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        return payload

    def record_agent_decision(self, decision: dict[str, Any]) -> dict[str, Any]:
        score = _safe_float(decision.get("score"), 0.5)
        direction = str(decision.get("action", "NEUTRAL")).upper()
        candidate = SignalCandidate(
            signal_id=str(decision.get("signal_id") or uuid.uuid4()),
            symbol=str(decision.get("symbol", "UNKNOWN")),
            timeframe=str(decision.get("timeframe", "UNKNOWN")),
            direction=direction if direction in {"BUY", "SELL", "HOLD"} else "UNKNOWN",
            score=score,
            confidence=_safe_float(decision.get("confidence"), 0.0),
            edge=abs(score - 0.5),
            decision=str(decision.get("decision", "unknown")),
            reason=str(decision.get("reason", "")),
            mode=str(decision.get("mode", "UNKNOWN")),
            created_at=str(decision.get("ts") or _now_iso()),
            source="agent_loop",
            data_status=str(decision.get("data_status", "UNKNOWN")),
            module_scores={
                str(key): _safe_float(value)
                for key, value in dict(decision.get("module_scores") or {}).items()
            },
            metadata={
                "research_note": "candidate-only; no execution instruction",
            },
        )
        return self.record_candidate(candidate)

    def iter_candidates(self, limit: int | None = None) -> Iterable[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        if limit is not None:
            lines = lines[-limit:]
        records: list[dict[str, Any]] = []
        for line in lines:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records

    def summarize(self, limit: int = 500) -> dict[str, Any]:
        records = list(self.iter_candidates(limit=limit))
        by_decision: dict[str, int] = {}
        by_direction: dict[str, int] = {}
        for record in records:
            by_decision[str(record.get("decision", "unknown"))] = by_decision.get(str(record.get("decision", "unknown")), 0) + 1
            by_direction[str(record.get("direction", "unknown"))] = by_direction.get(str(record.get("direction", "unknown")), 0) + 1
        return {
            "status": "ok",
            "sample_size": len(records),
            "by_decision": by_decision,
            "by_direction": by_direction,
            "path": str(self.path),
            "safe_mode": "RESEARCH_ONLY_NO_EXECUTION",
        }


_DEFAULT_STORE: JsonlOutcomeStore | None = None


def get_default_store() -> JsonlOutcomeStore:
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = JsonlOutcomeStore()
    return _DEFAULT_STORE
