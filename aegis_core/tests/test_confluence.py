import pytest

from aegis_core.engine.confluence import apply_multi_tf_confluence


def test_confluence_boosts_aligned_signals():
    result = apply_multi_tf_confluence(60, {"4h": 70, "1d": 80})
    assert result["status"] == "aligned"
    assert result["multiplier"] == pytest.approx(1.15)
    assert result["adjusted_score"] > result["original_score"]


def test_confluence_penalizes_opposing_signals():
    result = apply_multi_tf_confluence(65, {"4h": 30, "1d": 20})
    assert result["status"] == "opposing"
    assert result["multiplier"] == pytest.approx(0.70)
    assert result["adjusted_score"] < result["original_score"]
