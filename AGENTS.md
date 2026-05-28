# AGENTS.md — AEGIS / E-yAy Coding Rules

## Project status

This repository contains legacy AEGIS plus a cleaned signal-only `aegis_core`.

Current safe integration surface:

- `GET /aegis-core/health`
- `POST /aegis-core/signal`
- `POST /aegis-core/backtest-evidence`

`aegis_core` is signal-only. It must never become an execution engine.

## Non-negotiable rules

- Do not create final investment decisions.
- Do not emit final `buy`, `sell`, `hold`, `rebalance`, or execution commands.
- Do not emit `action`, `position_size`, `order`, `broker`, or `execution` fields from safe paths.
- Do not call broker, paper trading, optimizer, bounded updater, or execution engine from `aegis_core`.
- Do not silently fallback.
- Do not fake fresh timestamps with `Date.now()` when source timestamps are missing.
- Do not show fallback/mock/static data as live or verified.
- Do not remove existing legacy runtime unless explicitly requested.
- Do not run Docker unless explicitly requested.
- Do not modify unrelated files.

## Current architecture

Legacy AEGIS still exists and may contain old decision/execution behavior.

Safe core:

Data Integrity Gate
→ AEGIS Core Signal
→ BrainChain Adapter
→ Risk Engine Wrapper
→ Kill Switch Wrapper
→ OwnerBrief
→ Audit Record
→ NO EXECUTION

## Safe package

Use `aegis_core` for safe signal-only behavior.

Do not import these into safe paths:

- `strategies/execution_engine.py`
- `dashboard_react/backend/routes/paper_trading.py`
- `macro_bridge/run.py`
- `consensus_engine/src/final_allocator.py`
- `consensus_engine/src/position_optimizer.py`
- `consensus_engine/src/bounded_updater.py`
- `optimizer_service/`

## Dashboard rules

Dashboard must visibly label data freshness:

- `LIVE`
- `RECENT`
- `STALE`
- `FALLBACK`
- `PARTIAL_FALLBACK`
- `MOCK`
- `MISSING`
- `UNKNOWN`

Fallback macro data is not verified live market data.

Known fallback source:

- `dashboard_react/backend/routes/macro.py`
- `_FALLBACK_METRICS`

Known hardcoded fallback values:

- DXY `98.5`
- VIX `22.0`
- US10Y `4.25`
- Brent `92.0`
- XAU `4800`
- BTC.D `59.8`
- USDT.D `7.5`
- regime `NORMALIZATION`

These must never be displayed as verified live data.

## Testing

Prefer targeted tests only.

Useful commands:

python -m py_compile dashboard_react/backend/routes/macro.py
pytest aegis_core/tests
pytest tests/test_aegis_core_routes.py
pytest tests/test_eyay_integration_contract.py
cd dashboard_react/frontend
npm run build

## Response style for Codex

When completing a task, return only:

- files changed
- tests run
- result
- remaining blockers

Do not write long reports unless explicitly requested.
