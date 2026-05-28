"""
Quantum AI Limited — Value at Risk Calculator

Portfolio'nun Value-at-Risk hesapla.
"""
from typing import Dict, List, Tuple
from dataclasses import dataclass
from datetime import datetime
import math

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class VARMetrics:
    """Value at Risk metrikleri."""
    var_95: float  # 95% confidence level
    var_99: float  # 99% confidence level
    cvar_95: float  # Conditional VAR (expected shortfall)
    max_loss: float
    portfolio_delta: float
    portfolio_gamma: float
    timestamp: datetime


class VARCalculator:
    """Portfolio VAR ve risk metrikleri hesapla."""

    def __init__(self, lookback_days: int = 30):
        """
        Args:
            lookback_days: Historical lookback period
        """
        self.lookback_days = lookback_days

    def calculate_var_historical(
        self,
        returns: List[float],
        confidence_level: float = 0.95,
    ) -> float:
        """
        Historical VAR hesapla.

        Args:
            returns: Geçmiş getirilerin listesi
            confidence_level: Confidence level (0.95 or 0.99)

        Returns:
            VAR değeri (negatif sayı)
        """
        if not returns or len(returns) < 2:
            return 0.0

        sorted_returns = sorted(returns)
        var_index = int(len(sorted_returns) * (1 - confidence_level))

        var = sorted_returns[var_index]

        logger.debug(
            "var_historical_calculated",
            confidence=confidence_level,
            var=round(var, 4),
        )

        return var

    def calculate_var_parametric(
        self,
        portfolio_value: float,
        daily_volatility: float,
        confidence_level: float = 0.95,
    ) -> float:
        """
        Parametric VAR hesapla (normal dağılım).

        Args:
            portfolio_value: Portfolio değeri
            daily_volatility: Günlük volatilite
            confidence_level: Confidence level

        Returns:
            VAR değeri (USD)
        """
        # Z-score for confidence level
        z_scores = {
            0.90: 1.28,
            0.95: 1.645,
            0.99: 2.326,
        }

        z = z_scores.get(confidence_level, 1.645)

        # VAR = Portfolio Value * Z * Volatility
        var = portfolio_value * z * daily_volatility

        logger.debug(
            "var_parametric_calculated",
            confidence=confidence_level,
            var=round(var, 2),
        )

        return var

    def calculate_cvar(
        self,
        returns: List[float],
        confidence_level: float = 0.95,
    ) -> float:
        """
        Conditional Value at Risk (Expected Shortfall).

        Args:
            returns: Geçmiş getirilerin listesi
            confidence_level: Confidence level

        Returns:
            CVAR değeri
        """
        if not returns or len(returns) < 2:
            return 0.0

        sorted_returns = sorted(returns)
        var_index = int(len(sorted_returns) * (1 - confidence_level))

        # Ortalama VAR'ın altındaki getiriler
        worst_returns = sorted_returns[:var_index]

        if worst_returns:
            cvar = sum(worst_returns) / len(worst_returns)
        else:
            cvar = sorted_returns[0]

        logger.debug(
            "cvar_calculated",
            cvar=round(cvar, 4),
        )

        return cvar

    def calculate_portfolio_greeks(
        self,
        positions: Dict[str, Dict],  # {symbol: {delta, gamma, vega}}
        position_sizes: Dict[str, float],
    ) -> Tuple[float, float, float, float]:
        """
        Portfolio Greeks hesapla.

        Args:
            positions: Her sembol için Greeks
            position_sizes: Her sembol için pozisyon

        Returns:
            (delta, gamma, vega, theta)
        """
        portfolio_delta = 0.0
        portfolio_gamma = 0.0
        portfolio_vega = 0.0
        portfolio_theta = 0.0

        for symbol, greeks in positions.items():
            size = position_sizes.get(symbol, 0.0)

            portfolio_delta += greeks.get("delta", 0.0) * size
            portfolio_gamma += greeks.get("gamma", 0.0) * size
            portfolio_vega += greeks.get("vega", 0.0) * size
            portfolio_theta += greeks.get("theta", 0.0) * size

        logger.info(
            "portfolio_greeks_calculated",
            delta=round(portfolio_delta, 3),
            gamma=round(portfolio_gamma, 4),
            vega=round(portfolio_vega, 3),
        )

        return portfolio_delta, portfolio_gamma, portfolio_vega, portfolio_theta

    def calculate_stress_scenario(
        self,
        portfolio_value: float,
        position_deltas: Dict[str, float],
        market_shock: float,  # -0.10 = 10% shock
    ) -> float:
        """
        Stress scenario altında portfolio kaybı.

        Args:
            portfolio_value: Portfolio değeri
            position_deltas: Her pozisyon için delta
            market_shock: Market shock (%)

        Returns:
            Beklenen kayıp (USD)
        """
        total_pnl = 0.0

        for symbol, delta in position_deltas.items():
            symbol_pnl = delta * portfolio_value * market_shock
            total_pnl += symbol_pnl

        logger.info(
            "stress_scenario_pnl",
            shock=round(market_shock * 100, 2),
            loss=round(total_pnl, 2),
        )

        return total_pnl

    def calculate_metrics(
        self,
        portfolio_value: float,
        daily_returns: List[float],
        position_deltas: Dict[str, float],
    ) -> VARMetrics:
        """
        Tüm VAR metrikleri hesapla.

        Args:
            portfolio_value: Portfolio değeri
            daily_returns: Günlük getiriler
            position_deltas: Pozisyon deltas

        Returns:
            VARMetrics
        """
        # Volatilite
        if daily_returns:
            mean_return = sum(daily_returns) / len(daily_returns)
            variance = sum(
                (r - mean_return) ** 2 for r in daily_returns
            ) / len(daily_returns)
            volatility = math.sqrt(variance)
        else:
            volatility = 0.02

        # VAR hesaplamaları
        var_95 = self.calculate_var_parametric(
            portfolio_value, volatility, 0.95
        )
        var_99 = self.calculate_var_parametric(
            portfolio_value, volatility, 0.99
        )
        cvar_95 = self.calculate_cvar(daily_returns, 0.95)

        # Portfolio Greeks
        portfolio_delta, portfolio_gamma, _, _ = self.calculate_portfolio_greeks(
            {k: {"delta": v} for k, v in position_deltas.items()},
            position_deltas,
        )

        # Maksimum kayıp
        max_loss = self.calculate_stress_scenario(
            portfolio_value, position_deltas, -0.10  # 10% shock
        )

        metrics = VARMetrics(
            var_95=var_95,
            var_99=var_99,
            cvar_95=cvar_95,
            max_loss=max_loss,
            portfolio_delta=portfolio_delta,
            portfolio_gamma=portfolio_gamma,
            timestamp=datetime.now(),
        )

        logger.info(
            "var_metrics_calculated",
            var_95=round(var_95, 2),
            var_99=round(var_99, 2),
            max_loss=round(max_loss, 2),
        )

        return metrics
