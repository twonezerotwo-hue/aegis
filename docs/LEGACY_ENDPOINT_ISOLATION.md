# Legacy Endpoint Isolation

## Scope

This document captures the legacy AEGIS runtime surfaces that remain active for compatibility but are not approved for E-yAy / BrainChain integration.

## Known Old Risky Endpoints And Files

High-risk legacy routes and files identified in Phase 3 include:

- `consensus_engine/main.py`
  - `GET /signal`
  - `POST /process`
  - `POST /consensus/weights`
  - `POST /consensus/feedback/trade`
  - `POST /bounded_updater/update`
- `dashboard_react/backend/main.py`
  - `POST /execute`
  - `GET /api/dashboard`
  - legacy `/backtest/*` paths
  - optimizer control routes
- `dashboard_react/backend/routes/paper_trading.py`
  - `/api/paper/*`
- `dashboard_react/backend/routes/backtest_routes.py`
  - legacy simulated-trade backtest routes
- `dashboard_react/backend/routes/dashboard.py`
  - legacy consensus routes returning directional fields
- `dashboard_react/backend/routes/stream.py`
  - live-feed payloads with legacy decision semantics
- `optimizer_service/main.py`
- `optimizer_service/src/backtest_engine.py`
- `consensus_engine/src/final_allocator.py`
- `consensus_engine/src/position_optimizer.py`
- `consensus_engine/src/bounded_updater.py`
- `strategies/execution_engine.py`
- `shared/proto/signals.proto` order and execution service definitions

## Why These Surfaces Remain Untouched

- Backward compatibility for the current runtime was preserved during cleanup.
- The cleanup phases focused first on building a safe sidecar surface instead of rewriting the old system in place.
- Existing UI, research, dashboard, and legacy orchestration paths still depend on these surfaces.
- The quarantine-first approach reduced risk by isolating unsafe code before deactivation.

## Why E-yAy Must Not Call Them

- Many of these paths emit `action`, `position_size`, or trading-direction fields.
- Several paths connect to execution-like, broker-like, paper-trading, or optimizer-mutation logic.
- Multiple routes still contain silent fallback behavior that can continue after missing or degraded data.
- These routes do not honor the final `aegis_core` signal-only contract.
- They violate the BrainChain rule that final execution control remains outside AEGIS.

## Future Deprecation Plan

1. Keep legacy routes active only for current compatibility while E-yAy migrates to `/aegis-core/*`.
2. Move all E-yAy callers to:
   - `GET /aegis-core/health`
   - `POST /aegis-core/signal`
   - `POST /aegis-core/backtest-evidence`
3. Mark legacy decision and execution surfaces as unsupported for new integrations.
4. Add deployment-time gating so BrainChain-facing environments do not expose:
   - `/execute`
   - paper trading routes
   - optimizer apply / rollback surfaces
   - bounded updater surfaces
5. After migration, deprecate or disable legacy decision endpoints in a dedicated shutdown phase.

## Quarantine References

Quarantined copies for unsafe or sensitive runtime areas already exist under:

- `quarantine/execution/strategies/execution_engine.py`
- `quarantine/paper_trading/dashboard_react/backend/routes/paper_trading.py`
- `quarantine/orchestration/macro_bridge/run.py`
- `quarantine/portfolio_decision/consensus_engine/src/final_allocator.py`
- `quarantine/portfolio_decision/consensus_engine/src/position_optimizer.py`
- `quarantine/optimizer/consensus_engine/src/bounded_updater.py`
- `quarantine/optimizer/optimizer_service/main.py`
- `quarantine/optimizer/optimizer_service/src/backtest_engine.py`
- `quarantine/broken_paths/strategies/sentinel_ai/src/macro_indicators/crypto_specific.py`

## Approved Integration Reminder

`/aegis-core/*` remains the only approved AEGIS integration surface for E-yAy / BrainChain.
