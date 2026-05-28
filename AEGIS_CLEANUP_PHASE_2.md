# AEGIS Cleanup Phase 2

## What Was Created

- New sidecar package: `aegis_core/`
- Copied safe weight config: `aegis_core/config/consensus_weights.yaml`
- New signal-only engine modules:
  - `aegis_core/engine/regime_weights.py`
  - `aegis_core/engine/confluence.py`
  - `aegis_core/engine/consensus.py`
  - `aegis_core/engine/backtest.py`
- BrainChain-facing adapter:
  - `aegis_core/adapters/brainchain_adapter.py`
- Schemas:
  - `aegis_core/schemas/aegis_signal.schema.json`
  - `aegis_core/schemas/aegis_backtest.schema.json`
- Lightweight tests:
  - `aegis_core/tests/test_regime_weights.py`
  - `aegis_core/tests/test_confluence.py`
  - `aegis_core/tests/test_consensus.py`
  - `aegis_core/tests/test_brainchain_adapter.py`

## What Was Intentionally Not Touched

- Existing runtime imports were not changed.
- Existing endpoints were not removed.
- Old dashboard, orchestration, optimizer, execution, and paper-trading code was not deleted.
- Old app behavior was not intentionally modified.
- Docker was not run.

## How `aegis_core` Differs From Old AEGIS

- `aegis_core` is signal-only and does not emit final buy or sell actions.
- `aegis_core` does not return `position_size`.
- `aegis_core` does not include execution or broker intent.
- Regime fallback is explicit and warning-based instead of silent.
- Backtest support in this phase is evidence-only formatting, not a copied trade simulator.
- BrainChain integration is represented by a clean adapter contract rather than by reusing old orchestration code.

## Next Steps

1. Replace silent fallbacks in the old code paths with explicit warnings or fail-closed behavior.
2. Expand `aegis_core` with a safer extracted backtest layer after the current signal contract is validated.
3. Integrate `aegis_core` with the future E-yAy Data Integrity Gate.
4. Keep Risk Engine, Kill Switch, OwnerBrief, Audit, and Execution Control outside AEGIS Core.

## Reminder

AEGIS Core must return `SIGNAL_ONLY_NOT_FINAL`.
