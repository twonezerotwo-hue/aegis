"""
Quantum AI Limited — Market Making Backtester

Market-making stratejisinin historik veride simulasyonu.
"""
from typing import Dict, List
from dataclasses import dataclass
import json

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class BacktestResult:
    """Backtest sonuçları."""
    start_date: str
    end_date: str
    total_return: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    max_drawdown: float
    sharpe_ratio: float
    final_portfolio_value: float
    trades: List[Dict]


class MMBacktester:
    """Market making stratejisi backtester."""

    def __init__(self, initial_capital: float = 100000.0):
        """
        Args:
            initial_capital: Başlangıç sermayesi
        """
        self.initial_capital = initial_capital
        self.portfolio_value = initial_capital
        self.trades = []
        self.daily_values = [initial_capital]

    def backtest_from_data(
        self,
        price_data: List[Dict],  # [{timestamp, symbol, mid_price, bid, ask, ...}]
        config: Dict,
    ) -> BacktestResult:
        """
        Historik veriden backtest çalıştır.

        Args:
            price_data: Historik fiyat verisi
            config: MM configuration

        Returns:
            BacktestResult
        """
        self.trades = []
        self.daily_values = [self.initial_capital]

        positions = {}
        inventory = {}

        for i, candle in enumerate(price_data):
            try:
                symbol = candle.get("symbol", "BTCUSDT")
                mid_price = candle.get("mid_price", 0.0)

                if mid_price == 0:
                    continue

                # Spread calculation (simplified)
                bid = candle.get("bid", mid_price * 0.9999)
                ask = candle.get("ask", mid_price * 1.0001)
                spread = ask - bid

                # Simulate fills (mock)
                if i % 10 == 0:  # Every 10 candles
                    # Bid side fill (we sell)
                    if bid > 0:
                        trade = {
                            "timestamp": candle.get("timestamp"),
                            "symbol": symbol,
                            "side": "SELL",
                            "price": bid,
                            "size": 0.1,
                            "pnl": 0.0,
                        }
                        self.trades.append(trade)
                        inventory[symbol] = inventory.get(symbol, 0.0) - 0.1

                if i % 11 == 0:  # Every 11 candles
                    # Ask side fill (we buy)
                    if ask > 0:
                        trade = {
                            "timestamp": candle.get("timestamp"),
                            "symbol": symbol,
                            "side": "BUY",
                            "price": ask,
                            "size": 0.1,
                            "pnl": 0.0,
                        }
                        self.trades.append(trade)
                        inventory[symbol] = inventory.get(symbol, 0.0) + 0.1

                # Update portfolio value (simplified)
                portfolio_value = self.initial_capital
                for sym, inv in inventory.items():
                    current_price = candle.get("mid_price", 0.0)
                    portfolio_value += inv * current_price

                self.daily_values.append(portfolio_value)

            except Exception as e:
                logger.error("backtest_error", error=str(e))

        # Calculate metrics
        result = self._calculate_metrics(price_data[0], price_data[-1])

        logger.info(
            "backtest_complete",
            total_trades=len(self.trades),
            final_value=self.portfolio_value,
            return_pct=result.total_return * 100,
        )

        return result

    def _calculate_metrics(self, start_data: Dict, end_data: Dict) -> BacktestResult:
        """Backtest metrikleri hesapla."""
        # Returns
        total_return = (self.portfolio_value - self.initial_capital) / self.initial_capital

        # Win rate
        winning_trades = sum(1 for t in self.trades if t.get("pnl", 0) > 0)
        losing_trades = sum(1 for t in self.trades if t.get("pnl", 0) < 0)
        win_rate = winning_trades / len(self.trades) if self.trades else 0.0

        # Max drawdown
        max_value = max(self.daily_values) if self.daily_values else self.initial_capital
        min_value = min(self.daily_values) if self.daily_values else self.initial_capital
        max_drawdown = (min_value - max_value) / max_value if max_value > 0 else 0.0

        # Sharpe ratio (simplified)
        if len(self.daily_values) > 1:
            returns = [
                (self.daily_values[i] - self.daily_values[i-1]) / self.daily_values[i-1]
                for i in range(1, len(self.daily_values))
            ]
            mean_return = sum(returns) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
            std_dev = variance ** 0.5
            sharpe = mean_return / std_dev if std_dev > 0 else 0.0
        else:
            sharpe = 0.0

        result = BacktestResult(
            start_date=start_data.get("timestamp", ""),
            end_date=end_data.get("timestamp", ""),
            total_return=total_return,
            total_trades=len(self.trades),
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe,
            final_portfolio_value=self.portfolio_value,
            trades=self.trades,
        )

        return result

    def export_results(self, result: BacktestResult, filename: str) -> None:
        """Backtest sonuçlarını dışa aktar."""
        export_data = {
            "start_date": result.start_date,
            "end_date": result.end_date,
            "initial_capital": self.initial_capital,
            "final_portfolio_value": result.final_portfolio_value,
            "total_return": result.total_return,
            "total_trades": result.total_trades,
            "winning_trades": result.winning_trades,
            "losing_trades": result.losing_trades,
            "win_rate": result.win_rate,
            "max_drawdown": result.max_drawdown,
            "sharpe_ratio": result.sharpe_ratio,
            "summary": {
                "return_pct": f"{result.total_return * 100:.2f}%",
                "annual_return": f"{result.total_return * 365 * 100:.2f}%",
                "max_dd_pct": f"{result.max_drawdown * 100:.2f}%",
            },
        }

        with open(filename, "w") as f:
            json.dump(export_data, f, indent=2)

        logger.info("results_exported", filename=filename)

    def print_summary(self, result: BacktestResult) -> None:
        """Backtest sonuçlarını yazdır."""
        print("\n" + "="*60)
        print("MARKET MAKING BACKTEST RESULTS")
        print("="*60)
        print(f"Period: {result.start_date} to {result.end_date}")
        print(f"Initial Capital: ${self.initial_capital:,.2f}")
        print(f"Final Portfolio: ${result.final_portfolio_value:,.2f}")
        print(f"Total Return: {result.total_return*100:.2f}%")
        print("\nTrading Statistics:")
        print(f"Total Trades: {result.total_trades}")
        print(f"Winning Trades: {result.winning_trades}")
        print(f"Losing Trades: {result.losing_trades}")
        print(f"Win Rate: {result.win_rate*100:.2f}%")
        print("\nRisk Metrics:")
        print(f"Max Drawdown: {result.max_drawdown*100:.2f}%")
        print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
        print("="*60 + "\n")
