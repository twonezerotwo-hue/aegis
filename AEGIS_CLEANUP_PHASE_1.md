# AEGIS Cleanup Phase 1

## Summary

Phase 1 created quarantine and archive folders and copied the highest-risk decision, execution, optimizer, paper-trading, orchestration, and broken-path files into quarantine for controlled review.

Created folders:

- `quarantine/`
- `quarantine/execution/`
- `quarantine/portfolio_decision/`
- `quarantine/optimizer/`
- `quarantine/paper_trading/`
- `quarantine/orchestration/`
- `quarantine/broken_paths/`
- `archive/`
- `archive/reports/`
- `archive/monitoring/`
- `archive/dashboard_ui/`

Copied files:

- `strategies/execution_engine.py`
- `dashboard_react/backend/routes/paper_trading.py`
- `macro_bridge/run.py`
- `consensus_engine/src/final_allocator.py`
- `consensus_engine/src/position_optimizer.py`
- `consensus_engine/src/bounded_updater.py`
- `optimizer_service/main.py`
- `optimizer_service/src/backtest_engine.py`
- `strategies/sentinel_ai/src/macro_indicators/crypto_specific.py`

## What Was Not Done

- Original files were not moved.
- Original files were not deleted.
- Existing imports were not edited.
- Existing endpoints were not removed.
- Runtime wiring was not changed.
- Docker was not run.
- The app was not rewritten.

## Risks Isolated

- Execution risk from direct trade execution code.
- Paper-trading risk from trade-like endpoints and account flow.
- Final-decision risk from allocator/orchestration logic.
- Position-sizing risk from portfolio optimizer paths.
- Optimizer/config-drift risk from weight-updating services.
- Broken-path risk from the Sentinel macro indicator file with confirmed syntax failure.

## Next Steps

1. Create an `aegis_core` package.
2. Move only signal-generation, consensus scoring, confluence, regime-aware weighting, schema validation, and backtest-safe code into that new boundary.
3. Define a strict output contract that returns `SIGNAL_ONLY_NOT_FINAL`.
4. Keep execution, risk engine, kill switch, audit, owner brief, and execution control outside AEGIS Core for later BrainChain integration.
5. Review silent fallback paths before any import rewiring.

## Reminder

AEGIS Core must return `SIGNAL_ONLY_NOT_FINAL`.
