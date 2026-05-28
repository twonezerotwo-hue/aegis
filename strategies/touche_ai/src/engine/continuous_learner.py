"""
AEGIS Continuous Learning Engine

Extends Phase 1's UnifiedOptimizer with:
- Real-time learning with regime awareness
- Regime shift detection & parameter resets
- Adaptive learning rate based on market conditions
- Weekly periodic optimization (vs every 30 trades)
- Parameter stability validation before deployment

Phase 2: Continuous improvement with safeguards
"""
from typing import Dict, Optional, List
from datetime import datetime, timezone
import numpy as np
import structlog
import sys
import os

# Add parent path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unified_optimizer import UnifiedOptimizer, TradeRecord
from regime_detector import RegimeDetector, MarketRegime
from dynamic_weights import DynamicWeightManager

logger = structlog.get_logger(__name__)


class ContinuousLearner(UnifiedOptimizer):
    """
    Extended UnifiedOptimizer with phase 2 capabilities:
    - Regime-aware learning
    - Dynamic learning rate
    - Parameter stability validation
    - Automatic resets on regime shifts
    """

    def __init__(self, *args, **kwargs):
        """Initialize extended learner."""
        super().__init__(*args, **kwargs)

        # Phase 2 Extensions
        self.regime_detector = RegimeDetector()
        self.weight_manager = DynamicWeightManager()

        # Learning configuration
        self.learning_rate_schedule = "adaptive"  # Can be "fixed", "adaptive", "exponential"
        self.max_weight_concentration = 0.35  # Max weight for any single phase
        self.stability_threshold = 0.05  # Max allowed parameter drift
        self.min_reliable_trades = 50  # Minimum trades before declaring learning stable

        # Phase reliability tracking
        self.phase_reliability: Dict[int, float] = {i: 0.0 for i in range(1, 8)}  # Correlation scores
        self.phase_performance_history: Dict[int, List[float]] = {i: [] for i in range(1, 8)}

        # Regime tracking
        self.current_regime: Optional[MarketRegime] = None
        self.regime_shift_timestamp: Optional[datetime] = None
        self.last_weekly_optimization: Optional[datetime] = None

        # Learning metrics
        self.volatility_estimate = 0.02  # Market volatility estimate
        self.trades_since_regime_shift = 0

        logger.info("continuous_learner_initialized")

    def record_trade(self, trade: TradeRecord) -> None:
        """
        Override parent's record_trade() to add Phase 2 learning hooks.
        """
        # Call parent record_trade (handles Phase 1 learning)
        super().record_trade(trade)

        # ─────────────────────────────────────────────────────
        # PHASE 2: Enhanced learning tracking
        # ─────────────────────────────────────────────────────

        # Track phase reliability (how correlated is each phase with PnL?)
        self._track_phase_reliability(trade)

        # Enforce weight constraints
        self._enforce_weight_constraints()

        # Update learning rate dynamically
        self._update_learning_rate_dynamically()

        # Check for regime shifts
        self._check_regime_shift()

        # Weekly optimization trigger
        self._check_weekly_optimization_trigger()

        self.trades_since_regime_shift += 1

        logger.info(
            "continuous_learning_trade_processed",
            trade_count=len(self.trade_history),
            phase_reliability_avg=round(np.mean(list(self.phase_reliability.values())), 3),
        )

    def _track_phase_reliability(self, trade: TradeRecord) -> None:
        """
        Track how reliable each phase's signal is.
        Phases with consistent PnL correlation are reliable.
        """
        for phase_id in trade.winning_phases:
            # Winning phase: increase reliability
            self.phase_reliability[phase_id] += 0.02
            self.phase_performance_history[phase_id].append(1.0)

        for phase_id in trade.losing_phases:
            # Losing phase: decrease reliability
            self.phase_reliability[phase_id] -= 0.05
            self.phase_performance_history[phase_id].append(-1.0)

        # Keep reliability bounded [-1, 1]
        self.phase_reliability = {
            k: np.clip(v, -1.0, 1.0)
            for k, v in self.phase_reliability.items()
        }

    def _enforce_weight_constraints(self) -> None:
        """
        Prevent extreme weight concentrations.
        - No phase exceeds max_weight_concentration
        - Minimum 5% on each phase
        """
        phases_exceeded = []

        for phase_id, weight in self.weights.items():
            if weight > self.max_weight_concentration:
                excess = weight - self.max_weight_concentration
                self.weights[phase_id] = self.max_weight_concentration
                phases_exceeded.append((phase_id, excess))

            if weight < 0.05:
                self.weights[phase_id] = 0.05

        # Normalize to sum = 1.0
        total_weight = sum(self.weights.values())
        self.weights = {k: v / total_weight for k, v in self.weights.items()}

        if phases_exceeded:
            logger.info(
                "weight_constraints_enforced",
                phases_corrected=len(phases_exceeded),
            )

    def _update_learning_rate_dynamically(self) -> None:
        """
        Adjust learning rate based on market conditions.
        - High volatility: slower learning (0.005)
        - Normal volatility: standard learning (0.01)
        - Low volatility: faster learning (0.015)
        """
        # Estimate volatility from recent PnL
        recent_trades = self.trade_history[-20:] if self.trade_history else []
        if len(recent_trades) > 5:
            pnls = np.array([t.pnl for t in recent_trades])
            self.volatility_estimate = np.std(pnls) / (np.mean(np.abs(pnls)) + 0.001)
        else:
            self.volatility_estimate = 0.02

        # Adjust learning rate
        if self.learning_rate_schedule == "adaptive":
            if self.volatility_estimate > 0.05:
                new_lr = 0.005  # Slow learning in chaos
            elif self.volatility_estimate > 0.02:
                new_lr = 0.010  # Standard
            else:
                new_lr = 0.015  # Fast learning in calm

            old_lr = self.learning_rate
            self.learning_rate = new_lr

            if old_lr != new_lr:
                logger.info(
                    "learning_rate_updated",
                    old_rate=old_lr,
                    new_rate=new_lr,
                    volatility=round(self.volatility_estimate, 4),
                )

    def _check_regime_shift(self) -> None:
        """
        Detect regime shifts and reset parameters accordingly.
        """
        # Call regime detection (would need market data in real implementation)
        # For now, just track regime transitions
        detected_regime = self.regime_detector.get_current_regime()

        if detected_regime and detected_regime.regime_shifted_this_candle:
            old_regime = self.current_regime or "UNKNOWN"
            new_regime = detected_regime.regime

            if self.current_regime != new_regime:
                logger.info(
                    "regime_shift_detected",
                    old_regime=old_regime,
                    new_regime=new_regime.value if new_regime else None,
                )

                # Reset parameters to regime defaults
                self._reset_parameters_for_regime(new_regime)

                # Reset learning counters
                self.weight_manager.reset_learning()
                self.trades_since_regime_shift = 0

                self.current_regime = new_regime

    def _reset_parameters_for_regime(self, new_regime: MarketRegime) -> None:
        """
        Reset phase parameters to defaults for the new regime.
        """
        # Get base weights for new regime
        base_weights = self.weight_manager.get_base_weights(new_regime.value)

        # Reset phase weights toward regime defaults (75% new, 25% current)
        for phase_id, base_weight in base_weights.items():
            if isinstance(phase_id, int) and phase_id <= 7:
                self.weights[phase_id] = (
                    0.75 * base_weight +
                    0.25 * self.weights.get(phase_id, base_weight)
                )

        # Normalize
        total_weight = sum(self.weights.values())
        self.weights = {k: v / total_weight for k, v in self.weights.items()}

        logger.info("parameters_reset_for_regime", regime=new_regime.value)

    def _check_weekly_optimization_trigger(self) -> None:
        """
        Trigger full optimization every 7 days regardless of trade count.
        """
        now = datetime.now(timezone.utc)

        if self.last_weekly_optimization is None:
            # First time
            self.last_weekly_optimization = now
            return

        if (now - self.last_weekly_optimization).days >= 7:
            logger.info("weekly_optimization_triggered")

            # Run optimization with "heavy" setting
            result = self.optimize_periodic(optimization_type="heavy")

            self.last_weekly_optimization = now

            # Validate parameter stability
            self._validate_parameter_stability(result)

    def _validate_parameter_stability(self, optimization_result: Dict) -> None:
        """
        Check if parameters changed excessively after optimization.
        High parameter drift = possible overfitting.
        """
        if not optimization_result or "new_params" not in optimization_result:
            return

        stability_issues = []

        new_params = optimization_result["new_params"]

        for phase_id in range(1, 8):
            if phase_id not in new_params:
                continue

            old_params = self.phase_params.get(phase_id, {})
            new_phase_params = new_params[phase_id]

            for param_name, new_value in new_phase_params.items():
                old_value = old_params.get(param_name)
                if old_value is None:
                    continue

                # Calculate % change
                if isinstance(old_value, (int, float)) and isinstance(new_value, (int, float)):
                    if old_value != 0:
                        pct_change = abs(new_value - old_value) / abs(old_value)
                        if pct_change > 0.2:  # > 20% change
                            stability_issues.append({
                                "phase": phase_id,
                                "param": param_name,
                                "old": old_value,
                                "new": new_value,
                                "pct_change": round(pct_change, 3),
                            })

        if stability_issues:
            logger.warning(
                "parameter_stability_warnings",
                issues_count=len(stability_issues),
                top_issue=stability_issues[0] if stability_issues else None,
            )

            # Flag for walk-forward validation
            if len(stability_issues) > 5:
                logger.warning(
                    "parameter_instability_high",
                    recommend_walk_forward_validation=True,
                )

    def get_learning_status(self) -> Dict:
        """
        Return current learning status and metrics.
        """
        return {
            "num_trades": len(self.trade_history),
            "win_rate": self.stats.get("win_rate", 0.0),
            "learning_rate": self.learning_rate,
            "learning_rate_schedule": self.learning_rate_schedule,
            "volatility_estimate": round(self.volatility_estimate, 4),
            "phase_reliability": {
                f"phase_{k}": round(v, 3)
                for k, v in self.phase_reliability.items()
            },
            "current_regime": self.current_regime.value if self.current_regime else "UNKNOWN",
            "trades_since_regime_shift": self.trades_since_regime_shift,
            "weight_concentration_ratio": round(max(self.weights.values()), 3),
            "learning_stability": "stable" if len(self.trade_history) > self.min_reliable_trades else "learning",
            "last_weekly_optimization": self.last_weekly_optimization.isoformat() if self.last_weekly_optimization else None,
        }

    def recommend_deployment_actions(self) -> Dict[str, any]:
        """
        Provide deployment readiness recommendations.
        """
        recommendations = []

        # Check learning maturity
        if len(self.trade_history) < self.min_reliable_trades:
            recommendations.append({
                "category": "learning_maturity",
                "severity": "info",
                "message": f"Only {len(self.trade_history)}/{self.min_reliable_trades} trades. More data needed for stable learning.",
            })

        # Check win rate
        if self.stats.get("win_rate", 0) < 0.5:
            recommendations.append({
                "category": "win_rate",
                "severity": "warning",
                "message": f"Win rate {self.stats.get('win_rate'):.1%} is below 50%. Review phase reliability.",
            })

        # Check parameter stability
        if self.volatility_estimate > 0.1:
            recommendations.append({
                "category": "parameter_stability",
                "severity": "warning",
                "message": "High parameter volatility. Consider walk-forward validation before deployment.",
            })

        # Check weight distribution
        max_weight = max(self.weights.values())
        if max_weight > self.max_weight_concentration:
            recommendations.append({
                "category": "weight_distribution",
                "severity": "info",
                "message": f"Phase {max(self.weights, key=self.weights.get)} dominates with {max_weight:.1%}. May indicate overfitting.",
            })

        deployment_ready = len(recommendations) == 0 or all(
            r["severity"] == "info" for r in recommendations
        )

        return {
            "deployment_ready": deployment_ready,
            "recommendations": recommendations,
            "status": self.get_learning_status(),
        }
