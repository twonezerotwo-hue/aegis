"""
Unit Tests: Spread Optimizer & VAR Calculator
"""

from strategies.quantum_ai.src.mm_engine.spread_optimizer import SpreadOptimizer
from strategies.quantum_ai.src.risk_mgmt.var_calculator import VARCalculator


class TestSpreadOptimizer:
    """Spread optimizer tests."""

    def test_initialization(self):
        """Optimizer başlatılabilmeli."""
        optimizer = SpreadOptimizer()
        assert optimizer is not None

    def test_calculate_spread_basic(self):
        """Spread calculation test."""
        optimizer = SpreadOptimizer()

        volatility = 0.02
        fill_rate = 0.6

        spread = optimizer.calculate_spread(volatility, fill_rate)

        assert spread is not None
        assert isinstance(spread, float)
        assert spread > 0
        assert spread <= 10.0  # Max spread

    def test_calculate_spread_volatility(self):
        """Volatility affects spread."""
        optimizer = SpreadOptimizer()

        spread_low_vol = optimizer.calculate_spread(0.01, 0.5)
        spread_high_vol = optimizer.calculate_spread(0.05, 0.5)

        # Higher volatility → wider spread
        assert spread_high_vol >= spread_low_vol

    def test_adjust_for_market_conditions(self):
        """Market condition adjustments."""
        optimizer = SpreadOptimizer()

        base_spread = 2.0

        normal = optimizer.adjust_for_market_conditions(base_spread, "normal")
        high_vol = optimizer.adjust_for_market_conditions(base_spread, "high_vol")
        high_activity = optimizer.adjust_for_market_conditions(base_spread, "high_activity")

        assert normal > 0
        assert high_vol > normal  # High vol widens spread
        assert high_activity < normal  # High activity narrows spread


class TestVARCalculator:
    """Value at Risk calculator tests."""

    def test_initialization(self):
        """Calculator başlatılabilmeli."""
        calc = VARCalculator(lookback_days=30)
        assert calc is not None
        assert calc.lookback_days == 30

    def test_var_historical(self, historical_returns):
        """Historical VAR hesapla."""
        calc = VARCalculator()

        var_95 = calc.calculate_var_historical(historical_returns, 0.95)
        var_99 = calc.calculate_var_historical(historical_returns, 0.99)

        # VAR should be computed
        assert isinstance(var_95, float)
        assert isinstance(var_99, float)

        # VAR is based on worst returns up to confidence level
        # Both should be equal or 99 should be worse (more negative)
        assert var_99 <= var_95

    def test_var_parametric(self):
        """Parametric VAR hesapla."""
        calc = VARCalculator()

        portfolio_value = 100000.0
        volatility = 0.02

        var_95 = calc.calculate_var_parametric(portfolio_value, volatility, 0.95)
        var_99 = calc.calculate_var_parametric(portfolio_value, volatility, 0.99)

        # VAR positive (tutar)
        assert var_95 > 0
        assert var_99 > 0

        # VAR 99 > VAR 95
        assert var_99 > var_95

        # Reasonable range
        assert var_95 < portfolio_value * 0.1  # Less than 10%
        assert var_99 < portfolio_value * 0.2  # Less than 20%

    def test_cvar(self, historical_returns):
        """Conditional VAR hesapla."""
        calc = VARCalculator()

        cvar = calc.calculate_cvar(historical_returns, 0.95)

        assert cvar < 0  # Negative (kayıp)

    def test_cvar_worse_than_var(self, historical_returns):
        """CVAR daha kötü olmalı (VAR'dan daha)."""
        calc = VARCalculator()

        var = calc.calculate_var_historical(historical_returns, 0.95)
        cvar = calc.calculate_cvar(historical_returns, 0.95)

        # CVAR daha kötü (daha negatif)
        assert cvar < var or abs(cvar - var) < 0.0001

    def test_portfolio_greeks(self):
        """Portfolio Greeks hesapla."""
        calc = VARCalculator()

        positions = {
            "BTCUSDT": {"delta": 0.8, "gamma": 0.02, "vega": 0.5},
            "ETHUSDT": {"delta": 0.6, "gamma": 0.015, "vega": 0.3},
        }

        position_sizes = {
            "BTCUSDT": 1.0,
            "ETHUSDT": 10.0,
        }

        delta, gamma, vega, theta = calc.calculate_portfolio_greeks(
            positions, position_sizes
        )

        assert delta > 0
        assert gamma > 0
        assert vega > 0

    def test_stress_scenario(self):
        """Stress scenario hesapla."""
        calc = VARCalculator()

        portfolio_value = 100000.0
        position_deltas = {
            "BTCUSDT": 0.8,
            "ETHUSDT": 0.6,
        }

        loss_10pct = calc.calculate_stress_scenario(
            portfolio_value, position_deltas, -0.10
        )
        loss_5pct = calc.calculate_stress_scenario(
            portfolio_value, position_deltas, -0.05
        )

        # Daha büyük shock → daha büyük kayıp
        assert abs(loss_10pct) > abs(loss_5pct)

        # Negatif shock → negatif kayıp
        assert loss_10pct < 0

    def test_var_metrics_complete(self, historical_returns, portfolio_state):
        """Complete VAR metrics hesapla."""
        calc = VARCalculator()

        metrics = calc.calculate_metrics(
            portfolio_value=portfolio_state["portfolio_value"],
            daily_returns=historical_returns,
            position_deltas={"BTCUSDT": 0.8, "ETHUSDT": 0.6},
        )

        assert metrics.var_95 > 0
        assert metrics.var_99 > 0
        assert metrics.var_99 > metrics.var_95
        assert metrics.portfolio_delta > 0
        assert metrics.portfolio_gamma is not None

    def test_var_empty_returns(self):
        """Empty returns listesi."""
        calc = VARCalculator()

        var = calc.calculate_var_historical([], 0.95)
        assert var == 0.0

        cvar = calc.calculate_cvar([], 0.95)
        assert cvar == 0.0
