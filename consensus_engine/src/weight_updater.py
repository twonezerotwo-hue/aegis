"""
AEGIS Dynamic Weights Updater

Orchestrates weight updates based on trade outcomes.
- Processes trade records to extract winning/losing phases
- Updates DynamicWeights based on performance
- Triggers regime resets when detected
- Logs weight evolution for analysis
"""
from typing import Dict, List, Optional
from datetime import datetime, timezone
import structlog
import numpy as np

logger = structlog.get_logger(__name__)


class WeightUpdater:
    """
    Manages weight update orchestration.

    Flow:
    1. Trade execution happens
    2. WeightUpdater.process_trade_result() called
    3. Extract winning/losing phases from trade record
    4. Update weights via DynamicWeights.update_from_trade()
    5. Log changes and metrics
    """

    def __init__(self, dynamic_weights_manager):
        """
        Args:
            dynamic_weights_manager: DynamicWeights instance to manage
        """
        self.manager = dynamic_weights_manager
        self.trade_count = 0
        self.update_history: List[Dict] = []
        self.last_regime_check: Optional[datetime] = None

        logger.info("weight_updater_initialized")

    def process_trade_result(
        self,
        winning_phases: List[int],
        losing_phases: List[int],
        pnl: float,
        trade_id: Optional[str] = None,
    ) -> Dict:
        """
        Process a single trade result and update weights.

        Args:
            winning_phases: Phase IDs (1-7) that contributed to profit
            losing_phases: Phase IDs (1-7) that contributed to loss
            pnl: Trade profit/loss amount
            trade_id: Optional trade identifier for tracking

        Returns:
            Update summary with old/new weights and changes
        """
        # Capture current state
        old_weights = self.manager.get_weights().copy()
        old_array = self.manager.get_weight_array().copy()

        # Update weights based on trade result
        self.manager.update_from_trade(winning_phases, losing_phases, pnl)

        # Capture new state
        new_weights = self.manager.get_weights()
        new_array = self.manager.get_weight_array()

        # Calculate weight deltas
        weight_changes = {}
        for phase_name in new_weights.keys():
            old_val = old_weights[phase_name]
            new_val = new_weights[phase_name]
            delta = new_val - old_val
            if abs(delta) > 0.001:
                weight_changes[phase_name] = {
                    "old": round(old_val, 4),
                    "new": round(new_val, 4),
                    "delta": round(delta, 4),
                    "pct_change": round((delta / old_val * 100) if old_val > 0 else 0, 2),
                }

        # Create update record
        update_record = {
            "trade_id": trade_id or f"trade_{self.trade_count}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trade_count": self.trade_count,
            "regime": self.manager.current_regime,
            "pnl": pnl,
            "winning_phases": winning_phases,
            "losing_phases": losing_phases,
            "weight_changes": weight_changes,
            "new_weights": {k: round(v, 4) for k, v in new_weights.items()},
            "max_phase": max(
                new_weights.items(), key=lambda x: x[1]
            )[0],
            "max_weight": round(max(new_weights.values()), 4),
            "concentration_ratio": round(max(new_weights.values()) / min(new_weights.values()), 2),
        }

        self.update_history.append(update_record)
        self.trade_count += 1

        logger.info(
            "weight_update_processed",
            trade_id=trade_id,
            trade_num=self.trade_count,
            pnl=pnl,
            regime=self.manager.current_regime,
            phases_changed=len(weight_changes),
            max_phase_weight=update_record["max_weight"],
        )

        return update_record

    def get_weight_evolution(self, lookback: int = 50) -> Dict:
        """
        Analyze weight evolution over recent trades.

        Args:
            lookback: Number of recent updates to analyze

        Returns:
            Evolution metrics including stability, drift, trend
        """
        recent_updates = self.update_history[-lookback:]

        if not recent_updates:
            return {"trades_analyzed": 0, "evolution": "insufficient_data"}

        # Extract weight time series for each phase
        phase_timeseries = {}
        for phase_name in self.manager.PHASES:
            weights = []
            for update in recent_updates:
                if phase_name in update["new_weights"]:
                    weights.append(update["new_weights"][phase_name])
            if weights:
                phase_timeseries[phase_name] = {
                    "current": weights[-1],
                    "min": round(min(weights), 4),
                    "max": round(max(weights), 4),
                    "mean": round(np.mean(weights), 4),
                    "std": round(np.std(weights), 4),
                    "trend": "increasing" if weights[-1] > weights[0] else "decreasing",
                }

        # Overall concentration ratio trend
        concentration_ratios = [u["concentration_ratio"] for u in recent_updates]

        return {
            "trades_analyzed": len(recent_updates),
            "time_period": f"{recent_updates[0]['timestamp']} → {recent_updates[-1]['timestamp']}",
            "phase_evolution": phase_timeseries,
            "concentration_ratio": {
                "current": round(concentration_ratios[-1], 2),
                "mean": round(np.mean(concentration_ratios), 2),
                "trend": "increasing" if concentration_ratios[-1] > concentration_ratios[0] else "stable",
            },
            "regime_distribution": self._calculate_regime_distribution(recent_updates),
        }

    def _calculate_regime_distribution(self, updates: List[Dict]) -> Dict:
        """Count regimes in update history."""
        regime_counts = {}
        for update in updates:
            regime = update["regime"]
            regime_counts[regime] = regime_counts.get(regime, 0) + 1

        return regime_counts

    def get_phase_reliability(self) -> Dict[int, Dict]:
        """
        Analyze which phases are most reliable (correlate with wins).

        Returns:
            Per-phase win rate, avg PnL contribution, reliability score
        """
        phase_wins = {i: 0 for i in range(1, 8)}
        phase_losses = {i: 0 for i in range(1, 8)}
        phase_pnl = {i: 0.0 for i in range(1, 8)}

        for update in self.update_history:
            pnl = update["pnl"]
            if pnl > 0:
                for phase_id in update["winning_phases"]:
                    phase_wins[phase_id] += 1
                    phase_pnl[phase_id] += pnl
            else:
                for phase_id in update["losing_phases"]:
                    phase_losses[phase_id] += 1
                    phase_pnl[phase_id] += pnl

        reliability_report = {}
        for phase_id in range(1, 8):
            total_appearances = phase_wins[phase_id] + phase_losses[phase_id]
            if total_appearances > 0:
                win_rate = phase_wins[phase_id] / total_appearances
                reliability_score = (win_rate * 2 - 1) * 100  # -100 to +100
                reliability_report[phase_id] = {
                    "appearances": total_appearances,
                    "wins": phase_wins[phase_id],
                    "losses": phase_losses[phase_id],
                    "win_rate": round(win_rate, 3),
                    "avg_pnl_contribution": round(phase_pnl[phase_id] / total_appearances, 2),
                    "reliability_score": round(reliability_score, 1),
                }

        return reliability_report

    def recommend_phase_adjustments(self) -> Dict:
        """
        Based on reliability, recommend which phases to boost/reduce.

        Returns:
            Recommendations keyed by phase_id
        """
        reliability = self.get_phase_reliability()
        recommendations = {}

        for phase_id, metrics in reliability.items():
            reliability_score = metrics["reliability_score"]

            if reliability_score > 50:
                recommendation = "increase"
                reason = f"High reliability ({metrics['win_rate']:.1%} wins)"
            elif reliability_score < -50:
                recommendation = "decrease"
                reason = f"Low reliability ({metrics['win_rate']:.1%} wins)"
            else:
                recommendation = "maintain"
                reason = "Neutral reliability"

            recommendations[phase_id] = {
                "action": recommendation,
                "reason": reason,
                "reliability_score": reliability_score,
            }

        return recommendations

    def reset_on_regime_shift(self, new_regime: str) -> Dict:
        """
        Reset weights to regime baseline on shift detection.

        Args:
            new_regime: Regime name to reset to

        Returns:
            Reset details with old vs new weights
        """
        old_weights = self.manager.get_weights().copy()

        # Reset via regime switch
        self.manager.set_regime(new_regime)

        new_weights = self.manager.get_weights()

        reset_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "new_regime": new_regime,
            "trades_at_reset": self.trade_count,
            "old_weights": {k: round(v, 4) for k, v in old_weights.items()},
            "new_weights": {k: round(v, 4) for k, v in new_weights.items()},
        }

        logger.info(
            "weight_updater_regime_reset",
            new_regime=new_regime,
            trade_count=self.trade_count,
        )

        return reset_record

    def get_update_summary(self) -> Dict:
        """Get comprehensive update summary."""
        return {
            "total_trades_processed": self.trade_count,
            "updates_recorded": len(self.update_history),
            "current_weights": self.manager.get_weights(),
            "current_regime": self.manager.current_regime,
            "phase_reliability": self.get_phase_reliability(),
            "recommendations": self.recommend_phase_adjustments(),
            "evolution": self.get_weight_evolution(),
        }
