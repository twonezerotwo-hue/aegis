"""
Sentinel AI — Backtesting Engine

Sentinel multiplier'ın historik veride simulasyonu.
"""
from typing import List, Dict
from dataclasses import dataclass
import json

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class BacktestResult:
    """Backtest sonuçları."""
    start_date: str
    end_date: str
    periods: int
    avg_multiplier: float
    min_multiplier: float
    max_multiplier: float
    std_multiplier: float
    multiplier_changes: int  # Regime changes
    critical_alerts: int
    strategy_decisions: Dict[str, int]


class SentinelBacktester:
    """Sentinel AI backtesting engine."""

    def __init__(self):
        """Initialize backtester."""
        self.results = []
        self.alerts = []

    def backtest_from_data(
        self,
        market_data: List[Dict],  # Historical market data
        multiplier_engine=None,
    ) -> BacktestResult:
        """
        Run backtest on historical data.

        Args:
            market_data: List of {timestamp, vix, dxy, fear_greed, ...}
            multiplier_engine: Initialized multiplier engine

        Returns:
            BacktestResult
        """
        if not market_data:
            return BacktestResult(
                start_date="",
                end_date="",
                periods=0,
                avg_multiplier=1.0,
                min_multiplier=1.0,
                max_multiplier=1.0,
                std_multiplier=0.0,
                multiplier_changes=0,
                critical_alerts=0,
                strategy_decisions={},
            )

        multipliers = []
        regimes = []
        decision_counts = {"REDUCE_SIZE": 0, "MAINTAIN": 0, "INCREASE_SIZE": 0}
        critical_alerts = 0
        regime_changes = 0
        previous_regime = None

        for data in market_data:
            try:
                vix = data.get("vix", 20.0)
                dxy = data.get("dxy", 103.0)
                fear_greed = data.get("fear_greed", 50.0)

                # Calculate multiplier
                if multiplier_engine:
                    result = multiplier_engine.calculate_multiplier(
                        vix=vix,
                        dxy=dxy,
                        fear_greed=fear_greed,
                    )
                    multiplier = result.value
                    regime = result.regime
                else:
                    multiplier = 1.0
                    regime = None

                multipliers.append(multiplier)
                regimes.append(regime)

                # Track regime changes
                if previous_regime and regime != previous_regime:
                    regime_changes += 1
                previous_regime = regime

                # Track critical alerts
                if multiplier < 0.2 or vix > 40:
                    critical_alerts += 1

            except Exception as e:
                logger.error("backtest_error", error=str(e))

        # Calculate statistics
        avg_mult = sum(multipliers) / len(multipliers) if multipliers else 1.0
        min_mult = min(multipliers) if multipliers else 1.0
        max_mult = max(multipliers) if multipliers else 1.0

        # Std dev
        variance = sum((m - avg_mult) ** 2 for m in multipliers) / len(multipliers) if multipliers else 0
        std_mult = variance ** 0.5

        result = BacktestResult(
            start_date=market_data[0].get("timestamp", ""),
            end_date=market_data[-1].get("timestamp", ""),
            periods=len(market_data),
            avg_multiplier=avg_mult,
            min_multiplier=min_mult,
            max_multiplier=max_mult,
            std_multiplier=std_mult,
            multiplier_changes=regime_changes,
            critical_alerts=critical_alerts,
            strategy_decisions=decision_counts,
        )

        logger.info(
            "backtest_complete",
            periods=len(market_data),
            avg_multiplier=round(avg_mult, 3),
            regime_changes=regime_changes,
        )

        return result

    def export_results(self, result: BacktestResult, filename: str) -> None:
        """Export backtest results."""
        export_data = {
            "period": {
                "start": result.start_date,
                "end": result.end_date,
                "periods": result.periods,
            },
            "multiplier_stats": {
                "average": round(result.avg_multiplier, 4),
                "minimum": round(result.min_multiplier, 4),
                "maximum": round(result.max_multiplier, 4),
                "std_dev": round(result.std_multiplier, 4),
            },
            "regime_analysis": {
                "changes": result.multiplier_changes,
                "critical_alerts": result.critical_alerts,
            },
            "decisions": result.strategy_decisions,
        }

        with open(filename, "w") as f:
            json.dump(export_data, f, indent=2)

        logger.info("backtest_results_exported", filename=filename)

    def print_summary(self, result: BacktestResult) -> None:
        """Print backtest summary."""
        print("\n" + "="*70)
        print("SENTINEL AI BACKTEST RESULTS")
        print("="*70)
        print(f"Period: {result.start_date} to {result.end_date}")
        print(f"Total Periods: {result.periods}")
        print("\nRisk Multiplier Statistics:")
        print(f"  Average: {result.avg_multiplier:.4f}")
        print(f"  Range: [{result.min_multiplier:.4f}, {result.max_multiplier:.4f}]")
        print(f"  Std Dev: {result.std_multiplier:.4f}")
        print("\nRegimen Analysis:")
        print(f"  Regime Changes: {result.multiplier_changes}")
        print(f"  Critical Alerts: {result.critical_alerts}")
        print("\nStrategy Decisions:")
        for decision, count in result.strategy_decisions.items():
            print(f"  {decision}: {count}")
        print("="*70 + "\n")
