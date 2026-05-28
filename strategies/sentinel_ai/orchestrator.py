"""
Sentinel AI Limited — Market Sentiment Orchestrator

Makro ekonomik verileri analiz ederek risk multiplier üretir.
"""
from typing import Dict, Optional
from datetime import datetime, timezone

import structlog

from .src.macro_indicators.vix_monitor import VIXMonitor
from .src.macro_indicators.dxy_monitor import DXYMonitor
from .src.macro_indicators.fear_greed import FearGreedMonitor
from .src.macro_indicators.rates_monitor import RatesMonitor
from .src.macro_indicators.oil_monitor import OilMonitor
from .src.regime_detection.risk_off_detector import RiskOffDetector
from .src.risk_overlay.multiplier_engine import MultiplierEngine
from .src.models import SentinelDecision, RiskMultiplier, MarketRegime
from .src.macro_enhancer import MacroEnhancer

logger = structlog.get_logger(__name__)


class SentinelAIOrchestrator:
    """Main Sentinel AI orchestrator."""

    def __init__(self, config: Dict):
        """
        Args:
            config: Configuration dictionary
        """
        self.config = config

        # Initialize monitors
        self.vix_monitor = VIXMonitor()
        self.dxy_monitor = DXYMonitor()
        self.fear_greed_monitor = FearGreedMonitor()
        self.rates_monitor = RatesMonitor()
        self.oil_monitor = OilMonitor()

        # Initialize analysis engines
        self.risk_detector = RiskOffDetector()
        self.multiplier_engine = MultiplierEngine(
            floor=config.get("multiplier_floor", 0.1),
            ceiling=config.get("multiplier_ceiling", 1.0),
            default=config.get("default_multiplier", 1.0),
        )
        self.macro_enhancer = MacroEnhancer()

        # State
        self.last_multiplier = 1.0
        self.multiplier_history = []

    async def analyze_market_sentiment(
        self,
        vix: Optional[float] = None,
        dxy: Optional[float] = None,
        fear_greed: Optional[float] = None,
        fed_rates: Optional[float] = None,
        oil_prices: Optional[float] = None,
    ) -> SentinelDecision:
        """
        Analyze market sentiment and generate risk multiplier.

        Args:
            vix: VIX value (if None, fetches from API)
            dxy: DXY value (if None, fetches from API)
            fear_greed: Fear & Greed index (if None, fetches from API)
            fed_rates: Fed rates (if None, fetches from API)
            oil_prices: Oil prices (if None, fetches from API)

        Returns:
            SentinelDecision with risk multiplier
        """
        try:
            # Fetch data if not provided
            if vix is None:
                vix_indicator = await self.vix_monitor.fetch_vix()
                vix = vix_indicator.value if vix_indicator else 20.0
            else:
                vix = vix

            if dxy is None:
                dxy_indicator = await self.dxy_monitor.fetch_dxy()
                dxy = dxy_indicator.value if dxy_indicator else 103.0
            else:
                dxy = dxy

            if fear_greed is None:
                fg_indicator = await self.fear_greed_monitor.fetch_fear_greed()
                fear_greed = fg_indicator.value if fg_indicator else 50.0
            else:
                fear_greed = fear_greed

            if fed_rates is None:
                rates_indicator = await self.rates_monitor.fetch_rates()
                fed_rates = rates_indicator.current_rate if rates_indicator else 4.5
            else:
                fed_rates = fed_rates

            if oil_prices is None:
                oil_indicator = await self.oil_monitor.fetch_oil_prices()
                oil_prices = oil_indicator.price_usd if oil_indicator else 80.0
            else:
                oil_prices = oil_prices

            base_data = {
                "dxy": dxy,
                "us10y": fed_rates,
                "vix": vix,
                "brent": oil_prices,
            }

            try:
                enhanced_data = self.macro_enhancer.enhance(base_data)
            except Exception as enhancer_error:
                logger.warning("macro_enhancer_failed", error=str(enhancer_error))
                enhanced_data = {
                    "dxy_trend_7d": 0.0,
                    "us10y_trend_7d": 0.0,
                    "vix_trend_7d": 0.0,
                    "brent_trend_7d": 0.0,
                    "hg_trend_signal": "neutral",
                    "sp500_vs_ma200": 1.0,
                    "btc_dominance_change_7d": 0.0,
                    "stablecoin_supply_change_7d": 0.0,
                    "exchange_netflow_btc": 0.0,
                    "miner_reserves_change_7d": 0.0,
                    "hyg_lqd_ratio": 0.0,
                    "put_call_ratio": 1.0,
                    "credit_spread_ig": 120.0,
                    "global_liquidity_index": 0.0,
                    "btc_nasdaq_corr_30d": 0.0,
                    "btc_dxy_corr_30d": 0.0,
                    "divergence_flag": "none",
                    "correlation_break_signal": False,
                }

            # Detect regime
            regime, regime_confidence = self.risk_detector.detect_regime(
                vix, dxy, fear_greed, fed_rates, oil_prices
            )

            # Calculate multiplier
            risk_multiplier = self.multiplier_engine.calculate_multiplier(
                vix=vix,
                dxy=dxy,
                fear_greed=fear_greed,
                fed_rates=fed_rates,
                oil_prices=oil_prices,
                us10y=fed_rates,
                brent=oil_prices,
                regime=regime,
            )

            # Generate recommendation
            recommendation = self._generate_recommendation(
                risk_multiplier.value, regime
            )

            # Check for alerts
            alerts = self._check_alerts(risk_multiplier.value, vix)

            # Store history
            self.last_multiplier = risk_multiplier.value
            self.multiplier_history.append(risk_multiplier.value)
            if len(self.multiplier_history) > 1000:
                self.multiplier_history.pop(0)

            # Build decision
            decision = SentinelDecision(
                risk_multiplier=risk_multiplier,
                recommendation=recommendation,
                confidence=regime_confidence,
                market_regime=regime,
                alerts=alerts,
                metrics={
                    "vix": vix,
                    "dxy": round(dxy, 2),
                    "fear_greed": fear_greed,
                    "fed_rates": fed_rates,
                    "hedge_required": float(risk_multiplier.hedge_required),
                    "dxy_trend_7d": float(enhanced_data.get("dxy_trend_7d", 0.0)),
                    "us10y_trend_7d": float(enhanced_data.get("us10y_trend_7d", 0.0)),
                    "vix_trend_7d": float(enhanced_data.get("vix_trend_7d", 0.0)),
                    "brent_trend_7d": float(enhanced_data.get("brent_trend_7d", 0.0)),
                    "sp500_vs_ma200": float(enhanced_data.get("sp500_vs_ma200", 1.0)),
                    "btc_dominance_change_7d": float(enhanced_data.get("btc_dominance_change_7d", 0.0)),
                    "stablecoin_supply_change_7d": float(enhanced_data.get("stablecoin_supply_change_7d", 0.0)),
                    "exchange_netflow_btc": float(enhanced_data.get("exchange_netflow_btc", 0.0)),
                    "miner_reserves_change_7d": float(enhanced_data.get("miner_reserves_change_7d", 0.0)),
                    "hyg_lqd_ratio": float(enhanced_data.get("hyg_lqd_ratio", 0.0)),
                    "put_call_ratio": float(enhanced_data.get("put_call_ratio", 1.0)),
                    "credit_spread_ig": float(enhanced_data.get("credit_spread_ig", 120.0)),
                    "global_liquidity_index": float(enhanced_data.get("global_liquidity_index", 0.0)),
                    "btc_nasdaq_corr_30d": float(enhanced_data.get("btc_nasdaq_corr_30d", 0.0)),
                    "btc_dxy_corr_30d": float(enhanced_data.get("btc_dxy_corr_30d", 0.0)),
                    "divergence_flag": str(enhanced_data.get("divergence_flag", "none")),
                    "correlation_break_signal": bool(enhanced_data.get("correlation_break_signal", False)),
                },
                timestamp=datetime.now(timezone.utc),
            )

            decision.alerts.append(f"HG trend signal: {enhanced_data.get('hg_trend_signal', 'neutral')}")

            logger.info(
                "sentiment_analysis_complete",
                multiplier=round(risk_multiplier.value, 3),
                regime=regime.value,
                recommendation=recommendation,
            )

            return decision

        except Exception as e:
            logger.error("sentiment_analysis_error", error=str(e))
            # Return neutral decision
            return SentinelDecision(
                risk_multiplier=RiskMultiplier(
                    value=1.0,
                    regime=MarketRegime.NEUTRAL,
                    components={},
                ),
                recommendation="MAINTAIN",
                confidence=0.0,
                market_regime=MarketRegime.NEUTRAL,
                alerts=["Error in analysis"],
            )

    def _generate_recommendation(
        self, multiplier: float, regime: MarketRegime
    ) -> str:
        """Generate trading recommendation."""
        if multiplier < 0.3:
            return "REDUCE_SIZE"
        elif multiplier < 0.7:
            return "REDUCE_SIZE"
        elif multiplier > 0.9 and regime == MarketRegime.RISK_ON:
            return "INCREASE_SIZE"
        elif regime == MarketRegime.STAGFLATION:
            return "REDUCE_SIZE"
        else:
            return "MAINTAIN"

    def _check_alerts(self, multiplier: float, vix: float) -> list:
        """Check for alert conditions."""
        alerts = []

        if multiplier < 0.2:
            alerts.append("CRITICAL: Multiplier at floor")

        if vix > 40:
            alerts.append("CRITICAL: Extreme volatility (VIX > 40)")

        if multiplier < 0.3 and vix < 10:
            alerts.append("WARNING: Multiplier low but VIX low")

        if abs(multiplier - self.last_multiplier) > 0.3:
            alerts.append("WARNING: Sharp multiplier change")

        return alerts

    async def get_current_multiplier(self) -> float:
        """Get current risk multiplier."""
        decision = await self.analyze_market_sentiment()
        return decision.risk_multiplier.value

    def get_multiplier_statistics(self) -> Dict:
        """Get statistics on multiplier history."""
        if not self.multiplier_history:
            return {}

        return {
            "current": self.multiplier_history[-1],
            "average": sum(self.multiplier_history) / len(self.multiplier_history),
            "min": min(self.multiplier_history),
            "max": max(self.multiplier_history),
            "std_dev": self._calculate_std_dev(self.multiplier_history),
            "history_length": len(self.multiplier_history),
        }

    @staticmethod
    def _calculate_std_dev(values: list) -> float:
        """Calculate standard deviation."""
        if len(values) < 2:
            return 0.0

        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5
