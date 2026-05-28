"""
AEGIS CBR Engine - FAZ 6: Paper Trading Bridge
Integration layer between CBR decision engine and paper/live trading
"""

import asyncio
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class SignalEvent:
    """CBR trading signal event"""
    timestamp: datetime
    signal_type: str  # 'LONG', 'SHORT', 'CLOSE', 'SKIP'
    confidence: float
    position_size: float
    fingerprint_id: int
    similarity_score: float
    price: float
    market_type: str  # 'DIP', 'PEAK', 'BREAKOUT', 'REJECTION'
    reasoning: Dict


@dataclass
class ExecutionEvent:
    """Order execution event"""
    trade_id: str
    timestamp: datetime
    signal_id: str
    executed_price: float
    executed_quantity: float
    status: str  # 'PENDING', 'EXECUTED', 'REJECTED', 'PARTIAL'
    slippage_bps: float
    order_type: str  # 'MARKET', 'LIMIT'
    error: Optional[str] = None


class PaperTradingBridge:
    """
    Bridge between CBR engine and paper/live trading system.

    Responsibilities:
    1. Receive CBR signals
    2. Validate signals against compliance rules
    3. Route to paper trading or live execution
    4. Track execution and update monitor
    5. Handle errors and retries
    """

    def __init__(
        self,
        cbr_engine,  # CBR decision maker instance
        paper_trader,  # Paper trading simulator
        live_monitor,  # Live performance monitor
        max_retries: int = 3,
        timeout_ms: float = 5000,
    ):
        """
        Args:
            cbr_engine: CBR decision making engine
            paper_trader: Paper trading simulator
            live_monitor: Live performance monitor
            max_retries: Max retries on failure
            timeout_ms: Timeout for async operations
        """
        self.cbr_engine = cbr_engine
        self.paper_trader = paper_trader
        self.live_monitor = live_monitor

        self.max_retries = max_retries
        self.timeout_ms = timeout_ms

        self.active_signals = {}  # signal_id -> SignalEvent
        self.executed_trades = {}  # trade_id -> ExecutionEvent
        self.signal_callbacks: List[Callable] = []

        logger.info("PaperTradingBridge initialized")

    def register_signal_callback(self, callback: Callable[[SignalEvent], None]):
        """Register callback for signal events"""
        self.signal_callbacks.append(callback)
        logger.info(f"Signal callback registered: {callback.__name__}")

    async def process_fingerprint(self, fingerprint: Dict, current_price: float) -> Optional[SignalEvent]:
        """
        Process fingerprint through CBR and generate trading signal.

        Args:
            fingerprint: Market fingerprint from FAZ 1
            current_price: Current BTC/asset price

        Returns:
            SignalEvent or None if no signal
        """
        try:
            # Step 1: Search for similar cases
            similar_cases = await self._get_similar_cases(fingerprint)

            if not similar_cases:
                logger.debug("No similar cases found")
                return None

            # Step 2: Calculate case statistics
            case_stats = self._calculate_case_statistics(similar_cases)

            # Step 3: Make CBR decision
            decision = await self._make_cbr_decision(fingerprint, case_stats, current_price)

            if decision['action'] == 'SKIP':
                logger.debug(f"CBR decision: SKIP (confidence: {decision['confidence']:.2f})")
                return None

            # Step 4: Validate against compliance
            is_valid = await self._validate_compliance(decision)

            if not is_valid:
                logger.warning("Decision failed compliance check")
                return None

            # Step 5: Create signal event
            signal = SignalEvent(
                timestamp=datetime.now(),
                signal_type=decision['action'],
                confidence=decision['confidence'],
                position_size=decision['position_size'],
                fingerprint_id=fingerprint.get('id', -1),
                similarity_score=case_stats.get('mean_similarity', 0.0),
                price=current_price,
                market_type=fingerprint.get('market_type', 'UNKNOWN'),
                reasoning=decision.get('reasoning', {}),
            )

            self.active_signals[id(signal)] = signal

            # Notify callbacks
            for callback in self.signal_callbacks:
                try:
                    callback(signal)
                except Exception as e:
                    logger.error(f"Callback error: {e}")

            logger.info(
                f"Signal generated: {signal.signal_type} "
                f"(confidence: {signal.confidence:.2f}, size: {signal.position_size:.4f})"
            )

            return signal

        except Exception as e:
            logger.error(f"Error processing fingerprint: {e}")
            return None

    async def _get_similar_cases(self, fingerprint: Dict) -> List[Dict]:
        """Get similar historical cases"""
        # In production, would call similarity search engine
        # For now, return mock data
        return [
            {'forward_return': 0.02, 'similarity': 0.75, 'outcome': 'WIN'},
            {'forward_return': 0.015, 'similarity': 0.70, 'outcome': 'WIN'},
            {'forward_return': 0.01, 'similarity': 0.65, 'outcome': 'WIN'},
        ]

    def _calculate_case_statistics(self, cases: List[Dict]) -> Dict:
        """Calculate statistics from similar cases"""
        returns = [c.get('forward_return', 0) for c in cases]
        similarities = [c.get('similarity', 0) for c in cases]

        return {
            'sample_count': len(cases),
            'mean_similarity': sum(similarities) / len(similarities) if similarities else 0,
            'avg_return': sum(returns) / len(returns) if returns else 0,
            'win_rate': sum(1 for r in returns if r > 0) / len(returns) if returns else 0,
        }

    async def _make_cbr_decision(
        self,
        fingerprint: Dict,
        case_stats: Dict,
        current_price: float
    ) -> Dict:
        """Make CBR trading decision"""
        # In production, would call ProbabilisticDecisionMaker
        # For now, mock decision

        if case_stats.get('win_rate', 0) > 0.6 and case_stats.get('mean_similarity', 0) > 0.70:
            return {
                'action': 'LONG',
                'confidence': 0.75,
                'position_size': 0.03,
                'reasoning': case_stats,
            }
        else:
            return {
                'action': 'SKIP',
                'confidence': 0.0,
                'position_size': 0.0,
                'reasoning': case_stats,
            }

    async def _validate_compliance(self, decision: Dict) -> bool:
        """Validate decision against compliance rules"""
        # Check position size
        if decision['position_size'] > 0.10:
            logger.warning(f"Position size {decision['position_size']:.4f} exceeds max")
            return False

        # Check confidence
        if decision['confidence'] < 0.50:
            logger.debug(f"Confidence {decision['confidence']:.2f} below threshold")
            return False

        return True

    async def execute_signal(
        self,
        signal: SignalEvent,
        execution_price: Optional[float] = None,
    ) -> ExecutionEvent:
        """
        Execute trading signal through paper/live trader.

        Args:
            signal: SignalEvent to execute
            execution_price: Override execution price (for testing)

        Returns:
            ExecutionEvent with results
        """
        trade_id = f"TRADE_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        retry_count = 0

        while retry_count < self.max_retries:
            try:
                exec_price = execution_price or signal.price

                # Execute through paper trader
                result = await self._execute_paper_trade(
                    trade_id=trade_id,
                    signal_type=signal.signal_type,
                    quantity=signal.position_size,
                    price=exec_price,
                )

                execution = ExecutionEvent(
                    trade_id=trade_id,
                    timestamp=datetime.now(),
                    signal_id=str(id(signal)),
                    executed_price=result.get('executed_price', exec_price),
                    executed_quantity=result.get('executed_quantity', signal.position_size),
                    status=result.get('status', 'EXECUTED'),
                    slippage_bps=result.get('slippage_bps', 0),
                    order_type='MARKET',
                )

                self.executed_trades[trade_id] = execution

                # Update live monitor
                trade_return = result.get('return', 0)
                self.live_monitor.record_trade(
                    trade_result=trade_return,
                    confidence=signal.confidence,
                    position_size=signal.position_size,
                    symbol='BTC/USD',
                    notes=f"CBR: {signal.market_type}",
                )

                logger.info(f"Trade executed: {trade_id} | Status: {execution.status}")
                return execution

            except Exception as e:
                retry_count += 1
                logger.warning(f"Execution failed (retry {retry_count}/{self.max_retries}): {e}")

                if retry_count >= self.max_retries:
                    return ExecutionEvent(
                        trade_id=trade_id,
                        timestamp=datetime.now(),
                        signal_id=str(id(signal)),
                        executed_price=signal.price,
                        executed_quantity=0,
                        status='REJECTED',
                        slippage_bps=0,
                        order_type='MARKET',
                        error=str(e),
                    )

                await asyncio.sleep(0.1 * retry_count)

    async def _execute_paper_trade(
        self,
        trade_id: str,
        signal_type: str,
        quantity: float,
        price: float,
    ) -> Dict:
        """Execute trade through paper trading system"""
        # Mock implementation
        return {
            'trade_id': trade_id,
            'executed_price': price * (1 + 0.0001),  # 1bps slippage
            'executed_quantity': quantity,
            'status': 'EXECUTED',
            'slippage_bps': 1,
            'return': 0.02,  # Mock +2% return
        }

    def get_active_signals(self) -> Dict:
        """Get all active signals"""
        return self.active_signals.copy()

    def get_executed_trades(self) -> Dict:
        """Get all executed trades"""
        return self.executed_trades.copy()

    def close_position(self, trade_id: str, exit_price: float) -> ExecutionEvent:
        """Close an open position"""
        if trade_id not in self.executed_trades:
            logger.warning(f"Trade {trade_id} not found")
            return None

        # Mock close execution
        close_event = ExecutionEvent(
            trade_id=f"{trade_id}_CLOSE",
            timestamp=datetime.now(),
            signal_id=trade_id,
            executed_price=exit_price,
            executed_quantity=0,
            status='EXECUTED',
            slippage_bps=1,
            order_type='MARKET',
        )

        logger.info(f"Position closed: {trade_id}")
        return close_event

    def get_status(self) -> Dict:
        """Get bridge status"""
        return {
            'active_signals': len(self.active_signals),
            'executed_trades': len(self.executed_trades),
            'connected': True,
        }
