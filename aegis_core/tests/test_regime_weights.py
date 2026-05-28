from pathlib import Path

import pytest

from aegis_core.engine.regime_weights import (
    get_weights_for_regime,
    load_consensus_weights,
    map_regime_to_weight_key,
)


def test_known_regime_maps_correctly():
    weight_key, warnings = map_regime_to_weight_key("LIQUIDITY_EXPANSION")
    assert weight_key == "mega_bull"
    assert warnings == []


def test_unknown_regime_falls_back_with_warning():
    result = get_weights_for_regime("SOMETHING_NEW")
    assert result["weight_key"] == "default"
    assert result["warnings"]
    assert "falling back to default" in result["warnings"][0]


def test_weights_sum_to_one_for_each_regime_in_yaml():
    config = load_consensus_weights()
    regime_weights = config["regime_weights"]

    for regime_name, regime_block in regime_weights.items():
        weight_sum = sum(
            float(regime_block[key])
            for key in regime_block
            if key.endswith("_weight")
        )
        assert weight_sum == pytest.approx(1.0), regime_name

    assert Path("aegis_core/config/consensus_weights.yaml").exists()
