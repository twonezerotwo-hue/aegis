"""
AEGIS CBR Engine - FAZ 6: Live Monitor
Track live performance, equity curve, drawdown, and notifications
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional
from datetime import datetime
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Live performance metrics"""
    total_return: float
    current_drawdown: float
    max_drawdown: float
    win_rate: float
    sharpe_ratio: float
    consecutive_wins: int
    consecutive_losses: int
    consecutive_loss_streak: int
    trade_count: int
    winning_trades: int
    losing_trades: int


class LiveMonitor:
    """
    Real-time performance monitoring for paper/live trading.

    Tracks:
    - Equity curve
    - Drawdowns (current and max)
    - Trade statistics
    - Performance metrics (Sharpe, win rate, etc.)
    - Alerts and notifications
    """

    def __init__(
        self,
        initial_capital: float = 100000,
        max_dd_warning: float = 0.10,
        max_dd_critical: float = 0.20,
        max_consecutive_losses: int = 5,
        telegram_token: Optional[str] = None,
        slack_webhook: Optional[str] = None,
    ):
        """
        Args:
            initial_capital: Starting capital
            max_dd_warning: Drawdown threshold for warning
            max_dd_critical: Drawdown threshold for critical alert
            max_consecutive_losses: Alert on N consecutive losses
            telegram_token: Telegram bot token (optional)
            slack_webhook: Slack webhook URL (optional)
        """
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.equity_history = [initial_capital]
        self.trades = []
        self.timestamps = [datetime.now()]

        self.max_dd_warning = max_dd_warning
        self.max_dd_critical = max_dd_critical
        self.max_consecutive_losses = max_consecutive_losses

        self.telegram_token = telegram_token
        self.slack_webhook = slack_webhook
        self.alerts = []

        logger.info(
            f"LiveMonitor initialized: capital=${initial_capital:,.2f}, "
            f"max_dd_warning={max_dd_warning:.1%}, max_dd_critical={max_dd_critical:.1%}"
        )

    def record_trade(
        self,
        trade_result: float,
        trade_type: str = 'SIGNAL',
        confidence: float = 0.0,
        position_size: float = 0.0,
        symbol: str = 'BTC/USD',
        notes: Optional[str] = None,
    ):
        """Record a trade result and update equity"""
        old_equity = self.current_capital
        pnl = old_equity * trade_result
        self.current_capital += pnl

        trade_record = {
            'timestamp': datetime.now(),
            'type': trade_type,
            'return': trade_result,
            'pnl': pnl,
            'equity_after': self.current_capital,
            'confidence': confidence,
            'position_size': position_size,
            'symbol': symbol,
            'notes': notes,
            'win': trade_result > 0,
        }

        self.trades.append(trade_record)
        self.equity_history.append(self.current_capital)
        self.timestamps.append(datetime.now())

        self._check_alerts()
        self._notify_trade(trade_record)

        logger.info(
            f"Trade recorded: {symbol} {trade_type} | "
            f"Return: {trade_result:+.2%} | Equity: ${self.current_capital:,.2f}"
        )

    def _check_alerts(self):
        """Check for alert conditions"""
        metrics = self.get_metrics()

        if metrics.current_drawdown > self.max_dd_critical:
            alert = f"CRITICAL: Drawdown {metrics.current_drawdown:.1%} exceeds limit {self.max_dd_critical:.1%}"
            self.alerts.append(alert)
            self._send_notification(alert, severity='CRITICAL')

        elif metrics.current_drawdown > self.max_dd_warning:
            alert = f"WARNING: Drawdown {metrics.current_drawdown:.1%} approaches limit {self.max_dd_warning:.1%}"
            self.alerts.append(alert)
            self._send_notification(alert, severity='WARNING')

        if metrics.consecutive_losses >= self.max_consecutive_losses:
            alert = f"ALERT: {metrics.consecutive_losses} consecutive losses"
            self.alerts.append(alert)
            self._send_notification(alert, severity='ALERT')

    def get_metrics(self) -> PerformanceMetrics:
        """Calculate current performance metrics"""
        if not self.trades:
            return PerformanceMetrics(
                total_return=0.0, current_drawdown=0.0, max_drawdown=0.0,
                win_rate=0.0, sharpe_ratio=0.0, consecutive_wins=0,
                consecutive_losses=0, consecutive_loss_streak=0,
                trade_count=0, winning_trades=0, losing_trades=0,
            )

        total_return = (self.current_capital - self.initial_capital) / self.initial_capital

        equity_array = np.array(self.equity_history)
        peak_equity = np.maximum.accumulate(equity_array)
        drawdown = (equity_array - peak_equity) / peak_equity
        current_drawdown = drawdown[-1]
        max_drawdown = np.min(drawdown)

        returns = np.array([t['return'] for t in self.trades])
        wins = np.sum(returns > 0)
        losses = np.sum(returns < 0)
        win_rate = wins / len(returns) if len(returns) > 0 else 0.0

        sharpe = (np.mean(returns) / (np.std(returns) + 1e-8) * np.sqrt(252)) if len(returns) > 1 else 0.0

        consecutive_wins = 0
        consecutive_losses = 0
        consecutive_loss_streak = 0

        for trade in reversed(self.trades):
            if trade['win']:
                consecutive_wins += 1
                consecutive_losses = 0
            else:
                consecutive_losses += 1
                consecutive_wins = 0
                consecutive_loss_streak = max(consecutive_loss_streak, consecutive_losses)

        return PerformanceMetrics(
            total_return=total_return,
            current_drawdown=current_drawdown,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            sharpe_ratio=sharpe,
            consecutive_wins=consecutive_wins,
            consecutive_losses=consecutive_losses,
            consecutive_loss_streak=consecutive_loss_streak,
            trade_count=len(self.trades),
            winning_trades=int(wins),
            losing_trades=int(losses),
        )

    def _notify_trade(self, trade: Dict):
        """Send trade notification"""
        msg = (
            f"📊 Trade: {trade['symbol']} {trade['type']}\n"
            f"Return: {trade['return']:+.2%} | Confidence: {trade['confidence']:.2f}\n"
            f"Equity: ${trade['equity_after']:,.2f}"
        )
        msg = f"✅ WIN\n{msg}" if trade['win'] else f"❌ LOSS\n{msg}"
        self._send_notification(msg, severity='INFO')

    def _send_notification(self, message: str, severity: str = 'INFO'):
        """Send notification via Telegram/Slack"""
        if self.telegram_token:
            logger.info(f"[TELEGRAM] {severity} - {message}")
        if self.slack_webhook:
            logger.info(f"[SLACK] {severity} - {message}")
        logger.info(f"[{severity}] {message}")

    def get_equity_curve(self) -> pd.DataFrame:
        """Return equity curve as DataFrame"""
        return pd.DataFrame({
            'timestamp': self.timestamps,
            'equity': self.equity_history,
            'return': np.concatenate([[0], np.diff(self.equity_history) / self.equity_history[:-1]])
        })

    def get_trades_dataframe(self) -> pd.DataFrame:
        """Return trades as DataFrame"""
        return pd.DataFrame(self.trades) if self.trades else pd.DataFrame()

    def get_summary(self) -> Dict:
        """Get performance summary"""
        metrics = self.get_metrics()
        return {
            'initial_capital': self.initial_capital,
            'current_capital': self.current_capital,
            'total_return': metrics.total_return,
            'max_drawdown': metrics.max_drawdown,
            'current_drawdown': metrics.current_drawdown,
            'trade_count': metrics.trade_count,
            'win_rate': metrics.win_rate,
            'sharpe_ratio': metrics.sharpe_ratio,
            'consecutive_losses': metrics.consecutive_losses,
            'max_consecutive_loss_streak': metrics.consecutive_loss_streak,
        }

    def reset(self):
        """Reset monitor for new session"""
        self.current_capital = self.initial_capital
        self.equity_history = [self.initial_capital]
        self.trades = []
        self.timestamps = [datetime.now()]
        self.alerts = []
        logger.info("LiveMonitor reset")


class LivePerformanceDashboard:
    """Dashboard for viewing live performance"""

    def __init__(self, monitor: LiveMonitor):
        self.monitor = monitor

    def get_summary_text(self) -> str:
        """Generate text summary for display"""
        summary = self.monitor.get_summary()
        metrics = self.monitor.get_metrics()

        text = f"""
╔════════════════════════════════════════╗
║     AEGIS CBR ENGINE - LIVE STATUS     ║
╚════════════════════════════════════════╝

📈 CAPITAL & RETURNS:
  Initial Capital: ${summary['initial_capital']:,.2f}
  Current Capital: ${summary['current_capital']:,.2f}
  Total Return:    {summary['total_return']:+.2%}

📊 DRAWDOWN:
  Current DD:      {summary['current_drawdown']:.2%}
  Max DD:          {summary['max_drawdown']:.2%}
  Warning Level:   {self.monitor.max_dd_warning:.2%}

🎯 TRADES:
  Total Trades:    {summary['trade_count']}
  Wins:            {metrics.winning_trades}
  Losses:          {metrics.losing_trades}
  Win Rate:        {summary['win_rate']:.1%}

📉 RISK METRICS:
  Sharpe Ratio:    {summary['sharpe_ratio']:.2f}
  Consecutive L:   {summary['consecutive_losses']}
  Max L Streak:    {summary['max_consecutive_loss_streak']}

⏰ Status: RUNNING
"""
        return text

    def print_status(self):
        """Print status to console"""
        print(self.get_summary_text())
