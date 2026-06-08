# AEGIS Module Registry Report

Date: 2026-06-08

## What Changed

Added `aegis_platform.modules`:

- `contract.py`: `ModuleManifest`, `ModuleState`, `DataSafety`.
- `registry.py`: central registry, dependency/status resolution, default AEGIS manifests.
- `health.py`: combined module health helper.
- `loader.py`: structured lazy import helper.
- `errors.py`: manifest/registry exceptions.

Added API routes:

- `GET /api/system/modules`
- `GET /api/system/modules/{module_id}`
- `GET /api/system/health/full`

## Behavior

The registry returns dashboard-safe structured statuses:

- `HEALTHY`
- `DEGRADED_MODULE`
- `MISSING_MODULE`
- `DISABLED_MODULE`
- `UNAVAILABLE_PROVIDER`
- `FAILED`

Optional module failures do not crash the dashboard. Required module failures mark the system `FAILED`.

## Active vs Optional Modules

Required:

- `core.signal`
- `dashboard.backend`
- `dashboard.frontend`

Optional/removable:

- `research.catalog`
- `agent.orchestrator`
- `consensus.engine`
- `analyzer.ai`
- `sentinel.macro`
- `backtest.evidence`
- `news.sentiment`

Legacy/disabled by default:

- `optimizer.legacy`
- `paper.legacy`

## Safety

`ModuleManifest` rejects `can_emit_execution=true`. Output contracts reject forbidden fields such as `action`, `order`, `broker`, `execution`, and `position_size`.

## Tests

Added:

- `tests/test_platform_registry.py`
- `dashboard_react/backend/tests/test_system_routes.py`

## Remaining Risks

- Current default manifests are static. Later phases can load JSON manifests from module folders.
- External service health is represented as endpoint metadata; no network probe is done inside the registry yet.
