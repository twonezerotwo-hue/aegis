# AEGIS v6.0 - Quantum AI Futures Extension | Purpose: Validate futures fetcher and consensus futures modifier logic.
import os
import sys
import asyncio

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from strategies.quantum_ai.services.futures_fetcher import FuturesFetcher
from consensus_engine import main as consensus_main


@pytest.mark.asyncio
async def test_futures_fetcher_overleveraged_long_modifier(monkeypatch):
    fetcher = FuturesFetcher()

    async def fake_fetch_json(path: str, params: dict[str, str]):
        if path == "/fapi/v1/premiumIndex":
            return {"lastFundingRate": "0.00012"}  # 0.012%
        if path == "/fapi/v1/openInterest":
            return {"openInterest": "12500000000"}
        if path == "/futures/data/globalLongShortAccountRatio":
            return [{"longShortRatio": "2.8"}]
        return {}

    monkeypatch.setattr(fetcher, "_fetch_json", fake_fetch_json)

    data = await fetcher.get_futures_data("BTCUSDT")
    assert data.futures_signal == "OVERLEVERAGED_LONG"
    assert data.modifier == 0.68  # 0.80 * 0.85
    assert data.open_interest_usdt == 12500000000.0


@pytest.mark.asyncio
async def test_futures_fetcher_fallback_on_error(monkeypatch):
    fetcher = FuturesFetcher()

    async def fake_fetch_json(path: str, params: dict[str, str]):
        raise RuntimeError("timeout")

    monkeypatch.setattr(fetcher, "_fetch_json", fake_fetch_json)

    data = await fetcher.get_futures_data("BTCUSDT")
    assert data.futures_signal == "CACHE_FALLBACK"
    assert data.modifier == 1.0
    assert data.funding_rate == 0.0
    assert data.open_interest_usdt == 0.0
    assert data.long_short_ratio == 1.0


def test_consensus_applies_quantum_futures_modifier_and_soft_warning():
    base_payload = {
        "symbol": "BTC",
        "touche_eqs": 78,
        "fundamental_score": 76,
        "sentinel_multiplier": 0.85,
        "quantum_score": 80,
        "quantum_signal": "BUY",
        "regime": "NORMALIZATION",
        "tf_signals": {"15m": "BUY", "1h": "BUY", "4h": "BUY", "1d": "BUY"},
        "cbr_sample_count": 28,
        "cbr_win_rate_pct": 64,
        "market_depth_usd": 900000,
        "spread_pct": 0.05,
        "event_risk_score": 0.25,
        "hours_to_event": 72,
    }

    no_flag = dict(base_payload)
    no_flag["quantum_futures_modifier"] = 1.0
    no_flag["quantum_futures_signal"] = "NEUTRAL"

    flagged = dict(base_payload)
    flagged["quantum_futures_modifier"] = 0.80
    flagged["quantum_futures_signal"] = "OVERLEVERAGED_LONG"

    result_no_flag = asyncio.run(consensus_main.process_signal(no_flag))
    result_flagged = asyncio.run(consensus_main.process_signal(flagged))

    assert "soft_warnings" in result_flagged
    assert result_flagged["soft_warnings"]["futures_risk_flag"] is True
    assert result_no_flag["soft_warnings"]["futures_risk_flag"] is False
    assert result_flagged["confidence"] <= result_no_flag["confidence"]
