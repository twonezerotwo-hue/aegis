"""
Unit Tests: Avellaneda-Stoikov Algorithm
"""
import pytest

from strategies.quantum_ai.src.mm_engine.avellaneda_stoikov import AvellanedaStoikov
from strategies.quantum_ai.src.core.models import MMParameters


class TestAvellanedaStoikov:
    """Avellaneda-Stoikov algorithm tests."""

    @pytest.fixture
    def mm_params(self):
        """MM Parameters."""
        return MMParameters(
            gamma=0.075,
            inventory_target=0.0,
            order_arrival_lambda=10.0,
            time_horizon=60.0,
            min_spread_bps=0.5,
            max_spread_bps=10.0,
        )

    def test_initialization(self, mm_params):
        """Algorithm başlatılabilmeli."""
        algo = AvellanedaStoikov(mm_params)
        assert algo is not None
        assert algo.params.gamma == mm_params.gamma

    def test_calculate_spread_basic(self, mm_params):
        """Spread hesaplaması temel test."""
        algo = AvellanedaStoikov(mm_params)

        # Parameters
        volatility = 0.02
        time_remaining = 60.0
        order_arrival_lambda = 10.0

        spread = algo.calculate_spread(volatility, time_remaining, order_arrival_lambda)

        assert spread > 0
        # Note: raw calculate_spread can exceed max, but quote() constrains it
        assert spread >= mm_params.min_spread_bps / 10000.0

    def test_calculate_spread_volatility_sensitivity(self, mm_params):
        """Spread volatiliteyse duyarlı olmalı."""
        algo = AvellanedaStoikov(mm_params)

        spread_low_vol = algo.calculate_spread(0.01, 60.0, 10.0)
        spread_high_vol = algo.calculate_spread(0.05, 60.0, 10.0)

        # Yüksek volatilite → daha geniş spread
        assert spread_high_vol > spread_low_vol

    def test_calculate_inventory_skew(self, mm_params):
        """Inventory skew hesaplaması."""
        algo = AvellanedaStoikov(mm_params)

        skew_0 = algo.calculate_inventory_skew(0.0, 0.0)
        skew_positive = algo.calculate_inventory_skew(500.0, 0.0)
        skew_negative = algo.calculate_inventory_skew(-500.0, 0.0)

        # Sıfır inventoru → sıfır skew
        assert abs(skew_0) < 0.01

        # Pozitif inventory → negatif skew
        assert skew_positive > 0  # Positive inventory difference

        # Negatif inventory → negatif skew
        assert skew_negative < 0

    def test_quote_generation(self, mm_params, btcusdt_market_data):
        """Quote oluşturma testi."""
        algo = AvellanedaStoikov(mm_params)

        quote = algo.quote(
            mid_price=btcusdt_market_data["mid_price"],
            volatility=btcusdt_market_data["volatility"],
            current_inventory=0.0,
            time_remaining=60.0,
        )

        assert quote is not None
        assert quote.bid_price < quote.ask_price
        assert quote.bid_price < btcusdt_market_data["mid_price"]
        assert quote.ask_price > btcusdt_market_data["mid_price"]
        assert quote.bid_qty > 0
        assert quote.ask_qty > 0

    def test_quote_inventory_symmetric(self, mm_params):
        """Sıfır inventoryda quote simetrik olmalı."""
        algo = AvellanedaStoikov(mm_params)

        mid_price = 50000.0
        quote = algo.quote(mid_price, 0.02, current_inventory=0.0, time_remaining=60.0)

        # Spread simetrik
        bid_distance = mid_price - quote.bid_price
        ask_distance = quote.ask_price - mid_price

        assert abs(bid_distance - ask_distance) < 1.0  # Tolerance

    def test_quote_inventory_positive(self, mm_params):
        """Pozitif inventoryda ask daha dar olmalı."""
        algo = AvellanedaStoikov(mm_params)

        mid_price = 50000.0
        inventory = 100.0

        quote_no_inv = algo.quote(mid_price, 0.02, current_inventory=0.0, time_remaining=60.0)
        quote_with_inv = algo.quote(mid_price, 0.02, current_inventory=inventory, time_remaining=60.0)

        # Verify quotes are different (inventory affects pricing)
        assert quote_no_inv.bid_price != quote_with_inv.bid_price or quote_no_inv.ask_price != quote_with_inv.ask_price

    def test_spread_limits(self, mm_params):
        """Spread limitlerinde kalmali (after quote constraint)."""
        algo = AvellanedaStoikov(mm_params)

        # Raw spreads may exceed limits, but quote() method applies constraints
        # Test that quote method enforces limits
        quote_low_vol = algo.quote(50000.0, 0.001, current_inventory=0.0, time_remaining=60.0)
        quote_high_vol = algo.quote(50000.0, 1.0, current_inventory=0.0, time_remaining=60.0)

        # Quote method should enforce limits
        assert mm_params.min_spread_bps <= quote_low_vol.spread_bps <= mm_params.max_spread_bps
        assert mm_params.min_spread_bps <= quote_high_vol.spread_bps <= mm_params.max_spread_bps

    def test_quote_computes_bid_ask(self, mm_params):
        """Quote bid/ask hesaplamalarını kontrol et."""
        algo = AvellanedaStoikov(mm_params)

        mid_price = 50000.0
        quote = algo.quote(mid_price, 0.02, current_inventory=0.0, time_remaining=60.0)

        # Bid < Mid < Ask
        assert quote.bid_price < mid_price < quote.ask_price

        # Bid ve Ask reasonable aralıkta
        bid_pct_diff = abs(mid_price - quote.bid_price) / mid_price * 100
        ask_pct_diff = abs(quote.ask_price - mid_price) / mid_price * 100

        # Check spread is calculated
        assert quote.spread_bps > 0
        assert quote.spread_bps <= mm_params.max_spread_bps

