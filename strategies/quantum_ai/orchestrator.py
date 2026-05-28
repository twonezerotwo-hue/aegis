"""
Quantum AI Limited — Market Making Orchestrator

Tüm MM bileşenlerini birleştiren ana orchestrator.
"""
from typing import Dict, List
from datetime import datetime

import structlog

from .src.mm_engine.avellaneda_stoikov import AvellanedaStoikov, TwoSidedQuote
from .src.mm_engine.spread_optimizer import SpreadOptimizer
from .src.mm_engine.skew_manager import SkewManager
from .src.mm_engine.order_manager import OrderManager
from .src.execution.order_router import OrderRouter
from .src.arbitrage.cross_exchange import CrossExchangeArbitrage
from .src.arbitrage.funding_arb import FundingRateArbitrage
from .src.risk_mgmt.inventory_risk import InventoryRiskManager
from .src.risk_mgmt.var_calculator import VARCalculator
from .src.core.models import MMParameters

logger = structlog.get_logger(__name__)


class QuantumAIOrchestrator:
    """Quantum AI Limited market making orchestrator."""

    def __init__(
        self,
        config: Dict,
    ):
        """
        Args:
            config: Configuration dictionary with MM parameters
        """
        self.config = config

        # Create MM parameters from config
        mm_params = MMParameters(
            gamma=config.get("gamma", 0.075),
            inventory_target=config.get("inventory_target", 0.0),
            order_arrival_lambda=config.get("order_arrival_lambda", 10.0),
            time_horizon=config.get("time_horizon", 60.0),
            min_spread_bps=config.get("min_spread_bps", 0.5),
            max_spread_bps=config.get("max_spread_bps", 10.0),
        )

        # Initialize components
        self.avellaneda = AvellanedaStoikov(mm_params)
        self.spread_optimizer = SpreadOptimizer()
        self.skew_manager = SkewManager()
        self.order_manager = OrderManager()
        self.order_router = OrderRouter({})

        # Arbitrage engines
        self.cross_exchange_arb = CrossExchangeArbitrage(
            min_spread_bps=config.get("min_arbitrage_spread_bps", 10)
        )
        self.funding_arb = FundingRateArbitrage(
            min_apy=config.get("min_funding_apy", 0.05)
        )

        # Risk management
        self.inventory_risk = InventoryRiskManager(
            max_inventory=config.get("max_inventory", 1000.0)
        )
        self.var_calculator = VARCalculator()

        # State
        self.positions = {}  # {symbol: position}
        self.active_quotes = {}  # {symbol: quote}

    async def process_stream(
        self,
        market_data: Dict,
        portfolio_state: Dict,
    ) -> Dict:
        """
        Main market making pipeline.

        Args:
            market_data: Market prices and metrics
            portfolio_state: Current portfolio state

        Returns:
            Trading decisions and quotes
        """
        try:
            logger.info("processing_market_data", data_keys=list(market_data.keys()))

            # 1. Calculate optimal quotes using Avellaneda-Stoikov
            quotes = await self._generate_quotes(market_data)

            # 2. Check arbitrage opportunities
            arbitrage_signals = await self._check_arbitrage(market_data)

            # 3. Manage inventory and risk
            risk_decisions = await self._manage_risk(portfolio_state)

            # 4. Route orders
            execution_plan = await self._route_orders(quotes, risk_decisions)

            # 5. Update positions
            self.positions = await self._update_positions(execution_plan)

            result = {
                "quotes": quotes,
                "arbitrage_signals": arbitrage_signals,
                "risk_decisions": risk_decisions,
                "execution_plan": execution_plan,
                "positions": self.positions,
                "timestamp": datetime.now().isoformat(),
            }

            logger.info(
                "market_processing_complete",
                quotes_generated=len(quotes),
                arbitrage_signals=len(arbitrage_signals),
            )

            return result

        except Exception as e:
            logger.error("orchestrator_error", error=str(e))
            return {
                "error": str(e),
                "quotes": {},
                "arbitrage_signals": [],
            }

    async def _generate_quotes(
        self,
        market_data: Dict,
    ) -> Dict[str, TwoSidedQuote]:
        """Generate optimal two-sided quotes."""
        quotes = {}

        for symbol, data in market_data.items():
            try:
                mid_price = data.get("mid_price", 0.0)
                volatility = data.get("volatility", 0.02)
                time_remaining = data.get("time_remaining", 60.0)

                # Avellaneda-Stoikov calculation
                inventory = self.positions.get(symbol, {}).get("size", 0.0)

                quote = self.avellaneda.quote(
                    mid_price=mid_price,
                    volatility=volatility,
                    current_inventory=inventory,
                    time_remaining=time_remaining,
                )

                # Apply skew adjustment
                skew = self.skew_manager.calculate_skew(
                    inventory=inventory,
                    target_inventory=self.config.get("inventory_target", 0.0),
                )
                adjusted_bid, adjusted_ask = self.skew_manager.apply_skew_to_quote(
                    mid_price=mid_price,
                    bid=quote.bid_price,
                    ask=quote.ask_price,
                    skew=skew,
                )

                # Update quote with adjusted prices
                quote.bid_price = adjusted_bid
                quote.ask_price = adjusted_ask

                quotes[symbol] = quote

            except Exception as e:
                logger.error("quote_generation_error", symbol=symbol, error=str(e))

        return quotes

    async def _check_arbitrage(
        self,
        market_data: Dict,
    ) -> List[Dict]:
        """Check for arbitrage opportunities."""
        signals = []

        # Cross-exchange arbitrage
        if "exchange_prices" in market_data:
            for symbol, prices in market_data["exchange_prices"].items():
                opp = self.cross_exchange_arb.detect_opportunity(symbol, prices)
                if opp:
                    signals.append({
                        "type": "cross_exchange",
                        "symbol": symbol,
                        "spread_bps": round(opp.spread_pct * 100, 2),
                        "buy_exchange": opp.buy_exchange,
                        "sell_exchange": opp.sell_exchange,
                    })

        # Funding rate arbitrage
        if "funding_rates" in market_data:
            for symbol, rate in market_data["funding_rates"].items():
                funding_data = market_data.get("funding_data", {}).get(symbol)
                if funding_data:
                    opp = self.funding_arb.detect_opportunity(funding_data)
                    if opp:
                        signals.append({
                            "type": "funding_rate",
                            "symbol": symbol,
                            "apy": round(opp.annualized_return, 4),
                        })

        return signals

    async def _manage_risk(
        self,
        portfolio_state: Dict,
    ) -> Dict:
        """Manage inventory and portfolio risk."""
        decisions = {}

        for symbol, position in self.positions.items():
            try:
                current_price = portfolio_state.get(symbol, {}).get("price", 0.0)

                metrics = self.inventory_risk.calculate_risk_metrics(
                    symbol=symbol,
                    current_inventory=position.get("size", 0.0),
                    current_price=current_price,
                    portfolio_value=portfolio_state.get("portfolio_value", 100000),
                )

                decisions[symbol] = {
                    "risk_level": metrics.risk_level,
                    "should_limit": self.inventory_risk.should_limit_orders(
                        metrics, 0.0  # Proposed size
                    ),
                    "skew_multiplier": metrics.skew_multiplier,
                }

            except Exception as e:
                logger.error("risk_management_error", symbol=symbol, error=str(e))

        return decisions

    async def _route_orders(
        self,
        quotes: Dict[str, TwoSidedQuote],
        risk_decisions: Dict,
    ) -> List[Dict]:
        """Route orders to exchanges."""
        execution_plan = []

        for symbol, quote in quotes.items():
            risk_info = risk_decisions.get(symbol, {})

            if not risk_info.get("should_limit", False):
                execution_plan.append({
                    "symbol": symbol,
                    "bid": quote.bid_price,
                    "ask": quote.ask_price,
                    "bid_size": quote.bid_qty,
                    "ask_size": quote.ask_qty,
                })

        return execution_plan

    async def _update_positions(
        self,
        execution_plan: List[Dict],
    ) -> Dict:
        """Update positions based on execution plan."""
        # TODO: Track filled orders and update positions
        return self.positions

    async def calculate_metrics(
        self,
        portfolio_state: Dict,
    ) -> Dict:
        """Calculate portfolio metrics for monitoring."""
        portfolio_value = portfolio_state.get("portfolio_value", 100000)
        daily_returns = portfolio_state.get("daily_returns", [])
        position_deltas = {
            symbol: pos.get("delta", 0.0)
            for symbol, pos in self.positions.items()
        }

        var_metrics = self.var_calculator.calculate_metrics(
            portfolio_value=portfolio_value,
            daily_returns=daily_returns,
            position_deltas=position_deltas,
        )

        return {
            "var_95": var_metrics.var_95,
            "var_99": var_metrics.var_99,
            "portfolio_delta": var_metrics.portfolio_delta,
            "max_loss": var_metrics.max_loss,
        }
