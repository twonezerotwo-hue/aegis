# AEGIS Modular Upgrade Report

Date: 2026-06-08
Branch: codex/aegis-modular-upgrade

## What Changed

Added a modular platform metadata layer without enabling live trading or broker execution:

- `aegis_platform.modules`
- `aegis_platform.providers`
- JSON schemas for module/provider manifests.
- System routes under `/api/system`.
- Extended external repo matrix with research-only safety fields.
- Removed active Backtest V2 optimizer panel rendering.

## New Endpoints

- `GET /api/system/modules`
- `GET /api/system/modules/{module_id}`
- `GET /api/system/providers`
- `GET /api/system/health/full`
- Existing `GET /api/agent/research/external-repo-matrix` now returns:
  - `research_only: true`
  - `affects_signals: false`
  - `affects_execution: false`
  - `safe_integration_level`

## Module Registry Behavior

Modules are detachable through manifest metadata. Missing optional modules return structured state instead of crashing. Legacy optimizer and paper runtime are marked disabled in the default safe runtime.

## Provider Registry Behavior

Providers report capability, credentials, optional package availability, timestamp rules, and fallback behavior. Secret values are never returned.

## Removable Modules

Safely removable/degradable:

- research catalog
- agent orchestrator
- consensus service
- analyzer service
- sentinel service
- backtest evidence routes
- news sentiment service
- optimizer legacy service
- paper legacy runtime

Required:

- AEGIS core signal surface
- dashboard backend
- dashboard frontend

## Runtime Safety

No live trading was enabled. No broker execution was added. No API keys or secrets were exposed. The optimizer panel was removed from the active Backtest V2 page.

## Runtime Verification

- `http://localhost:8502/health`: 200, dashboard backend healthy.
- `http://localhost:8005/health`: 200, consensus healthy.
- `http://localhost:8007/health`: 200, analyzer healthy.
- `http://localhost:3001`: 200.
- `http://localhost:3001/v2`: 200.
- `http://localhost:8502/api/macro?horizon=medium`: 200, `data_status=LIVE`, `verified=true`, `fallback_fields=[]`.
- `http://localhost:8502/api/system/modules`: 200, structured module status, `system_status=DEGRADED` because optional service packages are not importable inside the dashboard container.
- `http://localhost:8502/api/system/providers`: 200, provider status only, no secrets.
- `http://localhost:8502/api/system/health/full`: 200, `system_status=DEGRADED`.

## Tests Added

- `tests/test_platform_registry.py`
- `tests/test_external_repo_matrix.py` updated
- `tests/test_dashboard_optimizer_disabled_static.py`
- `dashboard_react/backend/tests/test_system_routes.py`

## Tests Run

- `python -m py_compile ...`: passed for changed Python modules.
- `python -m pytest aegis_core/tests -v --tb=short`: 43 passed.
- `python -m pytest dashboard_react/backend/tests -v --tb=short`: 77 passed.
- `python -m pytest tests/test_platform_registry.py tests/test_external_repo_matrix.py tests/test_dashboard_optimizer_disabled_static.py dashboard_react/backend/tests/test_system_routes.py -q`: 13 passed.
- `node ./node_modules/typescript/lib/tsc.js --noEmit`: passed.
- `npm run build`: passed.
- `python -m pytest tests/test_v2_consistency.py -s -q`: V2 smoke output passed all field checks; pytest returns `no tests ran` because the file is an import-time smoke script.
- `python -m pytest tests -v --tb=short`: blocked by pytest capture cleanup after `tests/test_phase_2_5_validation.py` rewraps `sys.stdout`.
- `python -m pytest tests -v --tb=short -s`: ran 133 collected tests; all non-Touche-live-integration areas reached passing state, with 6 remaining failures isolated to `tests/test_touche_live_integration.py` and documented in `AEGIS_REMAINING_TECH_DEBT.md`.

## Remaining Risks

- This is metadata/registry phase, not full provider fetch refactor.
- Some legacy execution-like files still exist and must stay feature-flagged.
- Docker live containers were updated through controlled `docker cp` + restart for runtime verification; a clean image rebuild is still recommended for permanent deployment.
