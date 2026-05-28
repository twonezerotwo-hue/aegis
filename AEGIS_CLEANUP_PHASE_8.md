# AEGIS Cleanup Phase 8

## What Was Added

- Integration contract document:
  - `docs/EYAY_BRAINCHAIN_AEGIS_INTEGRATION_CONTRACT.md`
- Legacy isolation document:
  - `docs/LEGACY_ENDPOINT_ISOLATION.md`
- Machine-readable integration manifest:
  - `aegis_core/integration_manifest.json`
- New integration contract tests:
  - `tests/test_eyay_integration_contract.py`

## Integration Contract Summary

- `/aegis-core/*` is now the only approved AEGIS integration surface for E-yAy / BrainChain.
- Approved routes are:
  - `GET /aegis-core/health`
  - `POST /aegis-core/signal`
  - `POST /aegis-core/backtest-evidence`
- The contract explicitly forbids legacy decision, execution, paper-trading, optimizer, and bounded-updater paths.
- The contract also freezes the safety boundary:
  - no `action`
  - no `position_size`
  - no order, broker, or execution fields
  - `final_decision = false`

## Legacy Isolation Summary

- Phase 3 risky surfaces were documented again in a dedicated isolation note for downstream integration work.
- The old runtime remains untouched for compatibility only.
- E-yAy is explicitly instructed not to call:
  - legacy `/signal`
  - legacy `/process`
  - `/execute`
  - paper trading routes
  - optimizer routes
  - bounded updater paths
  - execution engine paths

## How E-yAy Should Use AEGIS

- E-yAy should treat `aegis_core` as a signal-only subsystem.
- E-yAy should call only the approved `/aegis-core/*` routes.
- E-yAy may apply stronger outer data-integrity, risk, kill-switch, audit, and execution policy on top of AEGIS.
- Actual execution control remains outside AEGIS.

## Remaining Next Step

Optional legacy endpoint deprecation or a full E-yAy gateway service.
