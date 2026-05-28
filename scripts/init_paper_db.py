#!/usr/bin/env python3
"""Initialize Paper Trading Database and Account"""

import sys
import os
import logging

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'strategies'))

from paper_trader.database import PaperTradingDB
from paper_trader.engine import PaperTrader
from paper_trader.account import PaperAccount

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_paper_trading():
    """Initialize paper trading system"""

    logger.info("=" * 60)
    logger.info("AEGIS HOLDING - PAPER TRADING INITIALIZATION")
    logger.info("=" * 60)

    # Initialize database
    logger.info("\n📊 Initializing database...")
    db = PaperTradingDB()
    logger.info("✅ Database ready")

    # Initialize account
    logger.info("\n💰 Initializing account...")
    account = PaperAccount(initial_capital=100000.0)
    logger.info(f"✅ Account initialized with $100,000")

    # Initialize trading engine
    logger.info("\n🤖 Initializing trading engine...")
    trader = PaperTrader(initial_capital=100000.0)
    logger.info("✅ Trading engine ready")

    # Print configuration
    logger.info("\n" + "=" * 60)
    logger.info("CONFIGURATION")
    logger.info("=" * 60)
    logger.info(f"Initial Capital:      $100,000 USDT")
    logger.info(f"Trading Pair:         BTC/USDT")
    logger.info(f"Position Size:        5% of cash (min $100, max $10k)")
    logger.info(f"Trading Fee:          0.1%")
    logger.info(f"Signal Source:        Consensus Engine (port 8005)")
    logger.info(f"Update Frequency:     60 seconds")
    logger.info(f"Database Location:    {db.db_path}")

    logger.info("\n" + "=" * 60)
    logger.info("✅ PAPER TRADING SYSTEM READY")
    logger.info("=" * 60)

    logger.info("\nNext steps:")
    logger.info("1. Open dashboard: http://localhost:8501")
    logger.info("2. Go to Paper Trading tab")
    logger.info("3. Click 'Run Cycle' to execute trades based on Consensus signals")
    logger.info("4. Monitor: Equity Curve, Recent Trades, Statistics")

    return trader


if __name__ == "__main__":
    init_paper_trading()
