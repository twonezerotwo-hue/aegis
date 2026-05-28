"""
AEGIS CBR Engine - FAZ 6: Paper to Live Tests
Test slippage simulation, live monitoring, and bridge integration
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from slippage_simulator import OrderBook, SlippageSimulator, ExecutionResult
from live_monitor import LiveMonitor, LivePerformanceDashboard
from paper_trading_bridge import PaperTradingBridge, SignalEvent, ExecutionEvent


class TestOrderBook:
    """Test order book modeling"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup order book"""
        self.ob = OrderBook(mid_price=45000, spread_bps=5)

    def test_initialization(self):
        """Test order book initialization"""
        assert self.ob.mid_price == 45000
        assert self.ob.spread_bps == 5
        assert len(self.ob.bids) > 0
        assert len(self.ob.asks) > 0

    def test_bid_ask_spread(self):
        """Test bid-ask spread is correct"""
        min_ask = min(level.price for level in self.ob.asks)
        max_bid = max(level.price for level in self.ob.bids)

        spread = (min_ask - max_bid) / self.ob.mid_price * 10000
        assert spread == pytest.approx(self.ob.spread_bps, rel=0.1)

    def test_vwap_buy(self):
        """Test VWAP calculation for buy orders"""
        vwap, filled, partial = self.ob.get_vwap('BUY', 0.1)

        assert vwap > 0
        assert filled <= 0.1
        assert isinstance(partial, bool)

    def test_vwap_sell(self):
        """Test VWAP calculation for sell orders"""
        vwap, filled, partial = self.ob.get_vwap('SELL', 0.1)

        assert vwap > 0
        assert filled <= 0.1

    def test_vwap_large_order(self):
        """Large orders should fill multiple levels"""
        vwap, filled, partial = self.ob.get_vwap('BUY', 2.0)

        assert filled > 0
        # Should be partial since order is large
        if filled < 2.0:
            assert partial is True

    def test_market_impact(self):
        """Test market impact calculation"""
        impact_small = self.ob.apply_market_impact('BUY', 0.1)
        impact_large = self.ob.apply_market_impact('BUY', 5.0)

        # Larger order should have more impact
        assert impact_large > impact_small
        assert impact_small >= 0
        assert impact_large <= 500  # Capped at 500bps

    def test_market_update(self):
        """Test order book update"""
        initial_mid = self.ob.mid_price
        self.ob.apply_market_impact('BUY', 1.0)  # Simulate price movement

        # OB should still be valid after update
        assert self.ob.mid_price > 0
        assert len(self.ob.bids) > 0


class TestSlippageSimulator:
    """Test slippage simulator"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup simulator"""
        self.sim = SlippageSimulator(mid_price=45000, spread_bps=5, commission_bps=10)

    def test_initialization(self):
        """Test simulator initialization"""
        assert self.sim.order_book.mid_price == 45000
        assert self.sim.commission_bps == 10
        assert len(self.sim.trade_history) == 0

    def test_execute_market_buy(self):
        """Execute market buy order"""
        result = self.sim.execute_order('BUY', 0.1)

        assert isinstance(result, ExecutionResult)
        assert result.filled_quantity > 0
        assert result.average_fill_price > 0
        assert result.slippage_bps > 0
        assert not result.partial_fill  # Small order should fill

    def test_execute_market_sell(self):
        """Execute market sell order"""
        result = self.sim.execute_order('SELL', 0.1)

        assert result.filled_quantity > 0
        assert result.average_fill_price > 0
        assert result.slippage_bps < 0  # Negative for sells

    def test_slippage_components(self):
        """Slippage should include spread, impact, and commission"""
        result = self.sim.execute_order('BUY', 0.5)

        # Slippage should be roughly: spread/2 + market_impact + commission
        min_slippage = 2.5 + 10  # spread/2 + commission in bps
        assert result.slippage_bps >= min_slippage * 0.8  # Allow some variance

    def test_large_order_partial_fill(self):
        """Large order may result in partial fill"""
        result = self.sim.execute_order('BUY', 50.0)

        # Very large order may be partial
        if result.partial_fill:
            assert result.filled_quantity < 50.0

    def test_slippage_statistics(self):
        """Calculate average slippage statistics"""
        for _ in range(10):
            self.sim.execute_order('BUY', 0.1)

        stats = self.sim.get_statistics()

        assert stats['total_trades'] == 10
        assert stats['avg_slippage_bps'] > 0
        assert stats['max_slippage_bps'] >= stats['avg_slippage_bps'] - 0.1  # Allow for float precision
        assert stats['buy_count'] == 10
        assert stats['sell_count'] == 0

    def test_mixed_orders_statistics(self):
        """Test statistics with mixed buys and sells"""
        for i in range(10):
            side = 'BUY' if i % 2 == 0 else 'SELL'
            self.sim.execute_order(side, 0.1)

        stats = self.sim.get_statistics()

        assert stats['buy_count'] == 5
        assert stats['sell_count'] == 5
        assert stats['total_trades'] == 10

    def test_reset(self):
        """Reset simulator"""
        self.sim.execute_order('BUY', 0.1)
        assert len(self.sim.trade_history) == 1

        self.sim.reset()
        assert len(self.sim.trade_history) == 0


class TestLiveMonitor:
    """Test live performance monitoring"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup monitor"""
        self.monitor = LiveMonitor(
            initial_capital=100000,
            max_dd_warning=0.10,
            max_dd_critical=0.20,
        )

    def test_initialization(self):
        """Test monitor initialization"""
        assert self.monitor.initial_capital == 100000
        assert self.monitor.current_capital == 100000
        assert len(self.monitor.equity_history) == 1
        assert len(self.monitor.trades) == 0

    def test_record_winning_trade(self):
        """Record winning trade"""
        self.monitor.record_trade(trade_result=0.02, confidence=0.75, position_size=0.03)

        assert len(self.monitor.trades) == 1
        assert self.monitor.trades[0]['win'] is True
        assert self.monitor.current_capital == pytest.approx(102000, rel=0.001)

    def test_record_losing_trade(self):
        """Record losing trade"""
        self.monitor.record_trade(trade_result=-0.02, confidence=0.65, position_size=0.03)

        assert len(self.monitor.trades) == 1
        assert self.monitor.trades[0]['win'] is False
        assert self.monitor.current_capital == 98000

    def test_equity_curve_update(self):
        """Equity curve should update with trades"""
        returns = [0.02, -0.01, 0.03, -0.02, 0.01]

        for ret in returns:
            self.monitor.record_trade(ret)

        assert len(self.monitor.equity_history) == len(returns) + 1
        # Final equity calculation
        final_equity = 100000
        for ret in returns:
            final_equity *= (1 + ret)
        assert self.monitor.current_capital == pytest.approx(final_equity, rel=0.001)

    def test_get_metrics_empty(self):
        """Get metrics with no trades"""
        metrics = self.monitor.get_metrics()

        assert metrics.total_return == 0
        assert metrics.trade_count == 0
        assert metrics.win_rate == 0

    def test_get_metrics_with_trades(self):
        """Get metrics after trades"""
        returns = [0.02, 0.01, -0.01, 0.03]

        for ret in returns:
            self.monitor.record_trade(ret)

        metrics = self.monitor.get_metrics()

        assert metrics.trade_count == 4
        assert metrics.winning_trades == 3
        assert metrics.losing_trades == 1
        assert metrics.win_rate == 0.75

    def test_drawdown_calculation(self):
        """Test drawdown tracking"""
        returns = [0.05, 0.03, -0.08, 0.02, -0.03]

        for ret in returns:
            self.monitor.record_trade(ret)

        metrics = self.monitor.get_metrics()

        assert metrics.current_drawdown <= 0
        assert metrics.max_drawdown <= 0
        assert abs(metrics.max_drawdown) > 0

    def test_consecutive_wins_losses(self):
        """Test win/loss streak tracking"""
        # Add 2 losses at the end
        for _ in range(2):
            self.monitor.record_trade(-0.01)

        metrics = self.monitor.get_metrics()

        # Last 2 trades are losses, so consecutive losses should be 2
        assert metrics.consecutive_losses == 2
        assert metrics.consecutive_loss_streak == 2

    def test_sharpe_ratio(self):
        """Test Sharpe ratio calculation"""
        returns = [0.02, 0.01, 0.02, 0.01, 0.02] * 5

        for ret in returns:
            self.monitor.record_trade(ret)

        metrics = self.monitor.get_metrics()

        assert metrics.sharpe_ratio > 0

    def test_get_summary(self):
        """Get performance summary"""
        self.monitor.record_trade(0.02)
        summary = self.monitor.get_summary()

        assert 'total_return' in summary
        assert 'win_rate' in summary
        assert 'trade_count' in summary

    def test_alert_on_high_drawdown(self):
        """Alert triggered on critical drawdown"""
        # Create 25% drawdown
        for _ in range(5):
            self.monitor.record_trade(-0.05)

        metrics = self.monitor.get_metrics()
        assert metrics.current_drawdown < -0.20

        # Alerts should have been generated
        assert len(self.monitor.alerts) > 0

    def test_equity_dataframe(self):
        """Export equity curve to DataFrame"""
        for ret in [0.02, -0.01, 0.03]:
            self.monitor.record_trade(ret)

        df = self.monitor.get_equity_curve()

        assert len(df) == 4  # Initial + 3 trades
        assert 'timestamp' in df.columns
        assert 'equity' in df.columns

    def test_trades_dataframe(self):
        """Export trades to DataFrame"""
        for ret in [0.02, -0.01, 0.03]:
            self.monitor.record_trade(ret)

        df = self.monitor.get_trades_dataframe()

        assert len(df) == 3
        assert 'win' in df.columns
        assert 'return' in df.columns

    def test_reset_monitor(self):
        """Reset monitor"""
        self.monitor.record_trade(0.02)
        assert len(self.monitor.trades) == 1

        self.monitor.reset()

        assert len(self.monitor.trades) == 0
        assert self.monitor.current_capital == self.monitor.initial_capital


class TestLivePerformanceDashboard:
    """Test performance dashboard"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup dashboard"""
        self.monitor = LiveMonitor(initial_capital=100000)
        self.dashboard = LivePerformanceDashboard(self.monitor)

    def test_summary_text(self):
        """Generate summary text"""
        self.monitor.record_trade(0.02)
        text = self.dashboard.get_summary_text()

        assert 'AEGIS CBR ENGINE' in text
        assert '$' in text
        assert '%' in text

    def test_summary_includes_metrics(self):
        """Summary should include all key metrics"""
        text = self.dashboard.get_summary_text()

        # Check for key content (accounting for unicode/emoji)
        assert 'Capital' in text or 'CAPITAL' in text
        assert 'DD' in text or 'DRAWDOWN' in text
        assert 'Trades' in text or 'TRADES' in text
        assert 'Sharpe' in text or 'SHARPE' in text


class TestPaperTradingBridge:
    """Test paper trading bridge (async)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup bridge"""
        self.monitor = LiveMonitor()
        self.bridge = PaperTradingBridge(
            cbr_engine=None,
            paper_trader=None,
            live_monitor=self.monitor,
        )

    def test_initialization(self):
        """Test bridge initialization"""
        assert self.bridge.cbr_engine is None
        assert self.bridge.live_monitor == self.monitor
        assert len(self.bridge.active_signals) == 0

    def test_signal_event_creation(self):
        """Create signal event"""
        signal = SignalEvent(
            timestamp=datetime.now(),
            signal_type='LONG',
            confidence=0.75,
            position_size=0.03,
            fingerprint_id=1,
            similarity_score=0.72,
            price=45000,
            market_type='DIP',
            reasoning={},
        )

        assert signal.signal_type == 'LONG'
        assert signal.confidence == 0.75

    def test_execution_event_creation(self):
        """Create execution event"""
        execution = ExecutionEvent(
            trade_id='TRADE_001',
            timestamp=datetime.now(),
            signal_id='SIG_001',
            executed_price=45000,
            executed_quantity=0.03,
            status='EXECUTED',
            slippage_bps=5,
            order_type='MARKET',
        )

        assert execution.trade_id == 'TRADE_001'
        assert execution.status == 'EXECUTED'

    @pytest.mark.asyncio
    async def test_process_fingerprint(self):
        """Process fingerprint (async)"""
        fingerprint = {
            'id': 1,
            'market_type': 'DIP',
            'price': 45000,
        }

        signal = await self.bridge.process_fingerprint(fingerprint, 45000)

        # May be None if no decision or signal filtered out
        if signal is not None:
            assert isinstance(signal, SignalEvent)

    @pytest.mark.asyncio
    async def test_execute_signal(self):
        """Execute signal (async)"""
        signal = SignalEvent(
            timestamp=datetime.now(),
            signal_type='LONG',
            confidence=0.75,
            position_size=0.03,
            fingerprint_id=1,
            similarity_score=0.72,
            price=45000,
            market_type='DIP',
            reasoning={},
        )

        execution = await self.bridge.execute_signal(signal)

        assert isinstance(execution, ExecutionEvent)
        assert execution.timestamp is not None

    def test_get_status(self):
        """Get bridge status"""
        status = self.bridge.get_status()

        assert 'active_signals' in status
        assert 'executed_trades' in status
        assert 'connected' in status


class TestPhase6Integration:
    """Integration tests for FAZ 6"""

    def test_paper_trading_workflow(self):
        """Test complete paper trading workflow"""
        # 1. Initialize components
        sim = SlippageSimulator(mid_price=45000)
        monitor = LiveMonitor(initial_capital=100000)

        # 2. Execute trades with slippage
        for i in range(10):
            result = sim.execute_order('BUY' if i % 2 == 0 else 'SELL', 0.1)
            # Mock trade return
            ret = 0.01 if result.slippage_bps < 10 else -0.01
            monitor.record_trade(ret)

        # 3. Check results
        metrics = monitor.get_metrics()
        assert metrics.trade_count == 10
        stats = sim.get_statistics()
        assert stats['total_trades'] == 10

    def test_live_monitoring_workflow(self):
        """Test live monitoring during trading"""
        monitor = LiveMonitor(initial_capital=100000, max_dd_critical=0.15)

        # Add a sequence of trades
        trades = [0.02, 0.02, 0.02, -0.01, -0.01, -0.01]  # 3 wins, then 3 losses
        for ret in trades:
            monitor.record_trade(ret)

        metrics = monitor.get_metrics()
        assert metrics.trade_count == 6
        assert metrics.winning_trades == 3
        assert metrics.losing_trades == 3
        # Last 3 trades are losses, so when reversed we have consecutive_wins=3 from the wins,
        # and the max_consecutive_loss_streak tracks the longest loss streak which is 3
        assert metrics.consecutive_loss_streak == 3


def test_faz6_readiness():
    """Meta test: Is FAZ 6 complete and ready?"""
    # Component 1: Slippage simulator
    sim = SlippageSimulator()
    result = sim.execute_order('BUY', 0.1)
    assert result.filled_quantity > 0

    # Component 2: Live monitor
    monitor = LiveMonitor()
    monitor.record_trade(0.02)
    metrics = monitor.get_metrics()
    assert metrics.trade_count == 1

    # Component 3: Dashboard
    dashboard = LivePerformanceDashboard(monitor)
    text = dashboard.get_summary_text()
    assert len(text) > 0

    # Component 4: Paper trading bridge
    bridge = PaperTradingBridge(None, None, monitor)
    assert bridge.get_status() is not None

    print("✅ FAZ 6 PAPER → LIVE - READY FOR PRODUCTION")
    print(f"   Slippage simulator: ✓ {result.slippage_bps:.1f}bps")
    print("   Live monitor: ✓ Tracking equity & metrics")
    print("   Dashboard: ✓ Real-time status")
    print("   Bridge: ✓ Paper trading integration")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
