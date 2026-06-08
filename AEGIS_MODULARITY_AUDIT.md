# AEGIS Modularity Audit

Date: 2026-06-08
Branch: codex/aegis-modular-upgrade

Scope: current checkout under `C:\Users\twone\Desktop\aegis_codex`.

## Summary

AEGIS already has partial modular safety: `aegis_core` is signal-only, legacy paper/optimizer routes are feature-flagged, macro data exposes field-level provenance, and `aegis_research` is separate from safe core. The main gap was lack of a central manifest/registry layer to show whether a capability is active, optional, disabled, missing, degraded, or legacy without crashing the dashboard.

This audit drove the first modular platform layer:

- `aegis_platform.modules`: manifest, registry, structured module health.
- `aegis_platform.providers`: provider manifest, credential/import status, no secret output.
- `/api/system/*` endpoints for dashboard-safe system visibility.

## Area Classification

| Area | Runtime class | Dashboard/API facing | Safe signal-only | Unsafe execution-like | Optional/mandatory | Removable safely | Tested | Manifest | Health | Fallback | Provenance |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|
| `aegis_core` | active runtime | yes | yes | no | mandatory | no | yes | yes | yes | block/degrade | yes |
| `aegis_research` | research-only | yes | yes | no | optional | yes | yes | yes | partial | degrade | partial |
| `aegis_platform` | active metadata runtime | yes | yes | no | mandatory for new status API | yes | yes | yes | yes | degrade | yes |
| `dashboard_react/backend` | active runtime | yes | mixed | legacy guarded | mandatory | no | yes | yes | yes | degrade | partial |
| `dashboard_react/frontend` | active runtime | yes | display-only | optimizer removed from active Backtest V2 | mandatory | no | partial | planned | yes via backend | UI degrade | partial |
| `consensus_engine` | active/legacy service | yes | mixed | may contain final allocator/optimizer legacy modules | optional service | yes if dashboard degrades | partial | yes | external health | degrade | partial |
| analyzer / analyzer-ai | optional service | yes | report-only | no direct safe-core execution | optional | yes | partial | yes | external health | degrade | partial |
| sentinel | optional risk/macro service | yes | risk evidence | no direct broker route | optional | yes | partial | yes | external health | fallback/degrade | yes |
| `macro_bridge` | legacy/research UI | no default dashboard need | no | possible legacy bridge behavior | optional | yes | no | planned | partial | disable | partial |
| `optimizer_service` | legacy/research | previously dashboard-facing | no | can mutate weights/config | optional legacy | yes | partial | yes | external health | disable | no |
| `strategies` | legacy/research/runtime mix | indirect | mixed | execution/order modules exist | optional except imported services | risky without audit | partial | partial | partial | partial | partial |
| `modules/news-ai-limited` | optional data service | yes | evidence-only | no direct broker path | optional | yes | partial | yes | external health | degrade | partial |
| `backtest` | research/evidence | yes | evidence-only | no broker in safe path | optional | yes | partial | yes | route health | degrade | partial |
| `docs` | documentation | no | yes | no | optional | yes | no | n/a | n/a | n/a | n/a |
| `tests` | test suite | no | yes | no | mandatory for release | no | n/a | n/a | n/a | n/a | n/a |
| `docker-compose.yml` | runtime orchestration | yes | n/a | may run legacy optional services | mandatory for Docker stack | partial | config-only | planned | Docker health | profiles | partial |
| Dockerfiles | runtime build | no | n/a | service dependent | mandatory for Docker builds | no | build-dependent | planned | n/a | n/a | n/a |
| `scripts` | maintenance | no | mixed | cleanup/build scripts only | optional | yes | partial | planned | n/a | n/a | n/a |
| `archive` | not present | no | n/a | n/a | optional missing | yes | n/a | missing | missing | n/a | n/a |
| `quarantine` | not present | no | n/a | n/a | optional missing | yes | n/a | missing | missing | n/a | n/a |

## Unsafe / Legacy-Like Surfaces To Keep Isolated

- `dashboard_react/backend/routes/paper_trading.py`
- `dashboard_react/backend/routes/paper_autotrader_routes.py`
- `dashboard_react/backend/routes/optimizer_agent_routes.py`
- `optimizer_service/`
- `strategies/execution_engine.py`
- `strategies/quantum_ai/src/execution/order_router.py`
- `macro_bridge/executor/trade_executor.py`
- `consensus_engine/src/final_allocator.py`
- `consensus_engine/src/position_optimizer.py`
- `consensus_engine/src/bounded_updater.py`

## Required Modules

- `core.signal`
- `dashboard.backend`
- `dashboard.frontend`

If required modules are missing, `/api/system/health/full` reports `FAILED` instead of raw traceback.

## Optional / Removable Modules

- `research.catalog`
- `agent.orchestrator`
- `consensus.engine`
- `analyzer.ai`
- `sentinel.macro`
- `backtest.evidence`
- `optimizer.legacy`
- `paper.legacy`
- `news.sentiment`

Optional missing modules should produce `DEGRADED_MODULE`, `MISSING_MODULE`, or `DISABLED_MODULE`.

## Current Gaps

- Some legacy paths still contain execution-like terms and must remain feature-flagged.
- Docker external network naming still references an old network for compatibility.
- Provider registry currently reports capability/credential/import status; it does not fetch provider data itself.
- Macro route still uses existing market data fetcher internally, with provider registry status added as metadata.
