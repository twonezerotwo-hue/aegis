"""
Simplified Dynamic Weights Manager for 7-Phase Consensus

Per-trade weight updates based on:
- Market regime (Trending/Ranging/Crash/HighVol)
- Phase performance (winning vs losing phases)
- Learning rate (0.01 per trade)
"""
import yaml
import numpy as np
from typing import Dict, List
import structlog

logger = structlog.get_logger(__name__)


class DynamicWeights:
    """
    Manages 7-phase dynamic weighting system.

    Design:
    1. Start with regime-based base weights
    2. On each trade: boost winning phase weights, reduce losing phase weights
    3. Normalize weights to sum = 1.0
    4. Store results in YAML for persistence
    """

    PHASES = [
        "phase_1_liquidity",
        "phase_2_structure",
        "phase_3_zones",
        "phase_4_confirmation",
        "phase_5_timing",
        "phase_6_risk",
        "phase_7_macro"
    ]

    # Base weights by market regime
    REGIME_WEIGHTS = {
        "trending": [0.15, 0.20, 0.10, 0.15, 0.15, 0.10, 0.15],      # Structure & Phases matter
        "ranging": [0.10, 0.10, 0.25, 0.20, 0.15, 0.05, 0.15],       # Zones crucial in consolidation
        "crash": [0.05, 0.05, 0.10, 0.10, 0.10, 0.35, 0.25],         # Risk management dominates
        "high_vol": [0.12, 0.12, 0.15, 0.12, 0.12, 0.20, 0.17],      # Balanced with risk emphasis
        "normal": [0.14, 0.15, 0.14, 0.15, 0.14, 0.14, 0.14],        # Equal distribution
    }

    def __init__(self, learning_rate: float = 0.01, config_path: str = None):
        """
        Args:
            learning_rate: Weight adjustment per trade (default 0.01 = 1%)
            config_path: Path to phase_weights.yaml for persistence
        """
        self.current_regime = "normal"
        self.weights = np.array(self.REGIME_WEIGHTS["normal"], dtype=float)
        self.learning_rate = learning_rate
        self.config_path = config_path
        self.trade_count = 0
        self.weight_history = []

        logger.info("dynamic_weights_initialized", regime=self.current_regime, learning_rate=learning_rate)

    def set_regime(self, regime: str):
        """
        Switch to new regime and reset weights to regime baseline.

        Args:
            regime: One of "trending", "ranging", "crash", "high_vol", "normal"
        """
        if regime not in self.REGIME_WEIGHTS:
            logger.warning("unknown_regime", regime=regime, using_default="normal")
            regime = "normal"

        self.current_regime = regime
        self.weights = np.array(self.REGIME_WEIGHTS[regime], dtype=float)

        logger.info("regime_switched", regime=regime, reset_weights=self.get_weights())

    def update_from_trade(
        self,
        winning_phases: List[int],  # Phase indices that helped (1-based → convert to 0-based)
        losing_phases: List[int],   # Phase indices that hurt
        pnl: float
    ):
        """
        Update weights based on trade result.

        Args:
            winning_phases: List of phase IDs that contributed to profit (1-7)
            losing_phases: List of phase IDs that contributed to loss (1-7)
            pnl: Trade PnL (profit/loss amount)
        """
        if pnl > 0:
            # Boost winning phase weights
            for phase_id in winning_phases:
                idx = phase_id - 1  # Convert 1-based to 0-based
                if 0 <= idx < len(self.weights):
                    self.weights[idx] *= (1.0 + self.learning_rate)

                    logger.info(
                        "weight_boosted_winning_phase",
                        phase=self.PHASES[idx],
                        new_weight=round(self.weights[idx], 4)
                    )

        else:
            # Reduce losing phase weights
            for phase_id in losing_phases:
                idx = phase_id - 1
                if 0 <= idx < len(self.weights):
                    self.weights[idx] *= (1.0 - self.learning_rate * 0.5)  # Smaller penalty

                    logger.info(
                        "weight_reduced_losing_phase",
                        phase=self.PHASES[idx],
                        new_weight=round(self.weights[idx], 4)
                    )

        # Normalize to sum = 1.0
        self._normalize_weights()

        self.trade_count += 1
        self.weight_history.append(self.weights.copy())

        logger.info(
            "weights_updated_from_trade",
            trade_num=self.trade_count,
            pnl=pnl,
            winning_phases=winning_phases,
            losing_phases=losing_phases,
            current_weights=self.get_weights()
        )

    def _normalize_weights(self):
        """Ensure weights sum to 1.0."""
        total = np.sum(self.weights)
        if total > 0:
            self.weights = self.weights / total

    def get_weights(self) -> Dict[str, float]:
        """
        Get current weights as phase_name → weight dict.

        Returns:
            Dict mapping phase names to weights (sum = 1.0)
        """
        return dict(zip(self.PHASES, self.weights))

    def get_weight_array(self) -> List[float]:
        """Get weights as simple list [0-6] indexable."""
        return self.weights.tolist()

    def get_phase_weight(self, phase_id: int) -> float:
        """
        Get weight for specific phase.

        Args:
            phase_id: 1-based phase ID (1-7)

        Returns:
            Weight value (0-1)
        """
        idx = phase_id - 1
        if 0 <= idx < len(self.weights):
            return float(self.weights[idx])
        return 0.0

    def save_weights(self, filepath: str = None):
        """
        Save current weights to YAML file.

        Args:
            filepath: Path to save YAML (uses config_path if not provided)
        """
        filepath = filepath or self.config_path
        if not filepath:
            logger.warning("save_weights_no_filepath")
            return

        weights_dict = {
            "regime": self.current_regime,
            "trade_count": self.trade_count,
            "weights": self.get_weights(),
            "weight_array": self.get_weight_array(),
        }

        try:
            with open(filepath, 'w') as f:
                yaml.dump(weights_dict, f, default_flow_style=False)
            logger.info("weights_saved", filepath=filepath)
        except Exception as e:
            logger.error("weights_save_failed", error=str(e))

    def load_weights(self, filepath: str = None):
        """
        Load weights from YAML file.

        Args:
            filepath: Path to load YAML (uses config_path if not provided)
        """
        filepath = filepath or self.config_path
        if not filepath:
            logger.warning("load_weights_no_filepath")
            return

        try:
            with open(filepath, 'r') as f:
                data = yaml.safe_load(f)

            self.current_regime = data.get("regime", "normal")
            self.trade_count = data.get("trade_count", 0)
            weight_array = data.get("weight_array", self.REGIME_WEIGHTS["normal"])
            self.weights = np.array(weight_array, dtype=float)

            logger.info("weights_loaded", filepath=filepath, regime=self.current_regime)
        except Exception as e:
            logger.error("weights_load_failed", error=str(e))

    def get_weight_distribution(self) -> Dict[str, any]:
        """
        Get comprehensive weight distribution info.
        """
        weights_dict = self.get_weights()
        sorted_phases = sorted(weights_dict.items(), key=lambda x: x[1], reverse=True)

        return {
            "current_regime": self.current_regime,
            "total_trades_processed": self.trade_count,
            "weights": weights_dict,
            "sorted_by_importance": [(phase, round(weight, 4)) for phase, weight in sorted_phases],
            "max_phase": sorted_phases[0][0] if sorted_phases else None,
            "max_weight": round(sorted_phases[0][1], 4) if sorted_phases else 0,
            "min_weight": round(sorted_phases[-1][1], 4) if sorted_phases else 0,
        }

    def reset_to_regime(self):
        """Reset weights to current regime defaults (without changing regime)."""
        base = self.REGIME_WEIGHTS.get(self.current_regime, self.REGIME_WEIGHTS["normal"])
        self.weights = np.array(base, dtype=float)
        logger.info("weights_reset_to_regime", regime=self.current_regime)
