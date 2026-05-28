# QUARANTINE_NOTES

- Date: 2026-04-30
- Purpose: Non-destructively isolate unsafe AEGIS paths before E-yAy / BrainChain integration while keeping the current app runnable.
- Scope: Create quarantine/archive folders, copy high-risk files into quarantine, and document why they are unsafe for a future `SIGNAL_ONLY_NOT_FINAL` AEGIS Core.

## Copied Files

| Original File | Quarantine Copy | Why Quarantined | Execution Risk | Sizing Risk | Final Decision Risk | Optimizer Risk | Silent Fallback Risk | Broken Syntax Risk |
|---|---|---|---|---|---|---|---|---|
| `strategies/execution_engine.py` | `quarantine/execution/strategies/execution_engine.py` | Direct order execution bridge. AEGIS Core must not execute trades. | Yes | No | No | No | No | No |
| `dashboard_react/backend/routes/paper_trading.py` | `quarantine/paper_trading/dashboard_react/backend/routes/paper_trading.py` | Paper-trading endpoints still represent a trading surface and should be isolated from core signal logic. | Yes | Yes | Yes | No | Possible | No |
| `macro_bridge/run.py` | `quarantine/orchestration/macro_bridge/run.py` | Cross-system orchestration combines macro, consensus, validation, and decision-style flow that belongs above AEGIS Core. | No | Yes | Yes | No | Possible | No |
| `consensus_engine/src/final_allocator.py` | `quarantine/portfolio_decision/consensus_engine/src/final_allocator.py` | Converts upstream scores into final portfolio decisions, which violates the future signal-only boundary. | No | Yes | Yes | No | No | No |
| `consensus_engine/src/position_optimizer.py` | `quarantine/portfolio_decision/consensus_engine/src/position_optimizer.py` | Handles position sizing and portfolio optimization that should move to BrainChain-side risk/execution layers. | No | Yes | Yes | Yes | No | No |
| `consensus_engine/src/bounded_updater.py` | `quarantine/optimizer/consensus_engine/src/bounded_updater.py` | Updates weights/config at runtime and introduces optimizer/config-drift behavior inside the current decision stack. | No | No | Indirect | Yes | Possible | No |
| `optimizer_service/main.py` | `quarantine/optimizer/optimizer_service/main.py` | Optimizer service can apply and roll back weights, which is unsafe to keep near a future signal-only core. | No | Yes | Indirect | Yes | Possible | No |
| `optimizer_service/src/backtest_engine.py` | `quarantine/optimizer/optimizer_service/src/backtest_engine.py` | Synthetic backtest path feeds optimizer behavior and is not a safe canonical source for integration. | No | Yes | Indirect | Yes | Possible | No |
| `strategies/sentinel_ai/src/macro_indicators/crypto_specific.py` | `quarantine/broken_paths/strategies/sentinel_ai/src/macro_indicators/crypto_specific.py` | Confirmed broken path with syntax failure, unsafe for later extraction until repaired or retired. | No | No | No | No | No | Yes |

## Notes

- Quarantine in this phase is non-destructive.
- Original files remain in their current locations.
- No imports were changed.
- No endpoints were removed.
- No runtime behavior was intentionally changed in this phase.

## Next Planned Step

Create an `aegis_core` package that exposes only signal, confluence, schema, regime, and backtest capabilities and returns `SIGNAL_ONLY_NOT_FINAL`.
