"""Dynamic exit signal tests for Touche and paper trader integration."""

from strategies.touche_ai import main as touche_main
from strategies.paper_trader.account import PaperAccount


def test_get_last_higher_low_detects_latest_hl():
    data = {
        "close": [100, 95, 102, 96, 108, 97, 110],
        "volume": [1000] * 7,
    }
    hl = touche_main.get_last_higher_low(data)
    assert hl == 97.0


def test_get_last_lower_high_detects_latest_lh():
    data = {
        "close": [100, 110, 102, 108, 101, 106, 99],
        "volume": [1000] * 7,
    }
    lh = touche_main.get_last_lower_high(data)
    assert lh == 106.0


def test_is_broken_works_for_long_and_short():
    assert touche_main.is_broken(current_price=99, level=100, side="LONG") is True
    assert touche_main.is_broken(current_price=101, level=100, side="LONG") is False
    assert touche_main.is_broken(current_price=101, level=100, side="SHORT") is True
    assert touche_main.is_broken(current_price=99, level=100, side="SHORT") is False


def test_touche_exit_signal_partial_close_when_overbought_low_volume(monkeypatch):
    def fake_ohlcv(symbol: str, limit: int = 120):
        closes = [100 + i for i in range(30)]
        volumes = [2000.0] * 29 + [500.0]
        return {"close": closes, "volume": volumes}

    monkeypatch.setattr(touche_main, "_get_recent_ohlcv", fake_ohlcv)
    monkeypatch.setattr(touche_main, "get_last_higher_low", lambda _df: 50.0)
    monkeypatch.setattr(touche_main, "get_last_lower_high", lambda _df: 200.0)

    import asyncio

    result = asyncio.run(
        touche_main.touche_exit_signal(symbol="BTCUSDT", position_side="LONG", entry_price=45000)
    )
    assert result["exit"] == "PARTIAL_CLOSE"
    assert result["percentage"] == 0.50
    assert result["reason"] == "Overbought + low volume"


def test_account_execute_sell_partial_reduces_position_and_keeps_remainder():
    account = PaperAccount(initial_capital=100000.0)
    account.execute_buy(current_price=50000.0, amount_pct=0.05, signal_strength=0.8)
    before_qty = account.btc_quantity

    ok = account.execute_sell_partial(current_price=51000.0, percentage=0.5, signal_strength=1.0)

    assert ok is True
    assert account.btc_quantity > 0.0
    assert account.btc_quantity < before_qty
