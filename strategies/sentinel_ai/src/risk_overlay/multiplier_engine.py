"""
Sentinel AI — Risk Multiplier Engine

Risk multiplier hesaplama motoru.
"""
from typing import Dict, Tuple
from datetime import datetime, timezone

import structlog

from ..models import RiskMultiplier, MarketRegime

logger = structlog.get_logger(__name__)


class MultiplierEngine:
    """Risk multiplier calculation engine."""

    def __init__(
        self,
        floor: float = 0.1,
        ceiling: float = 1.0,
        default: float = 1.0,
    ):
        """
        Args:
            floor: Minimum multiplier
            ceiling: Maximum multiplier
            default: Starting multiplier
        """
        self.floor = floor
        self.ceiling = ceiling
        self.default = default

    def calculate_multiplier(
        self,
        vix: float,
        dxy: float,
        fear_greed: float,
        fed_rates: float = 4.5,
        oil_prices: float = 80.0,
        us10y: float | None = None,
        brent: float | None = None,
        regime: MarketRegime = MarketRegime.NEUTRAL,
    ) -> RiskMultiplier:
        """
        Calculate risk multiplier from all indicators.

        Args:
            vix: VIX index value
            dxy: DXY value
            fear_greed: Fear & Greed index (0-100)
            fed_rates: Federal Funds Rate (%)
            oil_prices: WTI price (USD/barrel)
            us10y: US 10Y yield proxy
            brent: Brent/oil price proxy
            regime: Current market regime

        Returns:
            RiskMultiplier with calculation details
        """
        multiplier = self.default
        components = {}

        # 1. VIX adjustment
        vix_mult = self._apply_vix_adjustment(vix)
        multiplier = multiplier * vix_mult
        components["vix"] = vix_mult

        # 2. DXY adjustment
        dxy_mult = self._apply_dxy_adjustment(dxy)
        multiplier = multiplier * dxy_mult
        components["dxy"] = dxy_mult

        # 3. Fear & Greed adjustment
        fg_mult = self._apply_fear_greed_adjustment(fear_greed)
        multiplier = multiplier * fg_mult
        components["fear_greed"] = fg_mult

        # 4. Fed Rates adjustment (optional)
        if fed_rates > 0:
            rates_mult = self._apply_rates_adjustment(fed_rates)
            multiplier = multiplier * rates_mult
            components["fed_rates"] = rates_mult

        # 5. Oil Prices adjustment (optional)
        if oil_prices > 0:
            oil_mult = self._apply_oil_adjustment(oil_prices)
            multiplier = multiplier * oil_mult
            components["oil"] = oil_mult

        effective_us10y = us10y if us10y is not None else fed_rates
        effective_brent = brent if brent is not None else oil_prices

        hedge_required = False
        macro_note = ""
        if regime == MarketRegime.STAGFLATION and effective_us10y > 4.0 and effective_brent > 90 and dxy > 98:
            hedge_required = True
            macro_note = "Stagflasyon riski - hedge pozisyonu dusunun"
            multiplier = max(self.floor, multiplier * 0.85)

        # Apply constraints
        multiplier = max(self.floor, min(multiplier, self.ceiling))

        # Calculate signal strength (average confidence)
        signal_strength = 0.0
        if vix > 25 or vix < 15:
            signal_strength += 0.25
        if dxy > 105 or dxy < 101:
            signal_strength += 0.25
        if fear_greed < 40 or fear_greed > 70:
            signal_strength += 0.25
        if fed_rates > 4.5:
            signal_strength += 0.25

        # Build reasoning
        reasoning = self._build_reasoning(
            multiplier, vix, dxy, fear_greed, regime
        )

        result = RiskMultiplier(
            value=multiplier,
            regime=regime,
            components=components,
            timestamp=datetime.now(timezone.utc),
            reasoning=reasoning,
            signal_strength=min(signal_strength, 1.0),
            hedge_required=hedge_required,
            macro_note=macro_note,
        )

        logger.info(
            "multiplier_calculated",
            multiplier=round(multiplier, 3),
            regime=regime.value,
            components=components,
        )

        return result

    def _apply_vix_adjustment(self, vix: float) -> float:
        """Apply VIX adjustment."""
        mult = 1.0

        if vix > 35:
            mult = 0.4
        elif vix > 25:
            mult = 0.7
        elif vix < 15:
            mult = min(1.1, 1.0)

        return mult

    def _apply_dxy_adjustment(self, dxy: float) -> float:
        """Apply DXY adjustment."""
        mult = 1.0

        if dxy > 108.0:
            mult = 0.6
        elif dxy > 105.5:
            mult = 0.8

        return mult

    def _apply_fear_greed_adjustment(self, index: float) -> float:
        """Apply Fear & Greed adjustment."""
        mult = 1.0

        if index < 20:
            mult = 0.7
        elif index < 40:
            mult = 0.9
        elif index > 80:
            mult = 0.8

        return mult

    def _apply_rates_adjustment(self, rate: float) -> float:
        """Apply Fed Rates adjustment."""
        mult = 1.0

        if rate > 5.0:
            mult = 0.9

        return mult

    def _apply_oil_adjustment(self, price: float) -> float:
        """Apply Oil price adjustment."""
        mult = 1.0

        if price > 100:
            mult = 0.85

        return mult

    def apply_risk_gatekeeper_filters(
        self,
        position_size: float,
        vix: float,
        dxy: float,
        fear_greed: float,
    ) -> Tuple[float, Dict[str, float]]:
        """
        COMPONENT 4: Apply risk gatekeeper filt ers to position size.
        Sentinel AI: Filter-only (no signal generation).

        Args:
            position_size: Original calculated position size
            vix: VIX value
            dxy: DXY value
            fear_greed: Fear & Greed index (0-100)

        Returns:
            (adjusted_position_size, filter_breakdown)
        """
        adjusted_size = position_size
        filters = {}

        # VIX filter: VIX > 30 → reduce to 70%
        if vix > 30.0:
            vix_multiplier = 0.70
            adjusted_size *= vix_multiplier
            filters["vix"] = vix_multiplier
            logger.info("risk_gatekeeper_vix", vix=vix, reduction=1-vix_multiplier)
        else:
            filters["vix"] = 1.0

        # DXY filter: DXY > 106 → reduce to 80%
        if dxy > 106.0:
            dxy_multiplier = 0.80
            adjusted_size *= dxy_multiplier
            filters["dxy"] = dxy_multiplier
            logger.info("risk_gatekeeper_dxy", dxy=dxy, reduction=1-dxy_multiplier)
        else:
            filters["dxy"] = 1.0

        # Fear & Greed filter: FG < 25 → reduce to 60%
        if fear_greed < 25.0:
            fg_multiplier = 0.60
            adjusted_size *= fg_multiplier
            filters["fear_greed"] = fg_multiplier
            logger.info("risk_gatekeeper_fear_greed", fg=fear_greed, reduction=1-fg_multiplier)
        else:
            filters["fear_greed"] = 1.0

        return adjusted_size, filters

    def _build_reasoning(
        self,
        multiplier: float,
        vix: float,
        dxy: float,
        fear_greed: float,
        regime: MarketRegime,
    ) -> str:
        """Build human-readable reasoning."""
        reasons = []

        if regime == MarketRegime.PANIC:
            reasons.append("Market in PANIC mode")
        elif regime == MarketRegime.RISK_OFF:
            reasons.append("Risk-off environment")
        elif regime == MarketRegime.STAGFLATION:
            reasons.append("Stagflation risk detected")
        elif regime == MarketRegime.RISK_ON:
            reasons.append("Risk-on environment")

        if vix > 35:
            reasons.append("Extreme fear (VIX > 35)")
        elif vix > 25:
            reasons.append("Fear present (VIX > 25)")
        elif vix < 15:
            reasons.append("Complacency (VIX < 15)")

        if multiplier < 0.3:
            reasons.append("High caution advised")
        elif multiplier < 0.6:
            reasons.append("Moderate risk reduction")
        elif multiplier > 0.9:
            reasons.append("Normal operations")

        return "; ".join(reasons) if reasons else "Neutral sentiment"
