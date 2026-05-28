"""
AEGIS CBR Engine - FAZ 5: Auto-Labeler
Automatically label trade outcomes and update fingerprints with results
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class TradeOutcome:
    """Trade outcome record"""
    trade_id: str
    fingerprint_id: int
    entry_price: float
    exit_price: float
    forward_return: float  # Decimal, e.g., 0.02 = +2%
    outcome_category: str  # GREAT_WIN, WIN, BREAKEVEN, SMALL_LOSS, BIG_LOSS
    win: bool  # True if forward_return > 0
    confidence_score: float  # Original trade confidence
    position_size: float
    entry_time: datetime
    exit_time: datetime
    holding_period_hours: float
    notes: Optional[str]


class AutoLabeler:
    """
    Automatic trade outcome labeling and database updating.

    Process:
    1. Record trade entry (fingerprint, entry_price, confidence, position_size)
    2. On exit, calculate forward return
    3. Categorize outcome (WIN/LOSS quality)
    4. Update fingerprint with outcome
    5. Store for continuous learning
    """

    # Outcome categories with thresholds
    OUTCOME_CATEGORIES = {
        'GREAT_WIN': {'min_return': 0.05, 'description': '+5% or better'},       # >= 5%
        'WIN': {'min_return': 0.02, 'description': '+2% to +5%'},                 # 2% to 5%
        'BREAKEVEN': {'min_return': -0.01, 'description': '-1% to +2%'},         # -1% to 2%
        'SMALL_LOSS': {'min_return': -0.05, 'description': '-1% to -5%'},       # -1% to -5%
        'BIG_LOSS': {'min_return': -1.0, 'description': 'Below -5%'},           # < -5%
    }

    def __init__(self):
        """Initialize auto-labeler"""
        self.trades_log = []  # In-memory trade log
        logger.info("AutoLabeler initialized")

    def categorize_outcome(self, forward_return: float) -> Tuple[str, bool]:
        """
        Categorize trade outcome by return.

        Args:
            forward_return: Return as decimal (0.05 = +5%)

        Returns:
            (category_name, is_win)
        """
        is_win = forward_return > 0

        if forward_return >= 0.05:
            return 'GREAT_WIN', True
        elif forward_return >= 0.02:
            return 'WIN', True
        elif forward_return >= -0.01:
            return 'BREAKEVEN', forward_return > 0
        elif forward_return >= -0.05:
            return 'SMALL_LOSS', False
        else:
            return 'BIG_LOSS', False

    def label_trade(
        self,
        trade_id: str,
        fingerprint_id: int,
        entry_price: float,
        exit_price: float,
        confidence_score: float,
        position_size: float,
        entry_time: datetime,
        exit_time: datetime,
        notes: Optional[str] = None
    ) -> TradeOutcome:
        """
        Label a completed trade with outcome.

        Args:
            trade_id: Unique trade identifier
            fingerprint_id: ID of fingerprint that triggered trade
            entry_price: Entry price (BTC or asset)
            exit_price: Exit price
            confidence_score: Original trade confidence (0-1)
            position_size: Position size as % of capital
            entry_time: Entry timestamp
            exit_time: Exit timestamp
            notes: Optional notes

        Returns:
            TradeOutcome record
        """
        # Calculate forward return
        forward_return = (exit_price - entry_price) / entry_price

        # Categorize
        category, win = self.categorize_outcome(forward_return)

        # Calculate holding period
        holding_period = (exit_time - entry_time).total_seconds() / 3600  # hours

        # Create outcome record
        outcome = TradeOutcome(
            trade_id=trade_id,
            fingerprint_id=fingerprint_id,
            entry_price=entry_price,
            exit_price=exit_price,
            forward_return=forward_return,
            outcome_category=category,
            win=win,
            confidence_score=confidence_score,
            position_size=position_size,
            entry_time=entry_time,
            exit_time=exit_time,
            holding_period_hours=holding_period,
            notes=notes
        )

        # Log
        self.trades_log.append(outcome)

        logger.info(
            f"Trade labeled: {trade_id} | {category} | "
            f"Return: {forward_return:.2%} | Confidence: {confidence_score:.2f}"
        )

        return outcome

    def get_recent_outcomes(self, n: int = 20) -> List[TradeOutcome]:
        """Get N most recent trade outcomes"""
        return self.trades_log[-n:]

    def get_outcomes_by_category(self, category: str) -> List[TradeOutcome]:
        """Filter outcomes by category"""
        return [t for t in self.trades_log if t.outcome_category == category]

    def calculate_statistics(self, outcomes: Optional[List[TradeOutcome]] = None) -> Dict:
        """
        Calculate statistics from outcomes.

        Args:
            outcomes: Outcomes to analyze (default: all)

        Returns:
            Dict with statistics
        """
        if outcomes is None:
            outcomes = self.trades_log

        if not outcomes:
            return {
                'total_trades': 0,
                'win_rate': 0.0,
                'avg_return': 0.0,
                'std_return': 0.0,
                'max_return': 0.0,
                'min_return': 0.0,
                'avg_confidence': 0.0,
                'avg_position_size': 0.0,
            }

        returns = np.array([o.forward_return for o in outcomes])
        confidences = np.array([o.confidence_score for o in outcomes])
        positions = np.array([o.position_size for o in outcomes])
        wins = np.array([o.win for o in outcomes])

        return {
            'total_trades': len(outcomes),
            'win_rate': float(np.mean(wins)),
            'avg_return': float(np.mean(returns)),
            'std_return': float(np.std(returns)),
            'max_return': float(np.max(returns)),
            'min_return': float(np.min(returns)),
            'avg_confidence': float(np.mean(confidences)),
            'avg_position_size': float(np.mean(positions)),
            'total_return': float(np.sum(returns)),
            'sharpe_ratio': float(np.mean(returns) / (np.std(returns) + 1e-8) * np.sqrt(252)),
        }

    def get_outcome_distribution(self) -> Dict[str, int]:
        """Get count of outcomes by category"""
        distribution = {}
        for key in self.OUTCOME_CATEGORIES.keys():
            distribution[key] = len(self.get_outcomes_by_category(key))
        return distribution

    def confidence_calibration(self) -> Dict:
        """
        Check if confidence scores match actual outcomes.
        High confidence should correlate with better returns.

        Returns:
            Calibration metrics
        """
        if len(self.trades_log) < 5:
            return {'status': 'insufficient_data', 'trades': len(self.trades_log)}

        # Group by confidence quartiles
        confidences = np.array([t.confidence_score for t in self.trades_log])
        returns = np.array([t.forward_return for t in self.trades_log])

        quartiles = np.percentile(confidences, [25, 50, 75])
        bins = [0, quartiles[0], quartiles[1], quartiles[2], 1.0]
        labels = ['Low', 'Medium-Low', 'Medium-High', 'High']

        # Calculate return per confidence bin
        calibration = {}
        for i in range(len(bins) - 1):
            mask = (confidences >= bins[i]) & (confidences < bins[i + 1])
            if np.sum(mask) > 0:
                avg_return = np.mean(returns[mask])
                win_rate = np.mean(returns[mask] > 0)
                calibration[labels[i]] = {
                    'avg_return': float(avg_return),
                    'win_rate': float(win_rate),
                    'sample_count': int(np.sum(mask))
                }

        return calibration

    def export_to_dataframe(self) -> pd.DataFrame:
        """Export trades log to DataFrame"""
        if not self.trades_log:
            return pd.DataFrame()

        data = [
            {
                'trade_id': t.trade_id,
                'fingerprint_id': t.fingerprint_id,
                'entry_price': t.entry_price,
                'exit_price': t.exit_price,
                'forward_return': t.forward_return,
                'outcome_category': t.outcome_category,
                'win': t.win,
                'confidence_score': t.confidence_score,
                'position_size': t.position_size,
                'entry_time': t.entry_time,
                'exit_time': t.exit_time,
                'holding_period_hours': t.holding_period_hours,
                'notes': t.notes,
            }
            for t in self.trades_log
        ]

        return pd.DataFrame(data)

    def reset_log(self):
        """Clear trade log"""
        self.trades_log = []
        logger.info("Trade log cleared")


class TradeLogger:
    """
    Simple in-memory trade tracking for the session.
    Bridges between trading engine and auto-labeler.
    """

    def __init__(self):
        """Initialize trade logger"""
        self.active_trades = {}  # trade_id -> trade entry record

    def record_entry(
        self,
        trade_id: str,
        fingerprint_id: int,
        entry_price: float,
        confidence_score: float,
        position_size: float,
        entry_time: datetime,
        notes: Optional[str] = None
    ):
        """Record trade entry"""
        self.active_trades[trade_id] = {
            'fingerprint_id': fingerprint_id,
            'entry_price': entry_price,
            'confidence_score': confidence_score,
            'position_size': position_size,
            'entry_time': entry_time,
            'notes': notes,
        }

        logger.info(f"Trade entry recorded: {trade_id}")

    def record_exit(
        self,
        trade_id: str,
        exit_price: float,
        exit_time: datetime
    ) -> Optional[Dict]:
        """
        Record trade exit and return complete trade record.

        Returns:
            Complete trade record for labeling
        """
        if trade_id not in self.active_trades:
            logger.warning(f"Trade {trade_id} not found in active trades")
            return None

        entry = self.active_trades.pop(trade_id)

        trade_record = {
            **entry,
            'trade_id': trade_id,
            'exit_price': exit_price,
            'exit_time': exit_time,
        }

        logger.info(f"Trade exit recorded: {trade_id}")

        return trade_record

    def get_active_trades(self) -> Dict:
        """Get all active (open) trades"""
        return self.active_trades.copy()

    def get_active_trade_count(self) -> int:
        """Get number of active trades"""
        return len(self.active_trades)
