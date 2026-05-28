from consensus_engine.src.dynamic_weights import ModuleDynamicWeights


def test_winning_and_losing_modules_adjust_weights():
    manager = ModuleDynamicWeights()

    before = manager.get_weights("NORMALIZATION")
    update = manager.update_from_trade(
        winning_modules=["touche", "news"],
        losing_modules=["fundamental"],
        pnl=125.0,
        regime="NORMALIZATION",
    )
    after = update["weights"]

    assert after["touche"] > before["touche"]
    assert after["news"] > before["news"]
    assert after["fundamental"] < before["fundamental"]
    assert round(sum(after.values()), 6) == 1.0


def test_flat_pnl_keeps_weights_unchanged():
    manager = ModuleDynamicWeights()

    before = manager.get_weights("RISK_OFF")
    update = manager.update_from_trade(
        winning_modules=["touche"],
        losing_modules=["news"],
        pnl=0.0,
        regime="RISK_OFF",
    )

    assert update["weights"] == before
    assert update["message"] == "no change for flat pnl"
