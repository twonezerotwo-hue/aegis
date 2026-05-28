from macro_bridge.executor.trade_executor import calculate_asset_allocation, generate_rebalance_signal


def test_allocation_has_all_required_assets_and_sums_to_one():
    allocation = calculate_asset_allocation("normalization", macro_score=0.0, hedge=False)

    assert set(allocation.keys()) == {"gold", "btc", "bond", "commodity", "cash"}
    assert abs(sum(allocation.values()) - 1.0) <= 0.0001


def test_risk_on_high_score_overweights_btc_vs_risk_off_low_score():
    risk_on = calculate_asset_allocation("liquidity_expansion", macro_score=0.8, hedge=False)
    risk_off = calculate_asset_allocation("risk_off", macro_score=-0.8, hedge=False)

    assert risk_on["btc"] > risk_off["btc"]
    assert risk_off["bond"] > risk_on["bond"]


def test_hedge_overlay_increases_defensive_buckets():
    base = calculate_asset_allocation("normalization", macro_score=0.1, hedge=False)
    hedged = calculate_asset_allocation("normalization", macro_score=0.1, hedge=True)

    assert hedged["gold"] > base["gold"]
    assert hedged["bond"] > base["bond"]
    assert hedged["cash"] > base["cash"]
    assert hedged["btc"] < base["btc"]


def test_rebalance_signal_triggers_when_drift_exceeds_five_percent():
    target = {"gold": 0.20, "btc": 0.30, "bond": 0.20, "commodity": 0.10, "cash": 0.20}
    current = {"gold": 0.10, "btc": 0.38, "bond": 0.18, "commodity": 0.14, "cash": 0.20}

    signal = generate_rebalance_signal(target, current_allocation=current, threshold=0.05)

    assert signal["rebalance_required"] is True
    assert any(action["asset"] == "gold" and action["action"] == "BUY" for action in signal["actions"])
    assert any(action["asset"] == "btc" and action["action"] == "SELL" for action in signal["actions"])


def test_rebalance_signal_stays_idle_when_drift_within_threshold():
    target = {"gold": 0.20, "btc": 0.30, "bond": 0.20, "commodity": 0.10, "cash": 0.20}
    current = {"gold": 0.18, "btc": 0.32, "bond": 0.19, "commodity": 0.11, "cash": 0.20}

    signal = generate_rebalance_signal(target, current_allocation=current, threshold=0.05)

    assert signal["rebalance_required"] is False
    assert signal["actions"] == []
