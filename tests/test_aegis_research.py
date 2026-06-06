from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aegis_research.calibration import suggest_module_weights, suggest_thresholds
from aegis_research.data_adapters import adapter_inventory
from aegis_research.metrics import calculate_metric_summary
from aegis_research.outcomes import JsonlOutcomeStore


def test_outcome_store_records_candidate_without_forbidden_execution_fields():
    path = ROOT / ".pytest_cache" / "aegis_research_candidates.jsonl"
    path.parent.mkdir(exist_ok=True)
    if path.exists():
        path.unlink()
    store = JsonlOutcomeStore(path)

    payload = store.record_agent_decision(
        {
            "ts": "2026-06-07T00:00:00+00:00",
            "symbol": "BTC/USDT",
            "timeframe": "5m",
            "action": "BUY",
            "score": 0.57,
            "confidence": 0.62,
            "decision": "would_signal",
            "reason": "candidate only",
            "mode": "DRY_RUN",
            "position_size": 0.5,
            "execution": {"venue": "blocked"},
        }
    )

    assert payload["direction"] == "BUY"
    assert "action" not in payload
    assert "position_size" not in payload
    assert "execution" not in payload
    assert store.summarize()["sample_size"] == 1
    path.unlink(missing_ok=True)


def test_metric_summary_and_threshold_suggestions_are_shadow_only():
    records = [
        {"direction": "BUY", "confidence": 0.65, "forward_return_pct": 0.02},
        {"direction": "SELL", "confidence": 0.60, "forward_return_pct": -0.01},
        {"direction": "BUY", "confidence": 0.55, "forward_return_pct": -0.01},
    ]

    metrics = calculate_metric_summary(records).to_dict()
    suggestion = suggest_thresholds(records).to_dict()

    assert metrics["sample_size"] == 3
    assert metrics["hit_rate"] == pytest.approx(2 / 3)
    assert suggestion["status"] == "INSUFFICIENT_SAMPLE"
    assert suggestion["shadow_only"] is True
    assert "action" not in suggestion
    assert "execution" not in suggestion


def test_weight_suggestion_never_writes_production_config():
    suggestion = suggest_module_weights(
        {
            "touche": {"hit_rate": 0.6, "calibration_error": 0.25},
            "fundamental": {"hit_rate": 0.55, "calibration_error": 0.30},
        },
        sample_size=50,
    ).to_dict()

    assert suggestion["status"] == "SHADOW_SUGGESTION"
    assert suggestion["shadow_only"] is True
    assert round(sum(suggestion["proposed_weights"].values()), 6) == 1.0
    assert "position_size" not in suggestion


def test_data_adapter_inventory_is_explicit_when_optional_dependencies_are_missing():
    inventory = adapter_inventory()

    assert inventory["yfinance"]["source"] == "yfinance"
    assert "verified" in inventory["yfinance"]
    assert "data_status" in inventory["technical_analysis"]
