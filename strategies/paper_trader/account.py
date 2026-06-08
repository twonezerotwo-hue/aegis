from __future__ import annotations


class PaperAccount:
    """Minimal in-memory legacy paper account used by strategy tests."""

    def __init__(self, initial_capital: float = 100000.0) -> None:
        self.initial_capital = float(initial_capital)
        self.cash = float(initial_capital)
        self.btc_quantity = 0.0

    def execute_buy(self, *, current_price: float, amount_pct: float, signal_strength: float = 1.0) -> bool:
        price = float(current_price)
        amount_pct = max(0.0, min(1.0, float(amount_pct)))
        if price <= 0 or amount_pct <= 0:
            return False
        spend = min(self.cash, self.initial_capital * amount_pct * max(0.0, float(signal_strength)))
        if spend <= 0:
            return False
        self.cash -= spend
        self.btc_quantity += spend / price
        return True

    def execute_sell_partial(self, *, current_price: float, percentage: float, signal_strength: float = 1.0) -> bool:
        price = float(current_price)
        percentage = max(0.0, min(1.0, float(percentage)))
        if price <= 0 or percentage <= 0 or self.btc_quantity <= 0:
            return False
        quantity = self.btc_quantity * percentage * max(0.0, min(1.0, float(signal_strength)))
        if quantity <= 0:
            return False
        self.btc_quantity -= quantity
        self.cash += quantity * price
        return True
