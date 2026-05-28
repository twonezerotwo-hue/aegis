# AEGIS Cleanup Phase 6

## What Was Added

- New risk wrapper package:
  - `aegis_core/risk/__init__.py`
  - `aegis_core/risk/risk_engine.py`
  - `aegis_core/risk/kill_switch.py`
- Extended `POST /aegis-core/signal` to accept:
  - `risk_context`
  - `kill_switch_context`
- Added top-level `risk_result` and `kill_switch_result` to the safe route response
- Added lightweight tests:
  - `aegis_core/tests/test_risk_engine.py`
  - `aegis_core/tests/test_kill_switch.py`
  - `tests/test_aegis_core_risk_routes.py`

## How The Risk Engine Wrapper Works

- The risk wrapper runs after safe AEGIS Core signal generation when the Data Integrity Gate allows signal construction.
- It can also evaluate a blocked state when data integrity has already failed.
- It never emits `action`, `position_size`, order, broker, or execution fields.
- It returns only:
  - `status`
  - `hard_block`
  - `warnings`
  - `decision_permission = RISK_ENGINE_ONLY_NOT_FINAL`
  - `final_decision = false`

## How The Kill Switch Wrapper Works

- The kill switch runs after the risk wrapper.
- It can turn `ON` because of:
  - Data Integrity Gate hard block
  - Risk Engine hard block
  - manual kill switch
  - broker API error flag
  - unexpected correlation break flag
  - backtest timestamp violation flag
  - system integrity error flag
- It does not execute anything. It only reports a non-final block state.
- It returns only:
  - `status`
  - `hard_block`
  - `warnings`
  - `decision_permission = KILL_SWITCH_ONLY_NOT_FINAL`
  - `final_decision = false`

## PASS / DEGRADED_PASS / BLOCK Behavior

- `PASS`
  - Safe data integrity result
  - No hard risk conditions
  - Kill switch remains `OFF`
  - Route returns `SIGNAL_ONLY_NOT_FINAL`

- `DEGRADED_PASS`
  - Missing `risk_context`
  - Volatility spike without harder breach conditions
  - Signal still returns, but warnings are propagated

- `BLOCK`
  - Data integrity fail
  - contradiction score above threshold
  - daily or weekly loss breach
  - correlation break
  - stablecoin depeg
  - exchange outage
  - critical risk breach
  - kill switch activation conditions
  - Route returns `blocked = true`, `final_decision = false`, and never emits trade/execution intent

## How This Matches E-yAy / BrainChain Rules

- The wrapper sits only on the new safe `/aegis-core/signal` surface.
- Legacy endpoints remain unchanged.
- The route still does not produce buy, sell, hold, or sizing outputs.
- The Risk Engine and Kill Switch are guardrails, not decision engines.
- This keeps AEGIS Core signal-only while giving E-yAy / BrainChain a safer downstream integration contract.

## Remaining Next Step

Phase 7: OwnerBrief / Audit wrapper.
