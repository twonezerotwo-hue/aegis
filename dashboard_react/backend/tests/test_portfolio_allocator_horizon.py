from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.portfolio_allocator import build_allocation_plan


def _total_weight(plan: dict) -> float:
    return round(sum(plan["weights"].values()), 6)


def test_short_horizon_keeps_more_cash_than_long_horizon():
    short_plan = build_allocation_plan(horizon="short", regime="NORMALIZATION", metrics={"event_risk_score": 0.20, "vix": 18.0})
    long_plan = build_allocation_plan(horizon="long", regime="NORMALIZATION", metrics={"event_risk_score": 0.20, "vix": 18.0})

    assert short_plan["weights"]["cash"] > long_plan["weights"]["cash"]


def test_long_horizon_allows_more_btc_than_short_horizon():
    short_plan = build_allocation_plan(horizon="short", regime="LIQUIDITY_EXPANSION", metrics={"event_risk_score": 0.20, "vix": 16.0})
    long_plan = build_allocation_plan(horizon="long", regime="LIQUIDITY_EXPANSION", metrics={"event_risk_score": 0.20, "vix": 16.0})

    assert long_plan["weights"]["btc"] > short_plan["weights"]["btc"]


def test_medium_horizon_differs_from_short_and_long():
    short_plan = build_allocation_plan(horizon="short", regime="NORMALIZATION", metrics={"event_risk_score": 0.20, "vix": 18.0})
    medium_plan = build_allocation_plan(horizon="medium", regime="NORMALIZATION", metrics={"event_risk_score": 0.20, "vix": 18.0})
    long_plan = build_allocation_plan(horizon="long", regime="NORMALIZATION", metrics={"event_risk_score": 0.20, "vix": 18.0})

    assert medium_plan["weights"] != short_plan["weights"]
    assert medium_plan["weights"] != long_plan["weights"]


def test_weights_sum_to_one_and_cash_never_zero():
    for horizon in ("short", "medium", "long"):
        plan = build_allocation_plan(horizon=horizon, regime="NORMALIZATION", metrics={"event_risk_score": 0.20, "vix": 18.0})
        assert abs(_total_weight(plan) - 1.0) <= 0.00001
        assert plan["weights"]["cash"] > 0


def test_fallback_and_partial_fallback_force_illustrative_metadata():
    fallback_plan = build_allocation_plan(
        horizon="medium",
        regime="NORMALIZATION",
        metrics={"event_risk_score": 0.25, "vix": 22.0},
        data_status="FALLBACK",
        verified=False,
    )
    partial_plan = build_allocation_plan(
        horizon="medium",
        regime="NORMALIZATION",
        metrics={"event_risk_score": 0.25, "vix": 22.0},
        data_status="PARTIAL_FALLBACK",
        verified=False,
    )

    assert fallback_plan["allocation_profile"] == "fallback_illustrative"
    assert fallback_plan["verified"] is False
    assert "Illustrative allocation based on incomplete/fallback macro data." in fallback_plan["warnings"]
    assert partial_plan["allocation_profile"] == "fallback_illustrative"
    assert partial_plan["verified"] is False
    assert "Illustrative allocation based on incomplete/fallback macro data." in partial_plan["warnings"]


def test_event_risk_increases_cash_or_gold():
    calm_plan = build_allocation_plan(
        horizon="medium",
        regime="NORMALIZATION",
        metrics={"event_risk_score": 0.20, "vix": 18.0},
        verified=True,
        data_status="LIVE",
    )
    stressed_plan = build_allocation_plan(
        horizon="medium",
        regime="NORMALIZATION",
        metrics={"event_risk_score": 0.85, "vix": 18.0},
        verified=True,
        data_status="LIVE",
    )

    assert (
        stressed_plan["weights"]["cash"] > calm_plan["weights"]["cash"]
        or stressed_plan["weights"]["gold"] > calm_plan["weights"]["gold"]
    )


def test_hedge_on_increases_gold_or_bond():
    base_plan = build_allocation_plan(
        horizon="long",
        regime="NORMALIZATION",
        metrics={"event_risk_score": 0.20, "vix": 18.0},
        verified=True,
        data_status="LIVE",
        hedge_on=False,
    )
    hedge_plan = build_allocation_plan(
        horizon="long",
        regime="NORMALIZATION",
        metrics={"event_risk_score": 0.20, "vix": 18.0},
        verified=True,
        data_status="LIVE",
        hedge_on=True,
    )

    assert (
        hedge_plan["weights"]["gold"] > base_plan["weights"]["gold"]
        or hedge_plan["weights"]["bond"] > base_plan["weights"]["bond"]
    )


def test_allocation_plan_excludes_execution_fields():
    plan = build_allocation_plan(
        horizon="medium",
        regime="NORMALIZATION",
        metrics={"event_risk_score": 0.20, "vix": 18.0},
        verified=True,
        data_status="LIVE",
    )

    forbidden_fragments = ("execution", "order", "action", "position_size")
    for key in plan.keys():
        assert all(fragment not in key for fragment in forbidden_fragments)
