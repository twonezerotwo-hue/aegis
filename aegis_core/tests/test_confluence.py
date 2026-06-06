import pytest

from aegis_core.engine.confluence import apply_multi_tf_confluence


def test_confluence_boosts_aligned_signals():
    result = apply_multi_tf_confluence(60, {"4h": 70, "1d": 80})
    assert result["status"] == "aligned"
    assert result["multiplier"] == pytest.approx(1.20)
    assert result["adjusted_score"] > result["original_score"]


def test_confluence_penalizes_opposing_signals():
    result = apply_multi_tf_confluence(65, {"4h": 30, "1d": 20})
    assert result["status"] == "opposing"
    assert result["multiplier"] == pytest.approx(0.80)
    assert result["adjusted_score"] < result["original_score"]


def test_confluence_ignores_neutral_higher_timeframe_votes():
    result = apply_multi_tf_confluence(60, {"4h": 70, "1d": 50})
    assert result["status"] == "aligned"
    assert result["multiplier"] == pytest.approx(1.20)


def test_confluence_uses_direction_neutral_band():
    result = apply_multi_tf_confluence(52, {"4h": 80})
    assert result["status"] == "neutral"
    assert result["multiplier"] == pytest.approx(1.0)


def test_confluence_supports_explicit_signed_score_range():
    result = apply_multi_tf_confluence(
        {"value": 0.0, "range": "-1..1"},
        {"4h": {"value": 1.0, "range": "-1..1"}},
    )
    assert result["original_score"] == 50.0
    assert result["status"] == "neutral"
