"""
Tests for portfolio asset label fixes and real estate decision layer.
Verifies:
  - No garbled/abbreviated labels in frontend component
  - ASSET_METADATA has correct clean labels for all 5 assets
  - Commodity definition includes energy and industrial metals
  - Cash definition mentions liquidity reserve / opportunity capital
  - real_estate_decision contract in macro response
  - real_estate_decision never returns BUY_ZONE or BUILD_ZONE when data is unverified
  - required_checks is non-empty
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.portfolio_allocator import (
    ASSET_METADATA,
    build_real_estate_decision,
)
from routes import macro as macro_routes


# ── Frontend static checks ────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[2]
ALLOCATION_COMPONENT = ROOT / "frontend" / "src" / "components" / "portfolio" / "AllocationWithTip.tsx"


def _read_allocation_component() -> str:
    return ALLOCATION_COMPONENT.read_text(encoding="utf-8")


def test_no_garbled_label_axuxau():
    content = _read_allocation_component()
    assert "AuXAU" not in content


def test_no_garbled_label_bbtc():
    content = _read_allocation_component()
    assert "BBTC" not in content


def test_no_garbled_label_tbond():
    content = _read_allocation_component()
    assert "TBOND" not in content


def test_no_garbled_label_cemtia():
    content = _read_allocation_component()
    assert "CEMTIA" not in content


def test_gold_label_clean():
    content = _read_allocation_component()
    assert "ALTIN / GOLD" in content


def test_btc_label_clean():
    content = _read_allocation_component()
    assert "BITCOIN / BTC" in content


def test_bond_label_clean():
    content = _read_allocation_component()
    assert "TAHVİL / BONDS" in content or "TAHViL / BONDS" in content or "TAHV" in content


def test_commodity_label_clean():
    content = _read_allocation_component()
    assert "EMTİA / COMMODITIES" in content or "EMTiA / COMMODITIES" in content or "COMMODITIES" in content


def test_cash_label_clean():
    content = _read_allocation_component()
    assert "NAKİT / CASH" in content or "NAKiT / CASH" in content or "CASH" in content


# ── Backend ASSET_METADATA checks ────────────────────────────────────────────

def test_asset_metadata_has_all_assets():
    for asset in ("gold", "btc", "bond", "commodity", "cash"):
        assert asset in ASSET_METADATA, f"Missing asset: {asset}"


def test_asset_metadata_has_required_fields():
    required_fields = ("display_label", "subtitle", "definition", "portfolio_role", "increase_conditions", "reduce_conditions")
    for asset, meta in ASSET_METADATA.items():
        for field in required_fields:
            assert field in meta, f"Asset '{asset}' missing field '{field}'"


def test_commodity_definition_mentions_energy():
    defn = ASSET_METADATA["commodity"]["definition"].lower()
    assert "enerji" in defn or "energy" in defn, "Commodity definition must mention energy"


def test_commodity_definition_mentions_industrial_metals():
    defn = ASSET_METADATA["commodity"]["definition"].lower()
    assert "bakır" in defn or "copper" in defn or "sanayi" in defn or "industrial" in defn, \
        "Commodity definition must mention industrial metals"


def test_commodity_subtitle_mentions_brent():
    subtitle = ASSET_METADATA["commodity"]["subtitle"].lower()
    assert "brent" in subtitle or "energy" in subtitle


def test_cash_definition_mentions_liquidity_reserve():
    defn = ASSET_METADATA["cash"]["definition"].lower()
    assert "opsiyonellik" in defn or "liquidity" in defn or "reserve" in defn or "fırsat" in defn


def test_cash_subtitle_mentions_opportunity_capital():
    subtitle = ASSET_METADATA["cash"]["subtitle"].lower()
    assert "opportunity" in subtitle or "reserve" in subtitle or "liquidity" in subtitle


def test_all_display_labels_are_clean():
    garbled = ["AuXAU", "BBTC", "TBOND", "CEMTIA"]
    for asset, meta in ASSET_METADATA.items():
        label = meta["display_label"]
        for g in garbled:
            assert g not in label, f"Asset '{asset}' has garbled label fragment '{g}' in '{label}'"


# ── build_real_estate_decision unit tests ────────────────────────────────────

def test_real_estate_decision_returns_required_fields():
    result = build_real_estate_decision(
        horizon="medium",
        regime="NORMALIZATION",
        metrics={"vix": 18.0, "us10y": 4.0, "event_risk_score": 0.20, "brent": 82.0},
        data_status="LIVE",
        verified=True,
        cash_weight=0.25,
    )
    required = ("signal", "confidence", "data_status", "verified", "rationale",
                "buy_conditions", "avoid_conditions", "construction_conditions",
                "required_checks", "disclaimer")
    for field in required:
        assert field in result, f"Missing field: {field}"


def test_real_estate_required_checks_is_non_empty():
    result = build_real_estate_decision()
    assert isinstance(result["required_checks"], list)
    assert len(result["required_checks"]) >= 3


def test_real_estate_unverified_never_buy_zone():
    result = build_real_estate_decision(
        horizon="long",
        regime="LIQUIDITY_EXPANSION",
        metrics={"vix": 12.0, "us10y": 3.0, "event_risk_score": 0.10, "brent": 70.0},
        data_status="FALLBACK",
        verified=False,
        cash_weight=0.40,
    )
    assert result["signal"] not in ("BUY_ZONE", "BUILD_ZONE"), \
        f"Unverified data must not produce BUY_ZONE/BUILD_ZONE (got {result['signal']})"


def test_real_estate_unverified_partial_fallback_never_buy_zone():
    result = build_real_estate_decision(
        horizon="long",
        regime="ACCUMULATION",
        metrics={"vix": 14.0, "us10y": 3.2, "event_risk_score": 0.15, "brent": 78.0},
        data_status="PARTIAL_FALLBACK",
        verified=False,
        cash_weight=0.35,
    )
    assert result["signal"] not in ("BUY_ZONE", "BUILD_ZONE")


def test_real_estate_risk_off_signals_avoid():
    result = build_real_estate_decision(
        horizon="medium",
        regime="RISK_OFF",
        metrics={"vix": 35.0, "us10y": 4.8, "event_risk_score": 0.72, "brent": 105.0},
        data_status="LIVE",
        verified=True,
        cash_weight=0.30,
    )
    assert result["signal"] == "AVOID"


def test_real_estate_short_horizon_discourages_buy():
    result_short = build_real_estate_decision(
        horizon="short",
        regime="NORMALIZATION",
        metrics={"vix": 15.0, "us10y": 3.5, "event_risk_score": 0.15, "brent": 75.0},
        data_status="LIVE",
        verified=True,
        cash_weight=0.40,
    )
    result_long = build_real_estate_decision(
        horizon="long",
        regime="NORMALIZATION",
        metrics={"vix": 15.0, "us10y": 3.5, "event_risk_score": 0.15, "brent": 75.0},
        data_status="LIVE",
        verified=True,
        cash_weight=0.40,
    )
    assert result_short["confidence"] < result_long["confidence"]


def test_real_estate_signal_valid_enum():
    valid_signals = {"WAIT", "RESEARCH", "BUY_ZONE", "BUILD_ZONE", "AVOID"}
    for horizon in ("short", "medium", "long"):
        for regime in ("NORMALIZATION", "RISK_OFF", "LIQUIDITY_EXPANSION", "ACCUMULATION"):
            result = build_real_estate_decision(
                horizon=horizon,
                regime=regime,
                metrics={"vix": 20.0, "us10y": 4.0, "event_risk_score": 0.30, "brent": 85.0},
                data_status="LIVE",
                verified=True,
                cash_weight=0.25,
            )
            assert result["signal"] in valid_signals, f"Invalid signal: {result['signal']}"


# ── Macro endpoint integration: real_estate_decision in response ──────────────

class _FailingAsyncClient:
    def __init__(self, *args, **kwargs): pass
    async def __aenter__(self): return self
    async def __aexit__(self, exc_type, exc, tb): return False
    async def get(self, *args, **kwargs): raise RuntimeError("sentinel down")


def _all_market_live() -> dict:
    return {
        field: {
            "value": macro_routes._FALLBACK_METRICS[field],
            "source": "yfinance",
            "timestamp": "2026-05-29T10:00:00+00:00",
            "verified": True,
            "fallback_used": False,
        }
        for field in macro_routes._MARKET_FIELDS
    }


def test_macro_response_contains_real_estate_decision():
    async def _mock_fetch():
        return _all_market_live()

    async def _mock_live_scores(*args, **kwargs):
        return {"touche": None, "fundamental": None, "news": None, "sentinel": None}

    with patch.object(macro_routes, "fetch_market_data", _mock_fetch), \
         patch.object(macro_routes, "_fetch_live_scores", _mock_live_scores), \
         patch.object(macro_routes.httpx, "AsyncClient", _FailingAsyncClient):
        response = asyncio.run(macro_routes.get_macro_metrics("medium"))

    assert "real_estate_decision" in response
    rd = response["real_estate_decision"]
    assert "signal" in rd
    assert "confidence" in rd
    assert "required_checks" in rd
    assert len(rd["required_checks"]) >= 3
    assert rd["signal"] in {"WAIT", "RESEARCH", "BUY_ZONE", "BUILD_ZONE", "AVOID"}


def test_macro_response_contains_asset_metadata():
    async def _mock_fetch():
        return _all_market_live()

    async def _mock_live_scores(*args, **kwargs):
        return {"touche": None, "fundamental": None, "news": None, "sentinel": None}

    with patch.object(macro_routes, "fetch_market_data", _mock_fetch), \
         patch.object(macro_routes, "_fetch_live_scores", _mock_live_scores), \
         patch.object(macro_routes.httpx, "AsyncClient", _FailingAsyncClient):
        response = asyncio.run(macro_routes.get_macro_metrics("medium"))

    assert "asset_metadata" in response
    am = response["asset_metadata"]
    for asset in ("gold", "btc", "bond", "commodity", "cash"):
        assert asset in am, f"asset_metadata missing '{asset}'"
        assert "display_label" in am[asset]
