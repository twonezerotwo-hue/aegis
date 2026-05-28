"""
AEGIS v7.2 — Dynamic weight engine with strict horizon-config binding.

AEGIS Consensus Engine — Dynamic 7-Way Weighting System

Replaces static 3-way (50/35/15) with 7-way dynamic weighting:
- Each Touche phase gets own weight (learned + regime-aware)
- Weights adapt based on market regime (TRENDING/RANGING/CRASH/HIGH_VOL)
- Learning adjustments applied per phase attribution

Phase 2 Enhancement: Dynamic Weights + Continuous Learning
"""
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import UTC, datetime
import numpy as np
import structlog
import yaml

try:
    from .horizon_config_loader import get_horizon_config
except Exception:  # pragma: no cover - safe fallback for partial runtime imports
    get_horizon_config = None

logger = structlog.get_logger(__name__)


@dataclass
class WeightProfile:
    """Weight configuration for a market regime."""
    phase_1: float  # Liquidity
    phase_2: float  # Structure
    phase_3: float  # Fibonacci
    phase_4: float  # Confirmation
    phase_5: float  # Timing
    phase_6: float  # Risk
    phase_7: float  # Macro
    fundamental: float  # External signal
    news: float  # Sentiment signal

    def to_dict(self) -> Dict[int, float]:
        """Convert to phase_id → weight dict."""
        return {
            1: self.phase_1,
            2: self.phase_2,
            3: self.phase_3,
            4: self.phase_4,
            5: self.phase_5,
            6: self.phase_6,
            7: self.phase_7,
            "fund": self.fundamental,
            "news": self.news,
        }


class DynamicWeightManager:
    """
    Manages 7-way weight distribution based on market regime and learning.

    Design:
    1. Base weights by regime (TRENDING/RANGING/CRASH/HIGH_VOL)
    2. Apply learned adjustments (+/- from attribute analysis)
    3. Normalize to sum = 1.0
    4. Optional: add small random jitter for exploration
    """

    # Base weight profiles by regime
    BASE_PROFILES = {
        "TRENDING": WeightProfile(
            phase_1=0.10, phase_2=0.20, phase_3=0.10, phase_4=0.15,
            phase_5=0.15, phase_6=0.05, phase_7=0.10, fundamental=0.10, news=0.05
        ),
        "RANGING": WeightProfile(
            phase_1=0.08, phase_2=0.10, phase_3=0.20, phase_4=0.15,
            phase_5=0.10, phase_6=0.05, phase_7=0.12, fundamental=0.15, news=0.05
        ),
        "CRASH": WeightProfile(
            phase_1=0.05, phase_2=0.08, phase_3=0.08, phase_4=0.10,
            phase_5=0.10, phase_6=0.25, phase_7=0.19, fundamental=0.10, news=0.05
        ),
        "HIGH_VOL": WeightProfile(
            phase_1=0.12, phase_2=0.12, phase_3=0.12, phase_4=0.12,
            phase_5=0.12, phase_6=0.20, phase_7=0.10, fundamental=0.08, news=0.02
        ),
    }

    def __init__(self, min_phase_weight: float = 0.05, max_phase_weight: float = 0.35):
        """
        Args:
            min_phase_weight: Minimum weight per phase (prevent zeroing out)
            max_phase_weight: Maximum weight per phase (prevent domination)
        """
        self.min_phase_weight = min_phase_weight
        self.max_phase_weight = max_phase_weight

        # Learned adjustments per phase (from attribution analysis)
        self.learned_adjustments: Dict[int, float] = {i: 0.0 for i in range(1, 8)}
        self.learned_adjustments["fund"] = 0.0
        self.learned_adjustments["news"] = 0.0

        # Track adjustment history (for convergence analysis)
        self.adjustment_history: Dict[int, list] = {i: [] for i in range(1, 8)}

    def get_base_weights(self, regime: str) -> Dict[int, float]:
        """Get base weight profile for regime."""
        profile = self.BASE_PROFILES.get(regime, self.BASE_PROFILES["TRENDING"])
        return profile.to_dict()

    def apply_learning_adjustments(
        self,
        phase_attribution: Dict[int, float]
    ) -> Dict[int, float]:
        """
        Apply learned adjustments from attribution analysis.

        Args:
            phase_attribution: {phase_id: correlation_score, ...} from attribution logger

        Returns:
            Updated adjustments dict
        """
        for phase_id, correlation in phase_attribution.items():
            if isinstance(phase_id, int) and 1 <= phase_id <= 7:
                # Adjust based on correlation (but cap to prevent wild swings)
                adjustment_delta = np.clip(correlation * 0.02, -0.05, +0.05)

                # Exponential smoothing: new_adj = 0.7 * old + 0.3 * delta
                self.learned_adjustments[phase_id] = (
                    0.7 * self.learned_adjustments.get(phase_id, 0.0) +
                    0.3 * adjustment_delta
                )

                # Track history
                self.adjustment_history[phase_id].append(
                    self.learned_adjustments[phase_id]
                )

        logger.info(
            "learning_adjustments_applied",
            adjustments={k: round(v, 4) for k, v in self.learned_adjustments.items()},
        )

        return self.learned_adjustments

    def get_dynamic_weights(
        self,
        regime: str,
        apply_learning: bool = True,
        add_jitter: bool = False,
        jitter_scale: float = 0.01,
    ) -> Dict[int, float]:
        """
        Calculate final dynamic weights.

        Args:
            regime: Market regime (TRENDING/RANGING/CRASH/HIGH_VOL)
            apply_learning: Include learned adjustments?
            add_jitter: Add small random noise for exploration? (default: no)
            jitter_scale: Jitter noise scale (typical 0.01)

        Returns:
            Normalized weights dict {phase_id: weight, ...}
        """
        # Start with base weights
        weights = self.get_base_weights(regime)

        # Apply learned adjustments
        if apply_learning:
            for phase_id, adjustment in self.learned_adjustments.items():
                if phase_id in weights:
                    weights[phase_id] += adjustment

        # Apply jitter for exploration
        if add_jitter:
            for phase_id in weights:
                jitter = np.random.normal(0, jitter_scale)
                weights[phase_id] += jitter

        # Apply constraints (min/max per phase)
        for phase_id in range(1, 8):
            if phase_id in weights:
                weights[phase_id] = np.clip(
                    weights[phase_id],
                    self.min_phase_weight,
                    self.max_phase_weight
                )

        # Normalize to sum = 1.0
        total_weight = sum(weights.values())
        if total_weight > 0:
            weights = {k: v / total_weight for k, v in weights.items()}

        logger.info(
            "dynamic_weights_calculated",
            regime=regime,
            apply_learning=apply_learning,
            weights={k: round(v, 3) for k, v in weights.items()}
        )

        return weights

    def _normalize_weights(self, weights: Dict[int, float]) -> Dict[int, float]:
        """Normalize weights to sum = 1.0."""
        total = sum(weights.values())
        if total == 0:
            return {k: 1.0 / len(weights) for k in weights}
        return {k: v / total for k, v in weights.items()}

    def reset_learning(self):
        """Reset learned adjustments to zero (e.g., on regime shift)."""
        for phase_id in self.learned_adjustments:
            self.learned_adjustments[phase_id] = 0.0
        logger.info("learning_adjustments_reset")

    def save_state(self, filepath: str):
        """Save learned adjustments to YAML."""
        state = {
            "learned_adjustments": {
                f"phase_{k}": round(v, 4)
                for k, v in self.learned_adjustments.items()
            },
            "adjustment_history_length": {
                f"phase_{k}": len(v)
                for k, v in self.adjustment_history.items()
            },
        }
        with open(filepath, 'w') as f:
            yaml.dump(state, f)
        logger.info("weight_state_saved", filepath=filepath)

    def load_state(self, filepath: str):
        """Load learned adjustments from YAML."""
        try:
            with open(filepath, 'r') as f:
                state = yaml.safe_load(f)

            for key, value in state.get("learned_adjustments", {}).items():
                phase_id = int(key.split("_")[1])
                self.learned_adjustments[phase_id] = float(value)

            logger.info("weight_state_loaded", filepath=filepath)
        except Exception as e:
            logger.error("weight_state_load_failed", error=str(e))


class ConsensusAggregator:
    """
    Aggregates 7 phase signals + Fundamental + News into final consensus decision.
    """

    def __init__(self, weight_manager: DynamicWeightManager):
        self.weight_manager = weight_manager

    def aggregate_7way_signal(
        self,
        phase_signals: Dict[int, float],  # {1-7: signal_strength 0-1}
        fundamental_score: Optional[float] = None,  # 0-100
        news_score: Optional[float] = None,  # 0-100
        regime: str = "TRENDING",
    ) -> Tuple[float, float, str]:
        """
        Aggregate 7 phase signals + external scores into consensus.

        Args:
            phase_signals: {phase_id: signal_strength 0-1}
            fundamental_score: Fundamental AI score (0-100, normalized to 0-1)
            news_score: News AI score (0-100, normalized to 0-1)
            regime: Market regime for weight selection

        Returns:
            (aggregate_score 0-1, confidence 0-1, recommendation BUY/SELL/HOLD)
        """
        # Get dynamic weights
        weights = self.weight_manager.get_dynamic_weights(
            regime=regime,
            apply_learning=True,
        )

        # Normalize external scores to 0-1
        fund_signal = (fundamental_score / 100.0) if fundamental_score else 0.5
        news_signal = (news_score / 100.0) if news_score else 0.5

        # Calculate weighted aggregate
        phase_contribution = sum(
            phase_signals.get(phase_id, 0.0) * weights.get(phase_id, 0.0)
            for phase_id in range(1, 8)
        )

        fund_contribution = fund_signal * weights.get("fund", 0.1)
        news_contribution = news_signal * weights.get("news", 0.05)

        aggregate_score = phase_contribution + fund_contribution + news_contribution

        # Confidence = how strong is the consensus?
        # Higher if all phases aligned, lower if mixed signals
        phase_variance = np.std(list(phase_signals.values()))  # 0 = perfect alignment, 1 = scattered
        confidence = 1.0 - (phase_variance * 0.3)  # Variance reduces confidence by 0-30%
        confidence = np.clip(confidence, 0.0, 1.0)

        # Recommendation (simple threshold-based)
        if aggregate_score > 0.65:
            recommendation = "BUY"
        elif aggregate_score < 0.35:
            recommendation = "SELL"
        else:
            recommendation = "HOLD"

        logger.info(
            "consensus_aggregated",
            aggregate_score=round(aggregate_score, 3),
            confidence=round(confidence, 3),
            recommendation=recommendation,
            regime=regime,
        )

        return aggregate_score, confidence, recommendation


class ModuleDynamicWeights:
    """Layer-2 module-level dynamic weights for 5-module architecture."""

    REGIME_WEIGHTS = {
        "LIQUIDITY_EXPANSION": {
            "touche": 0.40,
            "fundamental": 0.30,
            "news": 0.15,
            "sentinel": 0.10,
            "quantum": 0.05,
        },
        "RISK_OFF": {
            "touche": 0.20,
            "fundamental": 0.25,
            "news": 0.15,
            "sentinel": 0.30,
            "quantum": 0.10,
        },
        "STAGFLATION": {
            "touche": 0.25,
            "fundamental": 0.35,
            "news": 0.10,
            "sentinel": 0.25,
            "quantum": 0.05,
        },
        "NORMALIZATION": {
            "touche": 0.35,
            "fundamental": 0.30,
            "news": 0.20,
            "sentinel": 0.10,
            "quantum": 0.05,
        },
    }

    def __init__(self):
        self.adjustments = {module: 0.0 for module in self.REGIME_WEIGHTS["NORMALIZATION"].keys()}
        self.update_history: list[Dict[str, object]] = []

    def get_weights(self, regime: str, horizon: str = "medium") -> Dict[str, float]:
        # AEGIS v7.2: Horizon config zorunludur; fallback davranisi kaldirildi.
        if get_horizon_config is None:
            raise ValueError("horizon config loader unavailable")

        horizon_cfg = get_horizon_config(horizon)
        horizon_weights = horizon_cfg.get("module_weights", {}) if isinstance(horizon_cfg, dict) else {}
        if not horizon_weights:
            raise ValueError(f"Horizon '{horizon}' not found in horizon_configs.yaml")

        base = {
            "touche": float(horizon_weights.get("touche", 0.35)),
            "fundamental": float(horizon_weights.get("fundamental", 0.30)),
            "news": float(horizon_weights.get("news", 0.20)),
            "sentinel": float(horizon_weights.get("sentinel", 0.10)),
            "quantum": float(horizon_weights.get("quantum", 0.05)),
        }

        for module_name, adjustment in self.adjustments.items():
            if module_name in base:
                base[module_name] = max(0.01, base[module_name] + adjustment)

        total = sum(base.values())
        return {key: round(value / total, 4) for key, value in base.items()}

    def update_from_trade(
        self,
        winning_modules: list[str],
        losing_modules: list[str],
        pnl: float,
        regime: str,
    ) -> Dict[str, object]:
        if pnl == 0:
            return {
                "pnl": pnl,
                "regime": regime,
                "weights": self.get_weights(regime),
                "adjustments": self.adjustments.copy(),
                "message": "no change for flat pnl",
            }

        for module_name in winning_modules:
            key = module_name.strip().lower()
            if key in self.adjustments:
                self.adjustments[key] += 0.01

        for module_name in losing_modules:
            key = module_name.strip().lower()
            if key in self.adjustments:
                self.adjustments[key] -= 0.005

        for module_name in self.adjustments:
            self.adjustments[module_name] = float(np.clip(self.adjustments[module_name], -0.15, 0.15))

        updated_weights = self.get_weights(regime)
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "pnl": pnl,
            "regime": regime,
            "winning_modules": winning_modules,
            "losing_modules": losing_modules,
            "adjustments": {k: round(v, 4) for k, v in self.adjustments.items()},
            "weights": updated_weights,
        }
        self.update_history.append(record)
        return record
