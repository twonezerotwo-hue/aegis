# AEGIS Cleanup Phase 4

## What Was Added

- New safe router: `dashboard_react/backend/routes/aegis_core_routes.py`
- New signal-only endpoints:
  - `GET /aegis-core/health`
  - `POST /aegis-core/signal`
  - `POST /aegis-core/backtest-evidence`
- Minimal router registration in `dashboard_react/backend/main.py`
- New lightweight route tests:
  - `tests/test_aegis_core_routes.py`

## What Was Intentionally Left Unchanged

- Old runtime endpoints were not removed.
- Old consensus runtime still exists as-is:
  - `/signal`
  - `/process`
  - `/execute`
  - old backtest routes
  - old paper trading routes
  - old optimizer routes
- No broker, paper-trading, optimizer, bounded-updater, final allocator, or position optimizer logic was imported into the new safe routes.

## Why The New `aegis_core` Routes Are Safer

- They call only the sidecar `aegis_core` package.
- They return `SIGNAL_ONLY_NOT_FINAL` or `EVIDENCE_ONLY_NOT_FINAL`.
- They do not emit `action`.
- They do not emit `position_size`.
- They do not emit order, broker, or execution fields.
- Unknown regime and missing-module conditions surface as warnings instead of silently mutating into final trade intent.
- Backtest evidence is wrapped only as evidence and does not simulate trades in this phase.

## How E-yAy / BrainChain Should Call The New Endpoints

1. Use `GET /aegis-core/health` as the liveness and capability check for the safe AEGIS Core API surface.
2. Use `POST /aegis-core/signal` as the integration entrypoint for module-score aggregation and BrainChain-facing signal normalization.
3. Consume:
   - `aegis_signal` for AEGIS-native signal metadata
   - `brainchain_signal` for downstream BrainChain adapter shape
4. Treat warnings as first-class integration signals and route them into the future Data Integrity Gate.
5. Use `POST /aegis-core/backtest-evidence` only for evidence packaging, not for trade simulation or execution decisions.

## Remaining Old-Runtime Risks From Phase 3

- `consensus_engine/main.py` still emits final decision fields in old endpoints.
- `dashboard_react/backend/main.py` still exposes `/execute`.
- `dashboard_react/backend/routes/backtest_routes.py` still includes simulated trade execution, Kelly-style sizing, and fallback trade injection.
- `dashboard_react/backend/routes/paper_trading.py` remains active.
- Optimizer and bounded-updater mutation paths remain present in legacy runtime.
- Silent fallback behavior remains in several old routes and strategy services.

## Next Step

Phase 5: Data Integrity Gate integration.
