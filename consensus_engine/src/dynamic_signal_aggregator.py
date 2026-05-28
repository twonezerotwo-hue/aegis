"""
AEGIS Consensus Engine — Dynamic 7-Way Signal Aggregator (Phase 2)

Extends the static 3-way weighting (50/35/15) with regime-aware 7-phase weighting.

Integration architecture:
- Static 3-way weighting still used for Touche/Fundamental/News mix
- Dynamic 7-way weighting applied ACROSS the 7 trading phases
- Phase weights adapt by market regime (Trending/Ranging/Crash/HighVol)
- Phase weights learn from trade outcomes

This enables:
1. Better performance in trending markets (boost Structure/Confirmation)
2. Protection in crash scenarios (boost Risk/Macro)
3. Efficiency in ranging markets (prioritize Zones)
"""
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
import numpy as np
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class DynamicAggregationResult:
    """Result of dynamic 7-way aggregation."""
    symbol: str
    phase_1_liquidity: float
    phase_2_structure: float
    phase_3_zones: float
    phase_4_confirmation: float
    phase_5_timing: float
    phase_6_risk: float
    phase_7_macro: float

    # Weighting info
    phase_weights: Dict[int, float]
    regime: str

    # Final consensus
    final_score: float
    decision: str  # BUY, SELL, HOLD
    confidence: float

    # Diagnostics
    weighted_contributions: Dict[int, float]
    dominant_phase: Tuple[int, str, float]  # (phase_id, phase_name, contribution)
    learning_applied: bool


class DynamicSignalAggregator:
    """
    Integrates dynamic 7-phase weighting into consensus engine.

    Works alongside existing SignalAggregator by:
    1. Taking 7-phase signal inputs from orchestrator
    2. Applying regime-aware dynamic weights
    3. Returning aggregated score for final decision
    """

    PHASE_NAMES = [
        "phase_1_liquidity",
        "phase_2_structure",
        "phase_3_zones",
        "phase_4_confirmation",
        "phase_5_timing",
        "phase_6_risk",
        "phase_7_macro",
    ]

    def __init__(self, regime_detector, dynamic_weight_manager, weight_updater):
        """
        Args:
            regime_detector: RegimeDetector instance for market regime
            dynamic_weight_manager: DynamicWeightManager with regime weights
            weight_updater: WeightUpdater for learning from trades
        """
        self.regime_detector = regime_detector
        self.weight_manager = dynamic_weight_manager
        self.weight_updater = weight_updater
        self.aggregation_count = 0

        logger.info("dynamic_signal_aggregator_initialized")

    def aggregate_phase_signals(
        self,
        symbol: str,
        phase_signals: Dict[int, float],  # {1: 0.8, 2: 0.75, ..., 7: 0.6}
        regime: Optional[str] = None,
        use_adaptive_weights: bool = True,
    ) -> DynamicAggregationResult:
        """
        Aggregate 7 phase signals with dynamic weighting.

        Args:
            symbol: Trading symbol
            phase_signals: Per-phase confidence scores (0-1)
            regime: Override regime (auto-detects if None)
            use_adaptive_weights: Use learning-adjusted weights

        Returns:
            DynamicAggregationResult with aggregated signal
        """
        # Detect regime if not provided
        if regime is None:
            regime_state = self.regime_detector.get_current_regime()
            regime = (
                regime_state.regime.value.lower()
                if regime_state
                else "normal"
            )

        # Get weights (with or without learning)
        if use_adaptive_weights:
            weights_dict = self.weight_manager.get_dynamic_weights(regime)
        else:
            # Base weights only
            weights_array = self.weight_manager.REGIME_WEIGHTS.get(
                regime.lower(),
                self.weight_manager.REGIME_WEIGHTS["normal"]
            )
            weights_dict = {
                i + 1: w for i, w in enumerate(weights_array)
            }

        # Validate inputs
        if not phase_signals or len(phase_signals) < 7:
            logger.warning(
                "incomplete_phase_signals",
                provided=len(phase_signals),
                expected=7,
                symbol=symbol,
            )
            return self._neutral_result(symbol, regime, weights_dict)

        # Calculate weighted contributions
        weighted_contributions = {}
        for phase_id in range(1, 8):
            signal = phase_signals.get(phase_id, 0.5)
            weight = weights_dict.get(phase_id, 1/7)
            contribution = signal * weight
            weighted_contributions[phase_id] = contribution

        # Aggregate
        final_score = sum(weighted_contributions.values())
        final_score = np.clip(final_score, 0.0, 1.0)

        # Decision
        decision, confidence = self._score_to_decision(final_score)

        # Confidence is average of phase signals
        phase_confidences = [
            phase_signals.get(i, 0.5) for i in range(1, 8)
        ]
        avg_confidence = np.mean(phase_confidences)

        # Find dominant phase
        dominant_id = max(
            weighted_contributions,
            key=weighted_contributions.get
        )
        dominant_name = self.PHASE_NAMES[dominant_id - 1]
        dominant_contribution = weighted_contributions[dominant_id]

        # Build result
        result = DynamicAggregationResult(
            symbol=symbol,
            phase_1_liquidity=float(phase_signals.get(1, 0.5)),
            phase_2_structure=float(phase_signals.get(2, 0.5)),
            phase_3_zones=float(phase_signals.get(3, 0.5)),
            phase_4_confirmation=float(phase_signals.get(4, 0.5)),
            phase_5_timing=float(phase_signals.get(5, 0.5)),
            phase_6_risk=float(phase_signals.get(6, 0.5)),
            phase_7_macro=float(phase_signals.get(7, 0.5)),
            phase_weights={i: float(v) for i, v in weights_dict.items()},
            regime=regime,
            final_score=float(final_score),
            decision=decision,
            confidence=float(avg_confidence),
            weighted_contributions={i: float(v) for i, v in weighted_contributions.items()},
            dominant_phase=(
                int(dominant_id),
                dominant_name,
                float(dominant_contribution)
            ),
            learning_applied=use_adaptive_weights,
        )

        self.aggregation_count += 1

        logger.info(
            "phase_signals_aggregated",
            symbol=symbol,
            regime=regime,
            final_score=round(final_score, 3),
            decision=decision,
            dominant_phase=dominant_name,
            aggregation_num=self.aggregation_count,
        )

        return result

    def _score_to_decision(self, score: float) -> Tuple[str, float]:
        """
        Convert aggregated score to BUY/SELL/HOLD.

        Score thresholds:
        - >0.65: Strong BUY
        - >0.55: Weak BUY
        - <0.35: Strong SELL
        - <0.45: Weak SELL
        - 0.45-0.55: HOLD
        """
        if score > 0.65:
            return "BUY", min(1.0, score + 0.1)
        elif score > 0.55:
            return "BUY", score
        elif score < 0.35:
            return "SELL", min(1.0, (1.0 - score) + 0.1)
        elif score < 0.45:
            return "SELL", 1.0 - score
        else:
            return "HOLD", 0.5

    def _neutral_result(
        self,
        symbol: str,
        regime: str,
        weights_dict: Dict[int, float],
    ) -> DynamicAggregationResult:
        """Return neutral HOLD result."""
        return DynamicAggregationResult(
            symbol=symbol,
            phase_1_liquidity=0.5,
            phase_2_structure=0.5,
            phase_3_zones=0.5,
            phase_4_confirmation=0.5,
            phase_5_timing=0.5,
            phase_6_risk=0.5,
            phase_7_macro=0.5,
            phase_weights=weights_dict,
            regime=regime,
            final_score=0.5,
            decision="HOLD",
            confidence=0.3,
            weighted_contributions={i: 0.0 for i in range(1, 8)},
            dominant_phase=(0, "none", 0.0),
            learning_applied=False,
        )

    def compare_regimes(
        self,
        phase_signals: Dict[int, float],
        symbol: str = "COMPARISON",
    ) -> Dict:
        """
        Show how the same signals are weighted differently across regimes.

        Useful for understanding regime-aware adaptation.
        """
        comparisons = {}

        for regime in ["trending", "ranging", "crash", "high_vol", "normal"]:
            result = self.aggregate_phase_signals(
                symbol,
                phase_signals,
                regime=regime,
                use_adaptive_weights=False,  # Use base weights, not learned
            )

            comparisons[regime] = {
                "final_score": result.final_score,
                "decision": result.decision,
                "dominant_phase": result.dominant_phase[1],
                "phase_weights": {
                    self.PHASE_NAMES[i - 1]: result.phase_weights[i]
                    for i in range(1, 8)
                },
            }

        return comparisons

    def get_aggregation_diagnostics(self, lookback: int = 50) -> Dict:
        """Analyze recent aggregations."""
        return {
            "total_aggregations": self.aggregation_count,
            "recent_lookback": lookback,
            "recommendation": "Track phase_weights evolution over time to validate learning",
        }
