from macro_bridge.macro.scorer import calculate_score


def test_score_is_bounded():
    score = calculate_score(dxy=99, us10y=3.4, btc_d=50, usdt_d=3, hg=4.2, vix=12)
    assert -1.0 <= score <= 1.0


def test_positive_scenario_scores_higher_than_risk_off():
    positive = calculate_score(dxy=100, us10y=3.6, btc_d=52, usdt_d=3.2, hg=4.3, vix=13)
    negative = calculate_score(dxy=105, us10y=4.8, btc_d=60, usdt_d=7.5, hg=3.1, vix=30)
    assert positive > negative
