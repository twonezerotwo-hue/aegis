"""
AEGIS Consensus Engine — Market Regime Detector

Unified regime detection combining macro + technical indicators:
- TRENDING: Strong directional move (ADX > 25, VIX < 25)
- RANGING: Consolidation/sideways (ADX < 25, BB squeeze)
- CRASH: Panic/stress mode (VIX > 30 or Fear < 25)
- HIGH_VOL: Elevated volatility but not panic (VIX 20-30)

Phase 2 Enhancement: Regime-aware weight switching + continuous monitoring
"""
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import numpy as np
import structlog

logger = structlog.get_logger(__name__)


class MarketRegime(Enum):
    """Four-state market regime model."""
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    CRASH = "CRASH"
    HIGH_VOL = "HIGH_VOL"


@dataclass
class RegimeState:
    """Current market regime state."""
    regime: MarketRegime
    confidence: float  # 0.0-1.0: how sure are we?
    component_scores: Dict[str, float] = field(default_factory=dict)  # {ADX: 0.8, VIX: 0.6, ...}
    persistence_candles: int = 0  # How many candles in this regime
    regime_shifted_this_candle: bool = False
    previous_regime: Optional[MarketRegime] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict:
        """Convert to JSON-serializable dict."""
        return {
            "regime": self.regime.value,
            "confidence": round(self.confidence, 3),
            "component_scores": {k: round(v, 3) for k, v in self.component_scores.items()},
            "persistence_candles": self.persistence_candles,
            "regime_shifted": self.regime_shifted_this_candle,
            "previous_regime": self.previous_regime.value if self.previous_regime else None,
            "timestamp": self.timestamp,
        }


class RegimeDetector:
    """
    Detects market regime from technical + macro indicators.

    Scoring System:
    - Aggregate multiple indicators into regime votes
    - Each indicator contributes confidence_score (0-1)
    - Final regime = highest scoring regime
    - Confidence = normalized score
    """

    def __init__(self, regime_persistence_threshold: int = 3):
        """
        Args:
            regime_persistence_threshold: Require N consecutive candles before regime shift
        """
        self.regime_persistence_threshold = regime_persistence_threshold
        self.current_regime: Optional[RegimeState] = None
        self.regime_history: list = []

    def detect_regime(
        self,
        adx: Optional[float] = None,
        di_plus: Optional[float] = None,
        di_minus: Optional[float] = None,
        bb_width_pct: Optional[float] = None,
        vix: Optional[float] = None,
        fear_greed: Optional[float] = None,
        dxy: Optional[float] = None,
        atr: Optional[float] = None,
    ) -> RegimeState:
        """
        Detect current market regime.

        Args:
            adx: Average Directional Index (0-100, >25 = trend)
            di_plus: +DI component
            di_minus: -DI component
            bb_width_pct: Bollinger Band width as % of middle band
            vix: VIX index (0-100+)
            fear_greed: Fear & Greed index (0-100)
            dxy: Dollar Index
            atr: Average True Range

        Returns:
            RegimeState with current regime and confidence
        """
        component_scores = {}

        # ─────────────────────────────────────────────────────────────
        # TREND STRENGTH (from ADX)
        # ─────────────────────────────────────────────────────────────
        trend_strength = 0.0
        if adx is not None:
            if adx > 50:
                trend_strength = 1.0  # Very strong trend
            elif adx > 25:
                trend_strength = 0.7  # Strong trend
            elif adx > 15:
                trend_strength = 0.3  # Weak trend
            else:
                trend_strength = 0.0  # No trend

            # Confirm direction with DI
            if di_plus is not None and di_minus is not None:
                di_diff = abs(di_plus - di_minus)
                if di_diff > 20:
                    trend_strength *= 1.2  # Strong confirmation

        component_scores["trend_strength"] = trend_strength

        # ─────────────────────────────────────────────────────────────
        # VOLATILITY STATE (from Bollinger Bands + VIX)
        # ─────────────────────────────────────────────────────────────
        volatility_score = 0.5  # Default: medium volatility
        bb_squeeze = False

        if bb_width_pct is not None:
            if bb_width_pct < 2.0:
                bb_squeeze = True  # Strong squeeze
                volatility_score = 0.1
            elif bb_width_pct < 3.0:
                bb_squeeze = True
                volatility_score = 0.2
            elif bb_width_pct > 8.0:
                volatility_score = 0.9  # High expansion
            elif bb_width_pct > 5.0:
                volatility_score = 0.7  # Moderate expansion

        # Adjust volatility score based on VIX
        if vix is not None:
            if vix > 35:
                volatility_score = 0.95  # Extreme
            elif vix > 25:
                volatility_score = 0.8  # High
            elif vix > 15:
                volatility_score = 0.5  # Normal
            elif vix < 12:
                volatility_score = 0.2  # Low/complacent

        component_scores["volatility"] = volatility_score
        component_scores["bb_squeeze"] = 1.0 if bb_squeeze else 0.0

        # ─────────────────────────────────────────────────────────────
        # SENTIMENT STATE (from Fear & Greed)
        # ─────────────────────────────────────────────────────────────
        sentiment_score = 0.5  # Default: neutral
        extreme_fear = False
        extreme_greed = False

        if fear_greed is not None:
            if fear_greed < 20:
                extreme_fear = True
                sentiment_score = 0.9  # High panic signal
            elif fear_greed < 40:
                sentiment_score = 0.7
            elif fear_greed > 80:
                extreme_greed = True
                sentiment_score = 0.3  # Overheated
            elif fear_greed > 60:
                sentiment_score = 0.4

        component_scores["sentiment"] = sentiment_score
        component_scores["extreme_fear"] = 1.0 if extreme_fear else 0.0
        component_scores["extreme_greed"] = 1.0 if extreme_greed else 0.0

        # ─────────────────────────────────────────────────────────────
        # REGIME VOTING
        # ─────────────────────────────────────────────────────────────

        # CRASH regime: Triggered by extreme fear OR high VIX + sentiment
        crash_score = 0.0
        if extreme_fear or (vix and vix > 30):
            crash_score = 1.0

        # TRENDING regime: ADX strong + low volatility (not crash)
        trending_score = 0.0
        if trend_strength > 0.6 and volatility_score < 0.8 and crash_score < 0.5:
            trending_score = trend_strength * 0.9

        # RANGING regime: Low trend + BB squeeze
        ranging_score = 0.0
        if trend_strength < 0.3 and bb_squeeze:
            ranging_score = 0.9

        # HIGH_VOL regime: High volatility but no crash/trend
        high_vol_score = 0.0
        if volatility_score > 0.6 and trending_score < 0.5 and crash_score < 0.5:
            if not bb_squeeze:  # Not ranging
                high_vol_score = volatility_score * 0.8

        regime_scores = {
            MarketRegime.CRASH: crash_score,
            MarketRegime.TRENDING: trending_score,
            MarketRegime.RANGING: ranging_score,
            MarketRegime.HIGH_VOL: high_vol_score,
        }

        component_scores["regime_scores"] = {r.value: s for r, s in regime_scores.items()}

        # ─────────────────────────────────────────────────────────────
        # DETERMINE FINAL REGIME & CONFIDENCE
        # ─────────────────────────────────────────────────────────────

        # Crash takes priority (risk safety)
        if crash_score > 0.7:
            new_regime = MarketRegime.CRASH
            confidence = min(0.9, crash_score)
        else:
            # Otherwise pick highest scoring regime
            winning_regime = max(regime_scores, key=regime_scores.get)
            new_regime = winning_regime
            confidence = min(1.0, regime_scores[new_regime] + 0.3)  # Add base confidence

        # Check for regime shift
        regime_shifted = False
        previous_regime = self.current_regime.regime if self.current_regime else None

        if self.current_regime is None or new_regime != self.current_regime.regime:
            regime_shifted = True
            persistence_candles = 1
        else:
            persistence_candles = self.current_regime.persistence_candles + 1

        # Create new regime state
        new_state = RegimeState(
            regime=new_regime,
            confidence=confidence,
            component_scores=component_scores,
            persistence_candles=persistence_candles,
            regime_shifted_this_candle=regime_shifted,
            previous_regime=previous_regime,
        )

        self.current_regime = new_state
        self.regime_history.append(new_state)

        logger.info(
            "regime_detected",
            regime=new_regime.value,
            confidence=round(confidence, 3),
            persistence_candles=persistence_candles,
            regime_shifted=regime_shifted,
            component_scores={k: round(v, 3) for k, v in component_scores.items()},
        )

        return new_state

    def get_current_regime(self) -> Optional[RegimeState]:
        """Get current regime state."""
        return self.current_regime

    def get_regime_confidence(self) -> float:
        """Get confidence in current regime classification (0-1)."""
        return self.current_regime.confidence if self.current_regime else 0.5

    def detect_regime_shift(self) -> bool:
        """Did regime shift on the current candle?"""
        return self.current_regime.regime_shifted_this_candle if self.current_regime else False

    def get_regime_persistence(self) -> int:
        """How many candles have we been in current regime?"""
        return self.current_regime.persistence_candles if self.current_regime else 0

    def predict_next_regime(self) -> Optional[Tuple[MarketRegime, float]]:
        """
        Probabilistic forecast of next regime (optional, basic).

        Returns:
            (predicted_regime, probability)
        """
        if len(self.regime_history) < 5:
            return None  # Not enough history

        # Simple: if in regime for >10 candles, check if signs of shift
        if self.get_regime_persistence() > 10:
            return self.current_regime.regime, 0.7

        # Otherwise, neutral forecast
        return None

    def get_regime_history_summary(self, lookback: int = 100) -> Dict:
        """Summarize regime changes over lookback period."""
        recent_history = self.regime_history[-lookback:]

        regime_counts = {r.value: 0 for r in MarketRegime}
        for state in recent_history:
            regime_counts[state.regime.value] += 1

        avg_persistence = (
            np.mean([s.persistence_candles for s in recent_history])
            if recent_history else 0
        )

        regime_shifts = sum(
            1 for s in recent_history if s.regime_shifted_this_candle
        )

        return {
            "regime_counts": regime_counts,
            "dominant_regime": max(
                regime_counts, key=regime_counts.get
            ),
            "avg_persistence_candles": round(avg_persistence, 1),
            "total_regime_shifts": regime_shifts,
            "shift_frequency": round(regime_shifts / max(len(recent_history), 1), 3),
        }

    def reset(self):
        """Reset regime detection (e.g., on new trading session)."""
        self.current_regime = None
        self.regime_history = []
        logger.info("regime_detector_reset")
