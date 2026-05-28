from consensus_engine.src.signal_aggregator import SignalAggregator

def test_aggregator_macro_sentinel_blocks_all():
    # Fundamental harika olsa da, Sentinel (0.4) barajın (<0.5) altında olduğu için sistem HOLD'a çekilmelidir.
    signals = [
        {"strategy_id": "sentinel", "score": 0.4},
        {"strategy_id": "fundamental_ai", "recommendation": "BULLISH", "score": 90.0, "confidence": 0.8}
    ]
    res = SignalAggregator.aggregate(signals)
    assert res.final_recommendation == "HOLD"
    assert res.position_multiplier == 0.0

def test_aggregator_fundamental_weighting():
    # Temel veri skoru 30'dan küçük -> Çarpan 0.3'e ezilmelidir.
    signals = [
        {"strategy_id": "sentinel", "score": 1.0},
        {"strategy_id": "fundamental_ai", "recommendation": "BEARISH", "score": 25.0, "confidence": 0.9}
    ]
    res = SignalAggregator.aggregate(signals)
    assert res.final_recommendation == "BEARISH"
    assert res.position_multiplier == 0.3

def test_aggregator_technical_conflict_depreciates_confidence():
    # Uyuşmazlıktan (BULLISH vs BEARISH) ötürü fundamental confidence değeri Yarı yarıya (0.6 -> 0.3) düşmelidir.
    # Akabinde <0.4 güven durumuna düştüğü için Karar İptal edilmeli (HOLD)
    signals = [
        {"strategy_id": "sentinel", "score": 1.0},
        {"strategy_id": "fundamental", "recommendation": "BULLISH", "score": 50.0, "confidence": 0.6},
        {"strategy_id": "touche", "recommendation": "BEARISH"}
    ]
    res = SignalAggregator.aggregate(signals)
    assert res.final_confidence == 0.3
    assert res.final_recommendation == "HOLD"
    assert res.position_multiplier == 0.0
