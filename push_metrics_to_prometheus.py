#!/usr/bin/env python3
# AEGIS v7.2 — Metrics pusher pushgateway baglanti duzeltmesi.
"""
AEGIS Holding - Push Metrics to Prometheus
Generates synthetic trading data and pushes metrics to Prometheus directly
"""

import time
import random
import requests
import os
from datetime import datetime
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AEGIS-PrometheusPusher")

# Prometheus Pushgateway URL
PUSHGATEWAY_URL = os.getenv("PUSHGATEWAY_URL", "http://pushgateway:9091")

class PrometheusMetricsPusher:
    """Pushes AEGIS metrics to Prometheus"""

    def __init__(self):
        self.registry = CollectorRegistry()
        self._create_gauges()
        self.iteration = 0

        # Base prices
        self.btc_price = 45000
        self.eth_price = 2500

    def _create_gauges(self):
        """Create Prometheus gauge metrics"""
        # Fund Health Metrics
        self.total_capital = Gauge('aegis_fund_total_capital', 'Total Fund Capital', registry=self.registry)
        self.daily_pnl = Gauge('aegis_fund_daily_pnl', 'Daily P&L', registry=self.registry)
        self.sharpe_ratio = Gauge('aegis_fund_sharpe_ratio', 'Sharpe Ratio', registry=self.registry)
        self.max_drawdown = Gauge('aegis_fund_max_drawdown', 'Max Drawdown', registry=self.registry)
        self.var_99 = Gauge('aegis_fund_var_99', 'Value at Risk 99%', registry=self.registry)
        self.btc_price_gauge = Gauge('aegis_btc_price', 'BTC Price', registry=self.registry)
        self.eth_price_gauge = Gauge('aegis_eth_price', 'ETH Price', registry=self.registry)

        # Strategy Performance Metrics
        self.touche_eqs_score = Gauge('aegis_touche_eqs_score', 'Touche EQS Score', registry=self.registry)
        self.fundamental_score = Gauge('aegis_fundamental_score', 'Fundamental Score', registry=self.registry)
        self.quantum_pnl = Gauge('aegis_quantum_pnl', 'Quantum Market-Making PnL', registry=self.registry)
        self.quantum_volume = Gauge('aegis_quantum_volume', 'Quantum Traded Volume', registry=self.registry)
        self.sentinel_multiplier = Gauge('aegis_sentinel_multiplier', 'Sentinel Risk Multiplier', registry=self.registry)
        self.vix_level = Gauge('aegis_vix_level', 'VIX Level', registry=self.registry)
        self.dxy_level = Gauge('aegis_dxy_level', 'DXY Level', registry=self.registry)
        self.fear_greed = Gauge('aegis_fear_greed_index', 'Fear & Greed Index', registry=self.registry)
        self.consensus_buy = Gauge('aegis_consensus_buy_signals', 'Consensus Buy Signals', registry=self.registry)
        self.consensus_sell = Gauge('aegis_consensus_sell_signals', 'Consensus Sell Signals', registry=self.registry)
        self.consensus_neutral = Gauge('aegis_consensus_neutral_signals', 'Consensus Neutral Signals', registry=self.registry)

        # Risk Metrics
        self.leverage_ratio = Gauge('aegis_leverage_ratio', 'Leverage Ratio', registry=self.registry)
        self.risk_budget_used = Gauge('aegis_risk_budget_used', 'Risk Budget Used %', registry=self.registry)
        self.portfolio_delta = Gauge('aegis_portfolio_delta', 'Portfolio Delta', registry=self.registry)
        self.portfolio_gamma = Gauge('aegis_portfolio_gamma', 'Portfolio Gamma', registry=self.registry)
        self.portfolio_vega = Gauge('aegis_portfolio_vega', 'Portfolio Vega', registry=self.registry)
        self.portfolio_theta = Gauge('aegis_portfolio_theta', 'Portfolio Theta', registry=self.registry)

        # System Health Metrics
        self.api_latency_p95 = Gauge('aegis_api_latency_p95', 'API Latency p95 (ms)', registry=self.registry)
        self.api_latency_p99 = Gauge('aegis_api_latency_p99', 'API Latency p99 (ms)', registry=self.registry)
        self.cache_hit_rate = Gauge('aegis_cache_hit_rate', 'Cache Hit Rate %', registry=self.registry)
        self.error_rate = Gauge('aegis_error_rate', 'Error Rate %', registry=self.registry)
        self.requests_per_sec = Gauge('aegis_requests_per_sec', 'Requests per Second', registry=self.registry)

    def generate_and_push_metrics(self):
        """Generate synthetic data and push to Prometheus"""
        self.iteration += 1

        # Update prices with small random walk
        self.btc_price += random.uniform(-500, 500)
        self.eth_price += random.uniform(-50, 50)

        # Fund Health
        total_capital = random.uniform(900000, 1200000)
        daily_pnl = random.uniform(-50000, 100000)

        self.total_capital.set(total_capital)
        self.daily_pnl.set(daily_pnl)
        self.sharpe_ratio.set(random.uniform(0.5, 3.0))
        self.max_drawdown.set(random.uniform(0.05, 0.25))
        self.var_99.set(random.uniform(0.05, 0.15))
        self.btc_price_gauge.set(self.btc_price)
        self.eth_price_gauge.set(self.eth_price)

        # Strategy Performance
        self.touche_eqs_score.set(random.uniform(40, 80))
        self.fundamental_score.set(random.uniform(30, 100))
        self.quantum_pnl.set(random.uniform(-50000, 100000))
        self.quantum_volume.set(random.uniform(100000, 5000000))
        self.sentinel_multiplier.set(random.uniform(0.1, 1.0))
        self.vix_level.set(random.uniform(12, 40))
        self.dxy_level.set(random.uniform(100, 110))
        self.fear_greed.set(random.randint(20, 90))
        self.consensus_buy.set(random.randint(0, 15))
        self.consensus_sell.set(random.randint(0, 15))
        self.consensus_neutral.set(random.randint(5, 20))

        # Risk Metrics
        self.leverage_ratio.set(random.uniform(1.0, 5.0))
        self.risk_budget_used.set(random.uniform(30, 95))
        self.portfolio_delta.set(random.uniform(-0.5, 0.5))
        self.portfolio_gamma.set(random.uniform(0.001, 0.1))
        self.portfolio_vega.set(random.uniform(-1000, 1000))
        self.portfolio_theta.set(random.uniform(-5000, 5000))

        # System Health
        self.api_latency_p95.set(random.uniform(10, 100))
        self.api_latency_p99.set(random.uniform(20, 200))
        self.cache_hit_rate.set(random.uniform(50, 99))
        self.error_rate.set(random.uniform(0, 5))
        self.requests_per_sec.set(random.randint(100, 1000))

        # AEGIS v7.2: Pushgateway gecici baglanti sorunlari icin retry uygulanir.
        push_error = None
        for attempt in range(3):
            try:
                push_to_gateway(
                    PUSHGATEWAY_URL,
                    job='aegis_trading',
                    registry=self.registry
                )
                timestamp = datetime.now().strftime("%H:%M:%S")
                logger.info(f"✅ Cycle #{self.iteration} - {timestamp}: Metrics pushed to Prometheus")
                print(f"✅ Metrics pushed | Capital: ${total_capital:,.0f} | PnL: ${daily_pnl:,.0f}")
                push_error = None
                break
            except Exception as e:  # noqa: BLE001
                push_error = e
                logger.warning("Push attempt %d failed: %s", attempt + 1, e)
                if attempt < 2:
                    time.sleep(2 ** attempt)

        if push_error is not None:
            logger.error(f"❌ Failed to push metrics after retries: {push_error}")

def main():
    """Main entry point"""
    print("\n" + "="*70)
    print("  AEGIS HOLDING - PROMETHEUS METRICS PUSHER")
    print("  Generating synthetic data and pushing to Prometheus...")
    print("="*70 + "\n")

    pusher = PrometheusMetricsPusher()

    try:
        while True:
            pusher.generate_and_push_metrics()
            time.sleep(10)  # Push every 10 seconds
    except KeyboardInterrupt:
        print("\n\n✅ Metrics pusher stopped")

if __name__ == "__main__":
    main()
