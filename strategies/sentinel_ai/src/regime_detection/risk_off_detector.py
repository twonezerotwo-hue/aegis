"""
Sentinel AI — Risk Off Detector

Risk regimesi tespiti modülü.
"""
from typing import List, Tuple

import structlog

from ..models import MarketRegime

logger = structlog.get_logger(__name__)


class RiskOffDetector:
    """Market regime detection (Risk-On/Off)."""

    def __init__(self):
        """Initialize detector."""
        self.vix_history: List[float] = []
        self.dxy_history: List[float] = []
        self.fear_greed_history: List[float] = []

    def detect_regime(
        self,
        vix: float,
        dxy: float,
        fear_greed: float,
        us10y: float = 4.0,
        brent: float = 80.0,
    ) -> Tuple[MarketRegime, float]:
        """
        Market regimesini tespit et.

        Args:
            vix: VIX value
            dxy: DXY value
            fear_greed: Fear & Greed index
            us10y: US 10Y yield proxy
            brent: Brent/oil price proxy

        Returns:
            (regime, confidence)
        """
        if self.detect_stagflation(dxy=dxy, us10y=us10y, brent=brent):
            regime = MarketRegime.STAGFLATION
            confidence = 0.85

            logger.info(
                "regime_detected",
                regime=regime.value,
                risk_score="stagflation_rule",
                confidence=round(confidence, 3),
                vix=vix,
                dxy=round(dxy, 2),
                fear_greed=fear_greed,
                us10y=round(us10y, 3),
                brent=round(brent, 2),
            )
            return regime, confidence

        # Risk scoring
        risk_score = 0.0

        # VIX scoring
        if vix > 35:
            risk_score += 3.0  # Extreme fear
        elif vix > 25:
            risk_score += 2.0  # Fear
        elif vix < 15:
            risk_score -= 1.0  # Complacency

        # DXY scoring
        if dxy > 108:
            risk_score += 2.0  # Very strong dollar
        elif dxy > 105.5:
            risk_score += 1.0  # Strong dollar

        # Fear & Greed scoring
        if fear_greed < 20:
            risk_score += 2.5  # Extreme fear
        elif fear_greed < 40:
            risk_score += 1.5  # Fear
        elif fear_greed > 80:
            risk_score -= 1.5  # Extreme greed

        # Determine regime
        if risk_score > 4.0:
            regime = MarketRegime.PANIC
            confidence = min(risk_score / 5.0, 1.0)
        elif risk_score > 2.0:
            regime = MarketRegime.RISK_OFF
            confidence = min(risk_score / 4.0, 1.0)
        elif risk_score < -1.5:
            regime = MarketRegime.RISK_ON
            confidence = min(abs(risk_score) / 3.0, 1.0)
        else:
            regime = MarketRegime.NEUTRAL
            confidence = 0.5

        logger.info(
            "regime_detected",
            regime=regime.value,
            risk_score=round(risk_score, 2),
            confidence=round(confidence, 3),
            vix=vix,
            dxy=round(dxy, 2),
            fear_greed=fear_greed,
        )

        return regime, confidence

    def detect_stagflation(self, dxy: float, us10y: float, brent: float) -> bool:
        """
        Stagflasyon tespiti:
        - Yuksek faiz (US10Y > 4.0)
        - Yuksek petrol (Brent > 90)
        - DXY > 98 (dolar zayif stagflasyon icin uygun)
        """
        if us10y > 4.0 and brent > 90 and dxy > 98:
            return True
        return False

    def add_indicators(
        self,
        vix: float,
        dxy: float,
        fear_greed: float,
    ) -> None:
        """
        Add indicators to history for trend analysis.

        Args:
            vix: VIX value
            dxy: DXY value
            fear_greed: Fear & Greed index
        """
        self.vix_history.append(vix)
        self.dxy_history.append(dxy)
        self.fear_greed_history.append(fear_greed)

        # Keep only last 100 readings
        if len(self.vix_history) > 100:
            self.vix_history.pop(0)
            self.dxy_history.pop(0)
            self.fear_greed_history.pop(0)

    def detect_regime_shift(self) -> bool:
        """
        Regime değişimi tespit et (sharp move).

        Returns:
            True if significant shift detected
        """
        if len(self.vix_history) < 2:
            return False

        vix_change = abs(self.vix_history[-1] - self.vix_history[-2])
        dxy_change = abs(self.dxy_history[-1] - self.dxy_history[-2])

        # Detect significant shifts
        if vix_change > 5.0 or dxy_change > 1.5:
            logger.warning(
                "regime_shift_detected",
                vix_change=round(vix_change, 2),
                dxy_change=round(dxy_change, 2),
            )
            return True

        return False

    def get_volatility_regime(self) -> str:
        """
        Get current volatility regime.

        Returns:
            "LOW", "MEDIUM", "HIGH", "EXTREME"
        """
        if not self.vix_history:
            return "UNKNOWN"

        current_vix = self.vix_history[-1]

        if current_vix > 35:
            return "EXTREME"
        elif current_vix > 25:
            return "HIGH"
        elif current_vix > 15:
            return "MEDIUM"
        else:
            return "LOW"
