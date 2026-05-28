# AEGIS Full System Audit Report

- Audit timestamp: `2026-05-01T22:53:08.8329347+03:00`
- Workspace: `C:\Users\twone\Desktop\aegis_codex`
- Audit mode: repository inspection, safe test execution, runtime probing, reporting only
- Change policy followed: no application code modified, no endpoints removed, no financial logic changed, no Docker teardown, no destructive actions

## 1. Executive Summary

### Overall conclusion

AEGIS is **not fully stable as an integrated live system today**, but it is **partially verified** at the code and targeted-test level.

- The **safe `aegis_core` sidecar** is in comparatively good shape. Its routes, wrappers, and signal-only contract are tested and currently respect the no-execution boundary.
- The **dashboard V2 provenance/fallback guard work** is materially improved in code. The frontend and backend now carry `data_status`, `verified`, `fallback_used`, `field_sources`, `fallback_fields`, and `module_sources` through the main V2 path.
- The **legacy runtime is still present and still dangerous**. Unsafe paths continue to expose `action`, `position_size`, paper-trading behavior, weight mutation, optimizer apply/rollback, and testnet execution entry points.
- The **live stack was not up during this audit**. `localhost:3001`, `127.0.0.1:8000`, `localhost:8502`, `localhost:8005`, and `localhost:8007` were all unavailable when probed. Because of that, the system is not end-to-end runtime-verified.

### Is AEGIS currently stable?

**Partially.**

- Stable at the **safe core contract** layer: yes, based on tests.
- Stable at the **dashboard provenance/fallback logic** layer: partially, based on static/backend tests and TypeScript compile.
- Stable as a **live integrated runtime**: no, not verified in this session because required services were down and legacy unsafe surfaces remain active in code.

### Which parts work?

- `aegis_core` signal-only engine, data gate, risk wrapper, kill switch, owner brief, and audit record.
- `/aegis-core/health`, `/aegis-core/signal`, `/aegis-core/backtest-evidence` implementation and contract tests.
- Dashboard V2 static provenance behavior:
  - macro fallback metadata
  - partial-fallback rendering
  - asset consensus provenance rendering
  - horizon-aware allocation behavior
- Frontend TypeScript compile (`tsc --noEmit`) passed.
- `dashboard_react/backend/routes/macro.py` compiles cleanly.

### Which parts are legacy?

- `dashboard_react/backend/main.py` legacy aggregate and `/execute`
- `dashboard_react/backend/routes/paper_trading.py`
- `consensus_engine/main.py` `/signal`, `/process`, `/bounded_updater/update`
- `consensus_engine/src/final_allocator.py`
- `consensus_engine/src/position_optimizer.py`
- `consensus_engine/src/bounded_updater.py`
- `optimizer_service/`
- `macro_bridge/run.py`
- `shared/proto/signals.proto`
- Root dashboard path `/` and its older SSE contract

### Which parts are unsafe or unverified?

- Unsafe:
  - `/execute`
  - `/api/paper/*`
  - `consensus-api /process`
  - `consensus-api /signal`
  - `optimizer-api`
  - `bounded_updater`
  - `macro_bridge`
  - `strategies/execution_engine.py`
- Unverified in this audit:
  - live `http://localhost:3001`
  - live `http://localhost:3001/v2`
  - live `http://127.0.0.1:8000/aegis-core/health`
  - live `http://localhost:8502/api/macro`
  - live `http://localhost:8502/api/live-feed`
  - live `http://localhost:8005/process`
  - live `http://localhost:8007/dashboard/exit_attribution`
  - Docker service orchestration state

### Which parts are tested?

- `aegis_core/tests` passed: `35/35`
- Route/contract tests passed:
  - `tests/test_aegis_core_routes.py`
  - `tests/test_aegis_core_data_gate_routes.py`
  - `tests/test_aegis_core_risk_routes.py`
  - `tests/test_aegis_core_ownerbrief_routes.py`
  - `tests/test_eyay_integration_contract.py`
- Dashboard backend static tests passed: `23/23`
  - macro fallback metadata
  - partial fallback rendering
  - asset consensus provenance
  - allocation horizon behavior
- Frontend type-check passed.

### Which parts are not tested?

- Full live `/v2` browser runtime with services actually up
- Full SSE behavior under real service data
- Full Docker stack runtime and healthchecks in this session
- End-to-end asset consensus for XAU/XAG/BOND/CASH against live upstreams
- End-to-end analyzer service output
- Legacy `/execute`, paper trading, optimizer mutation flows were intentionally not exercised

### Overall system status

**PARTIALLY VERIFIED**

Rationale:

- The safe core is verified by tests.
- The V2 provenance guard is partially verified by tests and static analysis.
- The live multi-service runtime is not verified because the required services were unavailable.
- Dangerous legacy execution/mutation surfaces still exist in active codepaths.

### Top 10 risks

1. `dashboard_react/backend/main.py` still exposes `/execute`, which reaches `strategies/execution_engine.py`.
2. `dashboard_react/frontend/src/services/apiV2.ts` still merges `consensus-api /process`, which emits `action` and `position_size`.
3. `consensus_engine/src/bounded_updater.py` and `optimizer_service/main.py` can mutate consensus weights.
4. `dashboard_react/backend/routes/paper_trading.py` still exposes paper-trading state mutations.
5. `dashboard_react/backend/services/sentinel_client.py` creates synthetic freshness timestamps with `datetime.now(...)`.
6. `dashboard_react/backend/routes/dashboard.py` contains mock/static endpoints that return fresh timestamps, which can overstate data freshness.
7. Non-crypto asset consensus (`XAU`, `XAG`, `BOND`, `CASH`) is gateway-derived from shared BTC macro context, not truly asset-native.
8. V1 dashboard SSE ignores the selected timeframe and strips `/USDT`, causing contract drift with what is displayed.
9. Macro fallback defaults differ between `/api/macro` and `/api/live-feed` normalization for `event_risk_score` and `hours_to_event`.
10. The Docker/runtime graph is large and fragile; the live services needed for `/v2` were down during this audit.

## 2. Repository Map

| Path | Role | Active or Legacy | Safe or Risky | Used by dashboard? | Used by AEGIS Core? | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| `aegis_core` | Safe signal-only package, data gate, wrappers, audit outputs | Active | Safe | Yes, via `/aegis-core/*` | Yes | Remain |
| `consensus_engine` | Legacy consensus runtime, `/process`, `/signal`, weight update logic | Active legacy | Risky | Yes | No | Refactor and isolate unsafe endpoints |
| `dashboard_react/backend` | FastAPI gateway for dashboard, macro route, stream route, safe core routes, legacy routes | Active mixed | Mixed-risk | Yes | Yes, hosts safe routes | Refactor |
| `dashboard_react/frontend` | React UI for legacy `/` and V2 `/v2` dashboards | Active mixed | Mixed-risk | Yes | No | Refactor and unify data sources |
| `macro_bridge` | Macro-to-decision/execution style bridge with position sizing and rebalance signal | Legacy | Risky | No direct current V2 use | No | Quarantine or deprecate |
| `modules` | Module container area, currently `news-ai-limited` | Active support | Mixed-risk | Indirectly | No | Remain, but standardize contracts |
| `strategies` | Service implementations for analyzer, cbr, fundamental, quantum, sentinel, touche; also execution engine | Active mixed | Mixed-risk to dangerous | Indirectly | No | Isolate execution pieces, keep analytics pieces |
| `optimizer_service` | Weight optimization API with apply/rollback | Active legacy | Dangerous | Optional/legacy dashboard use | No | Quarantine from user-facing stack |
| `backtest` | Backtest support utilities and historical data helpers | Active support | Mostly safe | Indirectly | No | Remain |
| `backtest_reports` | Generated backtest artifacts | Output/artifact | Safe | No | No | Remain |
| `audit_reports` | Prior repo audit documents | Artifact/doc | Safe | No | No | Remain |
| `shared` | Shared contracts and proto definitions, including execution-oriented proto | Shared legacy | Risky if used live | No direct | No | Refactor, split safe vs execution contracts |
| `scripts` | Utility scripts, init/health/event helpers | Active support | Mixed-risk | Indirectly | No | Remain, review individually |
| `grafana` | Observability provisioning and dashboards | Active infra | Safe operationally | No | No | Remain |
| `prometheus` | Metrics scraping config | Active infra | Safe operationally | Indirectly | No | Remain |
| `nginx` | Front-door reverse proxy config | Active infra | Safe operationally | Optional | No | Remain |
| `docker-compose.yml` | Full stack topology and service wiring | Active infra | Operationally risky due scope | Yes | Indirectly | Refactor into minimal and full profiles |
| `quarantine` | Containment area for broken/unsafe/orchestration/paper/optimizer/portfolio-decision code | Legacy containment | Safe if unused | No | No | Keep as quarantine |
| `archive` | Historical dashboard/monitoring/report assets | Legacy | Safe if unused | No | No | Keep archived |
| `docs` | Integration contracts, dashboard rules, endpoint isolation docs | Active docs | Safe | Yes | Yes | Remain |

## 3. Architecture Overview

### Current architecture summary

The repository contains **two overlapping architectures**:

1. A **safe sidecar path**:
   - `dashboard_react/backend/routes/aegis_core_routes.py`
   - `aegis_core/*`
   - signal-only, non-final, no execution

2. A **legacy decision/runtime path**:
   - `dashboard_react/backend/main.py`
   - `dashboard_react/backend/routes/dashboard.py`
   - `dashboard_react/backend/routes/stream.py`
   - `consensus_engine/main.py`
   - module services
   - optimizer/paper/execution surfaces

### High-level text diagram

```text
Frontend (:3001)
  -> API client (VITE_API_URL = http://localhost:8502)
    -> dashboard-backend (:8502)
      -> /api/dashboard              (legacy aggregate)
      -> /api/macro                  (macro gateway)
        -> sentinel-api (:8004)
      -> /api/consensus              (gateway consensus)
        -> prometheus (:9090)
        -> sentinel-api (:8004) for non-crypto proxy scoring
      -> /api/live-feed              (SSE aggregator)
        -> self /api/macro
        -> self /api/consensus
        -> consensus-api (:8005) /process /weights /consensus/historical_edge
        -> analyzer-ai (:8007) /dashboard/exit_attribution
      -> /aegis-core/*
        -> Data Integrity Gate
        -> AEGIS Core Signal
        -> BrainChain Adapter
        -> Risk Engine Wrapper
        -> Kill Switch Wrapper
        -> OwnerBrief
        -> Audit Record
        -> NO EXECUTION

Legacy decision path still present:
Frontend / backend
  -> /execute
    -> strategies/execution_engine.py
  -> consensus-api /process
    -> position sizing / final action / bounded updater
```

### Frontend dashboard

- Entry router: `dashboard_react/frontend/src/App.tsx`
- `/` renders legacy `Dashboard.tsx`
- `/v2` renders `DashboardV2.tsx`
- Default backend target from Vite env: `http://localhost:8502`

### Dashboard backend

- Main app: `dashboard_react/backend/main.py`
- Included routers:
  - `dashboard.router`
  - `aegis_core_routes.router`
  - `paper_trading.router`
  - `macro.router`
  - `stream.router`

### Consensus API

- File: `consensus_engine/main.py`
- Not safe-only
- Emits `action`, `position_size`, `green_light`, module weights, multi-timeframe outputs, and bounded-updater status

### Analyzer AI

- Docker service on `:8007`
- V2 uses it for exit attribution
- Live behavior not verified in this session because service was down

### Module services

- `touche-api` `:8001`
- `fundamental-api` `:8002`
- `quantum-api` `:8003`
- `sentinel-api` `:8004`
- `news-ai-limited` `:8006`

These either feed Prometheus, answer direct calls, or both.

### AEGIS Core sidecar

- Safe routes:
  - `GET /aegis-core/health`
  - `POST /aegis-core/signal`
  - `POST /aegis-core/backtest-evidence`
- Contract enforced by:
  - `aegis_core/integration_manifest.json`
  - `docs/EYAY_BRAINCHAIN_AEGIS_INTEGRATION_CONTRACT.md`

### Legacy decision paths

- `/execute` in `dashboard_react/backend/main.py`
- `/process`, `/signal`, `/weights`, `/bounded_updater/update` in `consensus_engine/main.py`
- `/api/paper/*` in `dashboard_react/backend/routes/paper_trading.py`
- `/optimizer/*` in `optimizer_service/main.py`
- `macro_bridge/run.py`

### SSE stream path

- Route: `dashboard_react/backend/routes/stream.py`
- Endpoint: `GET /api/live-feed`
- Aggregates macro, consensus, attribution, and weight data
- Also passes through unsafe fields such as `action` and `position_size`

### Docker service topology

Observed from `docker-compose.yml` and `docker compose config --services`:

- Infra:
  - `postgres` `5432`
  - `redis` `6379`
  - `clickhouse` `8123`, `9000`
  - `prometheus` `9090`
  - `grafana` `3000`
  - `qdrant` `6333`, `6334`
  - `pushgateway` `9091`
  - `nginx` `8080`
- Services:
  - `touche-api` `8001`
  - `fundamental-api` `8002`
  - `quantum-api` `8003`
  - `sentinel-api` `8004`
  - `consensus-api` `8005`
  - `news-ai-limited` `8006`
  - `analyzer-ai` `8007`
  - `optimizer-api` `8008`
  - `dashboard-backend` `8502`
  - `macro-bridge` `8503`
  - `dashboard-frontend` `3001`

### Port and service health observed during audit

| Port | Expected service | Observed during audit |
| --- | --- | --- |
| `3001` | dashboard-frontend | Not reachable |
| `8000` | safe backend / aegis-core if separately run | Not reachable |
| `8004` | sentinel-api | No listener observed |
| `8005` | consensus-api | Not reachable |
| `8006` | news-ai-limited | No listener observed |
| `8007` | analyzer-ai | Not reachable |
| `8008` | optimizer-api | No listener observed |
| `8502` | dashboard-backend | Not reachable |

`docker compose ps` could not confirm container state because Docker daemon access was unavailable in this session.

## 4. Execution Order / Runtime Flow

### Opening `http://localhost:3001`

Code path:

1. `dashboard_react/frontend/src/App.tsx` routes `/` to `Dashboard.tsx`.
2. `Dashboard.tsx` initializes:
   - symbol = `BTC/USDT`
   - timeframe = `1h`
3. `useMetrics(symbol, timeframe, interval)` polls `apiService.getDashboard(...)`, which targets `GET /api/dashboard`.
4. `useLiveFeed(feedSymbol)` strips `/USDT` and opens SSE at `GET /api/live-feed?symbol=BTC`.
5. Legacy cards render from the aggregate payload:
   - metric cards
   - consensus card
   - health card
   - AI analysis / legacy tabs
6. The page itself warns that the legacy SSE contract may not match the selected timeframe.

Key runtime facts:

- HTTP fetch includes both symbol and timeframe.
- Legacy SSE includes symbol only, not timeframe.
- This makes the legacy `/` page internally inconsistent whenever the user changes timeframe.

### Opening `http://localhost:3001/v2`

Code path:

1. `dashboard_react/frontend/src/App.tsx` routes `/v2` to `DashboardV2.tsx`.
2. `VadeContext.tsx` sets the horizon model:

| Horizon | Primary timeframe | Window | Kelly label |
| --- | --- | --- | --- |
| `short` | `4h` | `7d` | `0.15` |
| `medium` | `1d` | `30d` | `0.25` |
| `long` | `1w` | `90d` | `0.40` |

Default is `medium`.

3. `DashboardV2.tsx` calls `useRealTimeFeed("BTC/USDT", timeframe, "7d", vade)`.
4. `useRealTimeFeed.ts` opens:

```text
/api/live-feed?symbol=BTC/USDT&timeframe=<timeframe>&period=7d&horizon=<vade>
```

5. Separate `DashboardV2.tsx` effects also run:
   - `fetchMacro(vade)`
   - `fetchConsensus(symbol, timeframe, ..., vade)` for each asset card

### `/v2` macro flow

1. `fetchMacro(vade)` calls `GET /api/macro?horizon=<vade>`.
2. Backend `dashboard_react/backend/routes/macro.py`:
   - calls `sentinel-api /sentinel/event_risk?symbol=BTC&horizon=<vade>`
   - flattens `macro_snapshot`
   - fills missing fields from `_FALLBACK_METRICS`
   - computes `field_sources`, `fallback_fields`, `data_status`, `verified`, `live`
   - builds `allocation_plan`
3. Frontend `apiV2.normalizeMacro(...)`:
   - normalizes metrics
   - derives `macro_score` client-side if not present
   - derives or normalizes `hedge`
   - normalizes allocation target/current/rebalance fields

### `macroHorizon` vs `macro`

- `macroHorizon` comes from the direct `fetchMacro(vade)` request inside `DashboardV2.tsx`.
- `macro` comes from the SSE hook.
- `effectiveMacro = macroHorizon ?? macro`.

Implication:

- direct batch macro fetch is preferred
- SSE macro acts as a live stream / fallback source

### `/v2` consensus flow

For each asset card:

1. `fetchConsensus(symbol, timeframe, ..., vade)` is called from `apiV2.ts`.
2. It runs two requests in parallel:
   - gateway `GET /api/consensus?symbol=<symbol>&timeframe=<timeframe>&horizon=<vade>`
   - `POST consensus-api /process` with compact symbol and same timeframe/horizon
3. If `/process` fails, frontend keeps the gateway response and marks gateway-only fallback semantics.
4. `normalizeConsensus(...)` merges:
   - action
   - confidence
   - weighted score
   - five-module score
   - module sources
   - last updated timestamp
   - fallback/verified/data status flags

### `MacroRegimeCommentary`

- Component: `dashboard_react/frontend/src/components/macro/MacroRegimeCommentary.tsx`
- Inputs: `effectiveMacro`
- Behavior:
  - displays DXY, VIX, US10Y, Brent, XAU, BTC.D, USDT.D, EvRisk
  - if macro is `FALLBACK`, `PARTIAL_FALLBACK`, `MOCK`, `MISSING`, or `UNKNOWN`, it shows an explicit unverified/fallback commentary
  - otherwise it generates a deterministic narrative from macro values

Important finding:

- The “AI macro commentary” is **not an upstream AI service output** on the V2 main path.
- It is a **frontend rules-based narrative** derived from macro numbers and regime.

### `AllocationWithTip`

- Component: `dashboard_react/frontend/src/components/portfolio/AllocationWithTip.tsx`
- Input: `effectiveMacro`
- Uses:
  - `allocation_horizon`
  - `allocation_profile`
  - `allocation_target`
  - `rebalance_actions`
  - `verified`
  - `data_status`
- Verified rebalance language is intentionally gated behind `macro.verified === true && macro.data_status === "LIVE"`.

### `AssetConsensusCard`

- Component: `dashboard_react/frontend/src/components/assets/AssetConsensusCard.tsx`
- Displays:
  - symbol
  - timeframe
  - `action`
  - confidence
  - weighted score / 5-Mod
  - `data_status`
  - `verified`
  - `fallback_used`
  - last updated
  - module provenance
  - warnings for shared scores and unverified data

### `CrossAlignmentPanel`

- Component: `dashboard_react/frontend/src/components/validation/CrossAlignmentPanel.tsx`
- Inputs:
  - `macro`
  - asset consensus map
  - horizon (`vade`)
- Produces:
  - regime bias vs asset action alignment
  - final checklist
  - explicit `UNVERIFIED` states for fallback macro, fallback VIX, and hedge derived from unverified macro

### API calls involved in `/v2`

- `GET /api/macro`
- `GET /api/consensus`
- `GET /api/live-feed`
- `POST http://localhost:8005/process`
- `GET http://localhost:8005/weights`
- `GET http://localhost:8005/consensus/historical_edge`
- `GET http://localhost:8007/dashboard/exit_attribution`

### SSE updates

`useRealTimeFeed.ts` expects snapshot-style updates from `/api/live-feed` and also supports fallback polling when SSE degrades.

### Fallback behavior

- Macro:
  - backend fills missing fields from `_FALLBACK_METRICS`
  - frontend keeps `fallback_fields`, `field_sources`, `data_status`
- Consensus:
  - gateway-only if `/process` fails
  - top-level `verified` only true when all module sources are verified
- Allocation:
  - unverified macro forces illustrative language and suppresses verified rebalance guidance

### Timestamp and freshness handling

- Frontend utility: `dashboard_react/frontend/src/utils/dataFreshness.ts`
- Priority order:
  - `last_updated`
  - `updatedAt`
  - `updated_at`
  - `timestamp`
  - `generated_at`
  - `created_at`
- Status is explicit if provided; otherwise inferred from source hints and timestamp age.

Important limitation:

- This logic is only as trustworthy as the upstream timestamp.
- Where backend code stamps `datetime.now(...)` on fallback or proxy payloads, the UI may classify data as fresher than the true source.

## 5. Data Source Inventory

| Visible field | Frontend component | Backend endpoint | Upstream source | Hardcoded path? | Fallback path? | Mock path? | Stale risk? | Verified when? | Timestamp source | Reliability today |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `DXY` | `MacroRegimeCommentary` | `GET /api/macro` or SSE macro | Sentinel `event_risk.macro_snapshot.dxy` | Yes, `98.5` fallback | Yes | No direct mock on main V2 path | Yes | Only when sentinel timestamp exists and no fallback fields | `data.timestamp` or `macro_snapshot.timestamp` | Partial |
| `VIX` | `MacroRegimeCommentary`, `CrossAlignmentPanel` | `GET /api/macro` or SSE macro | Sentinel snapshot | Yes, `22.0` fallback | Yes | No direct mock on main V2 path | Yes | Same as DXY | Same as DXY | Partial |
| `US10Y` | `MacroRegimeCommentary` | `GET /api/macro` or SSE macro | Sentinel snapshot | Yes, `4.25` fallback | Yes | No direct mock on main V2 path | Yes | Same as DXY | Same as DXY | Partial |
| `Brent` | `MacroRegimeCommentary` | `GET /api/macro` or SSE macro | Sentinel snapshot | Yes, `92.0` fallback | Yes | No direct mock on main V2 path | Yes | Same as DXY | Same as DXY | Partial |
| `XAU` | `MacroRegimeCommentary` | `GET /api/macro` or SSE macro | Sentinel snapshot | Yes, `4800` fallback | Yes | No direct mock on main V2 path | Yes | Same as DXY | Same as DXY | Partial |
| `BTC.D` | `MacroRegimeCommentary` | `GET /api/macro` or SSE macro | Sentinel snapshot | Yes, `59.8` fallback | Yes | Also appears in static `GET /metrics/sentinel/crypto-macro` | Yes | Only with trusted sentinel timestamp and no fallback fields | Same as DXY or static endpoint `datetime.now(...)` | Partial to low |
| `USDT.D` | `MacroRegimeCommentary` | `GET /api/macro` or SSE macro | Sentinel snapshot | Yes, `7.5` fallback | Yes | No direct mock on main V2 path | Yes | Only with trusted sentinel timestamp and no fallback fields | Same as DXY | Partial |
| `EvRisk` | `MacroRegimeCommentary`, `CrossAlignmentPanel` | `GET /api/macro` or SSE macro | Sentinel `event_risk_score` | Yes, `0.25` in `/api/macro`; `0.18` in stream normalization fallback | Yes | No direct mock on main V2 path | Yes | Only with trusted sentinel timestamp/source | Sentinel timestamp if present; otherwise none | Low to partial |
| `NORMALIZATION` regime | `MacroRegimeCommentary`, `CrossAlignmentPanel` | `GET /api/macro` or SSE macro | Sentinel regime or fallback default | Yes, fallback regime default | Yes | No direct mock on main V2 path | Yes | Only when source field is sentinel and timestamp exists | Same as macro timestamp | Partial |
| `Hedge ON/OFF` | `MacroRegimeCommentary`, `AllocationWithTip`, `CrossAlignmentPanel` | `GET /api/macro` / SSE macro | Backend allocation plan or frontend derivation from macro thresholds | Derived, not fixed constant | Yes, can be derived from unverified macro | No | Yes | Only when macro verified live | Macro timestamp | Partial |
| `Macro score` | `MacroRegimeCommentary` | `GET /api/macro` normalized in frontend | Frontend formula if backend omits `macro_score` | Derived client-side | Yes, if macro inputs are fallback | No | Yes | Only as reliable as underlying macro metrics | Macro timestamp | Partial |
| `Portfolio allocation` | `AllocationWithTip` | `GET /api/macro` / SSE macro | Backend `build_allocation_plan(...)`; frontend can derive target if missing | Base profiles and overlays are coded | Yes | No | Yes | Only when macro verified live | Macro timestamp | Partial |
| `AI macro commentary` | `MacroRegimeCommentary` | None directly | Frontend deterministic commentary rules | Yes, rules-based | Yes, explicit fallback commentary | No | Follows macro | Only as reliable as macro | Macro timestamp | Partial |
| `Asset consensus scores` | `AssetConsensusCard` | `GET /api/consensus` + `POST /process` | Gateway Prometheus/macro proxy + consensus runtime | No direct constants for top-level score | Yes | Gateway fallback and gateway-only fallback exist | Yes | Only when all module sources are verified and live/recent | Latest of gateway/process/module timestamps | Low to partial |
| `T/F/N/S/Q module scores` | `AssetConsensusCard` | `GET /api/consensus` + `POST /process` | Gateway: Prometheus or shared macro proxy; Process: consensus runtime modules | Not usually hardcoded; gateway neutral fallback exists | Yes | Missing-module / gateway-error fallback exists | Yes | Only when module sources are verified, asset-specific, non-shared | Per-module timestamps | Low to partial |
| `confidence` | `AssetConsensusCard` | Mostly `/process`, fallback gateway confidence | Consensus runtime / gateway | No | Yes | Possible gateway fallback | Yes | Only when consensus verified | Consensus timestamp | Partial |
| `5-Mod` | `AssetConsensusCard` | `/process` or frontend computed fallback | Process five-module score or frontend recompute from module scores/weights | No | Yes | Yes, when gateway-only | Yes | Only when all five module sources verified | Consensus timestamp | Low to partial |
| `Final checklist` | `CrossAlignmentPanel` | Frontend-only derived | Macro + consensus inputs | Rules-based | Yes, explicit `UNVERIFIED` branches | No | Follows macro/consensus | Only as reliable as its inputs | Latest macro/consensus timestamps | Partial |

### Key inventory findings

- The V2 macro panel now has a **real provenance model**.
- The V2 asset panel has a **mixed provenance model** because it merges safe-ish gateway data with unsafe `/process` data.
- The V2 macro commentary and final checklist are **frontend-derived outputs**, not canonical backend truth.
- `macro_score` is **frontend-derived if omitted**, so it is not currently a fully canonical backend field.

## 6. Module-by-Module Explanation

| Module | Input | Output | Current data source | Asset-specific or shared | Uses fallback? | Can create final decisions? | Trust level |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Touche / technical | Symbol, timeframe, technical metrics | Technical score / signal | Prometheus in gateway, Touche service in legacy runtime | Asset-specific when symbol-labeled metrics exist; otherwise may fall back to shared/unlabelled | Yes | Not in safe core; yes indirectly in legacy process | Partial |
| Fundamental | Symbol, timeframe, on-chain/fundamental metrics | Fundamental score | Prometheus in gateway, Fundamental service in legacy runtime | Usually asset-specific for BTC if metric exists | Yes | Yes indirectly in legacy process | Partial |
| News | Timeframe, news sentiment | News score | Prometheus or News AI service | Often shared/global rather than asset-native | Yes | Yes indirectly in legacy process | Low to partial |
| Sentinel / macro | Macro indicators, event risk | Regime, event risk, macro snapshot, hedge signal inputs | Sentinel service or hardcoded fallback | Shared | Yes | Not in safe core; yes indirectly in legacy process | Partial |
| Quantum / quant | Quant/risk/liquidity inputs | Quantum score, liquidity/risk outputs | Legacy process / quantum service | Usually asset-specific | Yes | Yes indirectly in legacy process | Low to partial |
| Consensus aggregator | Module scores and weights | Weighted score, action, confidence | Gateway + consensus runtime | Asset-specific for BTC path; mixed/shared for non-crypto | Yes | Yes in legacy path | Low to partial |
| Multi-timeframe validator | Multi-timeframe module signals | Alignment/final signal metadata | `consensus_engine/main.py` | Asset-specific | Unknown / likely yes | Yes indirectly | Low |
| Meta scorer | Module outputs, penalties, confidence interval | `meta_score`, CI, penalties | `consensus_engine/main.py` | Asset-specific | Unknown / likely yes | Yes indirectly | Low |
| Portfolio allocator | Horizon, regime, metrics, data status | Allocation weights, warnings, rebalance plan | `dashboard_react/backend/services/portfolio_allocator.py` | Shared macro-driven multi-asset output | Yes | No final execution decision | Partial to good |
| Macro route | Horizon | Macro payload with provenance and allocation | Sentinel + fallback merge | Shared | Yes | No | Partial to good |
| Stream route | Macro, consensus, attribution, weights | SSE snapshot with merged fields | Self routes + consensus-api + analyzer-ai | Mixed | Yes | Yes, passes through legacy `action` and `position_size` | Low |
| Dashboard route | Consensus gateway, metric endpoints, static module endpoints | Gateway responses and legacy/static cards | Prometheus, Sentinel, static mock-like payloads | Mixed | Yes | Yes in gateway action outputs | Low |
| Analyzer AI | Consensus/history inputs | Exit attribution, report-style analysis | `analyzer-ai` service | Asset-specific or period-specific | Unknown | Can suggest action-style language in analyzer report layer | Low to partial |
| AEGIS Core | Clean signal bundle, macro regime, risk context | Signal-only output and evidence-only wrappers | `aegis_core/*` | Shared-safe path | No silent fallback | No | Good |
| Data Integrity Gate | Source/timestamp/confidence/fallback flags | Pass / degraded / hard-block | `aegis_core/data/integrity.py` | Shared-safe path | No silent fallback | No | Good |
| Risk Engine wrapper | Signal and risk context | Risk decision + warnings | `aegis_core/risk/risk_engine.py` | Shared-safe path | Degraded when context missing | No | Good |
| Kill Switch wrapper | Data gate + risk result + operational flags | Kill switch state | `aegis_core/risk/kill_switch.py` | Shared-safe path | No silent fallback | No | Good |
| OwnerBrief | Safe signal wrapper outputs | Human-readable operator brief | `aegis_core/reports` path | Shared-safe path | N/A | No | Good |
| Audit Record | Safe signal wrapper outputs | Trace/audit record | `aegis_core/audit/*` | Shared-safe path | N/A | No | Good |

## 7. Dashboard vs Module Consistency

| Consistency check | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Selected symbol/timeframe in V2 batch fetch | Consistent | `dashboard_react/frontend/src/pages/DashboardV2.tsx`, `dashboard_react/frontend/src/services/apiV2.ts` | `fetchConsensus(symbol, timeframe, ..., vade)` passes selected values through |
| Selected symbol/timeframe in V2 SSE | Partially consistent | `dashboard_react/frontend/src/hooks/useRealTimeFeed.ts` | SSE uses symbol/timeframe/horizon, but only for BTC live feed |
| Displayed BTC card symbol/timeframe vs SSE | Guarded but not guaranteed | `DashboardV2.tsx` | UI detects mismatch and warns if SSE returns wrong symbol/timeframe |
| Displayed non-BTC cards vs fetch symbol/timeframe | Consistent | `DashboardV2.tsx`, `apiV2.ts` | Non-BTC cards use direct fetch, not SSE |
| Consensus module timeframe | Consistent | `apiV2.ts`, `consensus_engine/main.py` | Same timeframe is sent to gateway and `/process` |
| Portfolio horizon | Consistent | `VadeContext.tsx`, `DashboardV2.tsx`, `routes/macro.py`, `portfolio_allocator.py` | Vade controls horizon and `/api/macro?horizon=...` |
| Kelly/window settings vs backend | Inconsistent / unknown | `VadeContext.tsx`, `apiV2.ts` | UI exposes Kelly/window semantics, but only horizon is sent to backend; Kelly fraction is not a canonical API parameter |
| Macro batch fetch vs macro SSE fallback defaults | Inconsistent | `routes/macro.py`, `routes/stream.py`, `apiV2.ts` | `/api/macro` fallback uses EvRisk `0.25` and `48h`; stream fallback normalizes to `0.18` and `72h` |
| Final checklist vs displayed cards | Partially consistent | `CrossAlignmentPanel.tsx`, `AssetConsensusCard.tsx` | Uses same consensus objects, but may mix BTC SSE data with non-BTC batch data |
| Legacy `/` dashboard symbol/timeframe vs SSE | Inconsistent | `Dashboard.tsx`, `useLiveFeed.ts` | Legacy SSE strips `/USDT` and drops timeframe entirely |

### Consistency conclusion

- V2 is much more consistent than V1.
- The largest remaining consistency problems are:
  - legacy `/` SSE contract drift
  - batch vs SSE fallback default mismatch
  - UI Kelly/window semantics not being carried as canonical backend parameters

## 8. Data Freshness and Data Quality Audit

### Tracking coverage

| Field or concept | Audit result | Notes |
| --- | --- | --- |
| `source` | Partial | Present on macro, consensus, stream, many legacy endpoints; not standardized everywhere |
| `timestamp` | Partial | Often present, but sometimes missing or synthetically generated |
| `last_updated` | Partial | Used heavily in V2, but missing in several legacy aggregate responses |
| `available_timestamp` | Good in safe core, weak elsewhere | AEGIS Core data gate expects it; dashboard/legacy stack does not standardize it |
| `fallback_used` | Good on V2 macro/consensus paths | Not universal in older endpoints |
| `verified` | Good on V2 macro/consensus paths | Not consistent in legacy aggregate/static endpoints |
| `live` | Good on V2 macro path | Not universal elsewhere |
| `data_status` | Good on V2 path | Present but mixed quality in legacy paths |
| `field_sources` | Good on macro V2 path | Strong improvement |
| `fallback_fields` | Good on macro V2 path | Strong improvement |
| `module_sources` | Good on consensus V2 path | Strong improvement |
| stale detection | Partial | Frontend utility exists, but depends on trustworthy timestamps |
| mock/static detection | Partial | Frontend detects mock-like source hints, but backend static endpoints do not always mark themselves as mock |
| missing data detection | Good | Present in V2 and safe core, weaker in some legacy routes |

### Places where synthetic freshness is created

1. `dashboard_react/backend/services/sentinel_client.py`
   - `metrics["timestamp"] = datetime.now(timezone.utc).isoformat()`
   - This records **fetch-wrapper time**, not the upstream market/source timestamp.

2. `dashboard_react/backend/routes/dashboard.py`
   - `/metrics/touche`, `/metrics/fundamental`, `/metrics/quantum`, `/metrics/sentinel`, `/metrics/news`
   - return fresh `timestamp = datetime.now(...)`
   - they do not propagate Prometheus sample timestamps

3. `dashboard_react/backend/routes/dashboard.py`
   - “new endpoints” such as:
     - `/metrics/touche/multiframe`
     - `/metrics/fundamental/onchain-flows`
     - `/metrics/quantum/liquidity-analysis`
     - `/metrics/sentinel/crypto-macro`
     - `/metrics/news/source-reliability`
     - `/metrics/consensus/performance-feedback`
   - are static/mock-like payloads with fresh `datetime.now(...)` timestamps

4. `consensus_engine/src/signal_collector.py`
   - falls back to `datetime.now(...)` when module timestamps are missing
   - this can artificially freshen missing upstream module timing

### Places where stale or partial data can still be misleading

- `dashboard_react/backend/services/prometheus_client.py`
  - falls back to unlabelled historical Prometheus values when symbol-labelled metrics are absent
  - these can be shared rather than asset-specific
- `dashboard_react/backend/routes/dashboard.py`
  - non-crypto asset scores are computed from shared BTC macro context
- `dashboard_react/frontend/src/services/apiV2.ts`
  - derives `macro_score` client-side if missing
  - derives allocation target/current if backend omits fields

### Places where fallback/mock/stale handling is good

- `dashboard_react/backend/routes/macro.py`
  - field-level fallback detection
  - `field_sources`
  - `fallback_fields`
  - `PARTIAL_FALLBACK`
- `dashboard_react/frontend/src/components/macro/MacroRegimeCommentary.tsx`
  - explicit fallback/unverified commentary
- `dashboard_react/frontend/src/components/portfolio/AllocationWithTip.tsx`
  - illustrative-only wording on unverified macro
- `dashboard_react/frontend/src/components/validation/CrossAlignmentPanel.tsx`
  - `UNVERIFIED` status on partial/fallback macro and fallback VIX

### Data-quality conclusion

The V2 path now has the right metadata structure, but **source timestamp integrity is still inconsistent across the stack**. The biggest remaining data-quality problem is **fresh-looking timestamps on fallback/proxy/static outputs**.

## 9. Data Correctness Audit

### Code-proven fallback constants

These values are hardcoded in `dashboard_react/backend/routes/macro.py` and also appear in `dashboard_react/backend/routes/stream.py` normalization:

- `DXY = 98.5`
- `VIX = 22.0`
- `US10Y = 4.25`
- `Brent = 92.0`
- `XAU = 4800`
- `BTC.D = 59.8`
- `USDT.D = 7.5`
- `regime = NORMALIZATION`

They also influence non-crypto asset scoring in `dashboard_react/backend/routes/dashboard.py`.

### Correctness table

| Displayed value | Code provenance | Is it hardcoded? | Fallback-generated? | Other source path | Safe live label if seen today | Audit judgment |
| --- | --- | --- | --- | --- | --- | --- |
| `DXY 98.5` | `_FALLBACK_METRICS["dxy"]` | Yes | Yes | Sentinel live snapshot if available | `FALLBACK` or `PARTIAL_FALLBACK`, never `LIVE` on fallback path | Not correct as live data if unlabeled |
| `VIX 22.0` | `_FALLBACK_METRICS["vix"]` | Yes | Yes | Sentinel live snapshot if available | `FALLBACK` or `PARTIAL_FALLBACK` | Not correct as live data if unlabeled |
| `US10Y 4.25` | `_FALLBACK_METRICS["us10y"]` | Yes | Yes | Sentinel live snapshot if available | `FALLBACK` or `PARTIAL_FALLBACK` | Not correct as live data if unlabeled |
| `Brent 92.0` | `_FALLBACK_METRICS["brent"]` | Yes | Yes | Sentinel live snapshot if available | `FALLBACK` or `PARTIAL_FALLBACK` | Not correct as live data if unlabeled |
| `XAU 4800` | `_FALLBACK_METRICS["xau"]` | Yes | Yes | Sentinel live snapshot if available | `FALLBACK` or `PARTIAL_FALLBACK` | Not correct as live data if unlabeled |
| `BTC.D 59.8` | `_FALLBACK_METRICS["btc_d"]`; also static `/metrics/sentinel/crypto-macro` | Yes | Yes | Sentinel live snapshot or static endpoint | `FALLBACK`, `PARTIAL_FALLBACK`, or `MOCK/STATIC` depending source | High risk of being mistaken for live if routed through static endpoint |
| `USDT.D 7.5` | `_FALLBACK_METRICS["usdt_d"]` | Yes | Yes | Sentinel live snapshot if available | `FALLBACK` or `PARTIAL_FALLBACK` | Not correct as live data if unlabeled |
| `EvRisk 49-51%` | Not found as a hardcoded fallback constant | No direct match | No direct batch fallback match | Likely Sentinel/process-derived if seen | `LIVE` only with trusted upstream timestamp and source; otherwise `UNKNOWN` | Unverifiable in this audit because services were down |
| `XAU 4620-4640` | Not found as a hardcoded fallback constant | No direct match | No direct fallback match | Likely live Sentinel or other upstream | `LIVE` only with trusted source timestamp; otherwise `UNKNOWN` | Unverifiable in this audit because services were down |
| `NORMALIZATION` regime | Macro fallback default | Yes | Yes | Sentinel regime if available | `FALLBACK` or `PARTIAL_FALLBACK` when defaulted | Correct only as fallback label, not as verified live regime |

### Additional correctness findings

- `apiV2.ts` computes `macro_score` client-side when backend omits it. This is acceptable as UI derivation, but it is not canonical provenance.
- `CrossAlignmentPanel.tsx` uses `macro.metrics.event_risk_score` and `macro.metrics.vix` directly for final checklist logic. If those are fallback values, checklist status becomes logic on top of fallback values.
- `dashboard_react/backend/routes/dashboard.py` static endpoint `/metrics/sentinel/crypto-macro` returns `btc_dominance_pct: 59.8` with a fresh timestamp. That payload is not safe to interpret as verified live data.

## 10. Portfolio Allocation Audit

### Files audited

- `dashboard_react/backend/services/portfolio_allocator.py`
- `dashboard_react/frontend/src/components/portfolio/AllocationWithTip.tsx`
- `dashboard_react/backend/tests/test_portfolio_allocator_horizon.py`
- `dashboard_react/backend/tests/test_frontend_allocation_static.py`

### What the allocator currently does

- Uses horizon-aware base profiles:
  - short: more cash, less BTC
  - medium: balanced
  - long: more BTC, less cash
- Applies overlays for:
  - macro regime
  - hedge status
  - event risk
  - VIX
  - data quality / illustrative mode
- Rebalances weights back to total `1.0`
- Applies risk limits and cash floors

### Findings

1. **Weights sum to 100%**
   - Verified by tests.

2. **Cash is never zero**
   - Verified by tests.

3. **Horizon-aware behavior exists**
   - Verified by tests:
     - short keeps more cash than long
     - long allows more BTC than short
     - medium differs from both

4. **Fallback/partial fallback suppresses verified allocation language**
   - Backend sets `allocation_profile = "fallback_illustrative"` when macro is unverified.
   - Frontend hides verified rebalance guidance unless macro is `LIVE` and `verified`.

5. **Displayed allocation does change across horizons**
   - Confirmed by base profiles and test coverage.

6. **Final allocation language is mostly guarded correctly**
   - `AllocationWithTip.tsx` uses illustrative wording for unverified macro.
   - This is good and aligned with the no-advice requirement.

### Material limitations

- `apiV2.ts` can derive allocation target client-side if the backend omits `allocation_target`.
- `apiV2.ts` can derive current allocation from target when no current allocation is supplied.
- That means some rebalance/current-vs-target views can become UI-derived rather than canonical portfolio state.

### Audit verdict

The portfolio allocation layer is **one of the more reliable V2 pieces**, but it is still only **partially reliable** because:

- it depends on macro provenance quality
- it can derive values client-side when backend fields are absent
- it is advisory/illustrative, not actual portfolio state

## 11. Asset Consensus Provenance Audit

### Files audited

- `dashboard_react/frontend/src/components/assets/AssetConsensusCard.tsx`
- `dashboard_react/frontend/src/services/apiV2.ts`
- `dashboard_react/backend/routes/dashboard.py`
- `dashboard_react/backend/routes/stream.py`
- `consensus_engine/main.py`

### Provenance model summary

- Gateway side:
  - BTC-like assets: Prometheus and gateway logic
  - non-crypto assets (`XAU`, `XAG`, `BOND`, `CASH`): shared BTC macro proxy formulas
- Process side:
  - `consensus-api /process`
  - provides action, confidence, five-module score, `position_size`, module sources, sentinel/quantum metadata
- Frontend:
  - merges gateway + process
  - computes top-level `verified` only if all module sources are verified

### Asset-by-asset audit

| Asset | Source | `data_status` | `last_updated` | `verified` | `fallback_used` | Module-source reality | Are T/F/N/S/Q asset-specific? | Shared-score warning? | Can stale/unverified still render? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `BTC` | Gateway + `/process` | Aggregated from gateway, process, and module sources | Latest available among gateway/process/module timestamps | Only if all sources are live/recent and verified | Yes, when any module falls back or process is unavailable | Mixed but potentially strongest path | T/F often asset-specific, N may be shared/global, S/Q from process | Yes if gateway/process says so | Yes, but card shows warnings and badges |
| `XAU` | Gateway macro-derived + optional `/process` | Aggregated | Usually gateway macro timestamp or none | Effectively low/rare because shared gateway module scores are not asset-specific | Common | Gateway uses shared BTC macro snapshot or hardcoded macro defaults | Gateway T/F/N are shared, not asset-native; S/Q depend on process | Yes | Yes |
| `XAG` | Gateway macro-derived + optional `/process` | Aggregated | Same pattern as XAU | Low/rare | Common | Shared macro proxy | Gateway T/F/N shared | Yes | Yes |
| `BOND` | Gateway macro-derived + optional `/process` | Aggregated | Same pattern as XAU | Low/rare | Common | Shared macro proxy | Gateway T/F/N shared | Yes | Yes |
| `CASH` | Gateway macro-derived + optional `/process` | Aggregated | Same pattern as XAU | Low/rare | Common | Shared macro proxy | Gateway T/F/N shared | Yes | Yes |

### Important provenance findings

1. `AssetConsensusCard` visibly surfaces:
   - `Data Status`
   - `Verified`
   - `Fallback used`
   - warnings
   - module provenance

2. Gateway non-crypto consensus is **explicitly shared-score based**:
   - `shared_score=True`
   - `asset_specific=False`
   - warnings include “Shared module score, not asset-specific.”

3. V2 does **not fully block display** of unverified scores.
   - It blocks them from appearing verified.
   - It does **not** block them from appearing at all.

4. `apiV2.normalizeConsensus(...)` still passes through:
   - `action`
   - `position_size`
   - `green_light`
   from `/process`.

### Verdict

- BTC consensus: **partial reliability**
- XAU/XAG/BOND/CASH consensus: **low reliability unless and until asset-native, timestamped, verified sources replace shared BTC proxy scoring**

## 12. AEGIS Core Safety Audit

### Files audited

- `aegis_core/engine/consensus.py`
- `aegis_core/data/integrity.py`
- `aegis_core/risk/risk_engine.py`
- `aegis_core/risk/kill_switch.py`
- `aegis_core/engine/backtest.py`
- `aegis_core/engine/confluence.py`
- `aegis_core/integration_manifest.json`
- `dashboard_react/backend/routes/aegis_core_routes.py`
- `docs/EYAY_BRAINCHAIN_AEGIS_INTEGRATION_CONTRACT.md`

### Safety conclusions

| Safety requirement | Result | Evidence |
| --- | --- | --- |
| Signal-only behavior | PASS | `decision_permission`, `final_decision=False`, tests |
| No `action` field in safe responses | PASS | route tests and core tests |
| No `position_size` field in safe responses | PASS | route tests and core tests |
| No order/broker/execution fields | PASS | manifest + tests + adapters |
| Data Integrity Gate present | PASS | `aegis_core/data/integrity.py` |
| Risk Engine wrapper present | PASS | `aegis_core/risk/risk_engine.py` |
| Kill Switch wrapper present | PASS | `aegis_core/risk/kill_switch.py` |
| OwnerBrief present | PASS | route and ownerbrief tests |
| Audit Record present | PASS | route and audit tests |
| Integration manifest limits approved routes | PASS | `integration_manifest.json` |
| E-yAy contract forbids legacy routes and execution | PASS | contract doc + tests |

### Test results

- `python -m pytest aegis_core/tests`
  - **PASS** `35 passed`
- `python -m pytest tests/test_aegis_core_routes.py tests/test_aegis_core_data_gate_routes.py tests/test_aegis_core_risk_routes.py tests/test_aegis_core_ownerbrief_routes.py tests/test_eyay_integration_contract.py`
  - **PASS** `29 passed`

### AEGIS Core verdict

`aegis_core` is the **cleanest and most trustworthy part of the repository today**. It should remain isolated from all legacy decision and execution surfaces.

## 13. Legacy Runtime Risk Audit

| File or area | What it does | Risk finding | Classification |
| --- | --- | --- | --- |
| `dashboard_react/backend/main.py` | Main dashboard backend | Exposes `/execute`; aggregate dashboard emits `action`; includes paper-trading router | Active, dangerous |
| `dashboard_react/backend/routes/paper_trading.py` | Paper-trading session/buy/sell endpoints | Mutates session state, positions, trades | Active, dangerous |
| `consensus_engine/main.py` | Legacy consensus runtime | `/signal` and `/process` emit final-style action and position sizing; `/bounded_updater/update` mutates weights | Active, dangerous |
| `consensus_engine/src/final_allocator.py` | Final action/allocation engine | Builds final trade/order style allocations | Legacy-dangerous |
| `consensus_engine/src/position_optimizer.py` | Position sizing engine | Calculates Kelly-based position size | Legacy-dangerous |
| `consensus_engine/src/bounded_updater.py` | Weight updater | Writes updated weights to config files, backup/rollback | Active mutation surface |
| `optimizer_service/main.py` | Optimizer API | Applies optimized config to live weights and supports rollback | Active, dangerous |
| `macro_bridge/run.py` | Macro bridge runtime | Emits `decision`, `position_size`, `asset_allocation`, `rebalance_signal`, `hedge` | Legacy-dangerous |
| `strategies/execution_engine.py` | Binance testnet order bridge | Places or simulates orders | Dangerous, safe only if isolated |
| `shared/proto/signals.proto` | Shared execution-oriented proto | Contains order/execution contracts | Legacy-risky |

### Additional risky patterns found

- `dashboard_react/backend/routes/stream.py`
  - passes through `action` and `position_size`
  - contains `except Exception: pass` in a live aggregation path
- `dashboard_react/backend/routes/dashboard.py`
  - returns action-style gateway consensus
  - contains static/mock-like endpoints with fresh timestamps

## 14. Test Suite Audit

### Commands run

| Command | Result | Notes |
| --- | --- | --- |
| `python -m pytest aegis_core/tests` | PASS | `35 passed`; Pytest cache warning only |
| `python -m pytest tests/test_aegis_core_routes.py tests/test_aegis_core_data_gate_routes.py tests/test_aegis_core_risk_routes.py tests/test_aegis_core_ownerbrief_routes.py tests/test_eyay_integration_contract.py` | PASS | `29 passed`; Pytest cache warning only |
| `python -m pytest dashboard_react/backend/tests` | PASS | `23 passed`; covers macro fallback metadata, allocation, provenance |
| `python -m py_compile dashboard_react/backend/routes/macro.py` | PASS | Confirms route compiles |
| `node .\\node_modules\\typescript\\lib\\tsc.js --noEmit` | PASS | Frontend type-check clean |
| `npm run build` | FAIL | `spawn EPERM` from build tooling / environment |
| `python tests/test_v2_consistency.py` | FAIL | Live dependency failure: `localhost:8502` connection refused |

### What the dashboard backend tests currently verify well

- `test_macro_fallback_metadata.py`
  - macro fallback metadata
  - partial fallback metadata
  - exact fallback-cluster detection
- `test_dashboard_partial_fallback_render_static.py`
  - UI normalization preserves fallback metadata
  - macro commentary does not present partial fallback as live
  - verified rebalance language is suppressed on partial fallback
  - final checklist marks partial fallback as unverified
- `test_asset_consensus_provenance_static.py`
  - visible provenance fields exist
  - shared-score and unverified warnings are surfaced
  - consensus paths propagate module provenance
- `test_portfolio_allocator_horizon.py`
  - horizon differences
  - weights sum to one
  - cash floor
  - fallback illustrative mode

### What is still missing from tests

- Live integration with actual running services
- Canonical source timestamp integrity across all modules
- Runtime agreement between batch macro and SSE macro defaults
- Full asset-native provenance for non-crypto assets

## 15. Docker / Service Health Audit

### `docker-compose.yml` observations

`docker compose config --services` succeeded and listed:

- `postgres`
- `redis`
- `fundamental-api`
- `news-ai-limited`
- `prometheus`
- `quantum-api`
- `sentinel-api`
- `clickhouse`
- `touche-api`
- `analyzer-ai`
- `grafana`
- `macro-bridge`
- `qdrant`
- `consensus-api`
- `nginx`
- `postgres-exporter`
- `dashboard-backend`
- `optimizer-api`
- `pushgateway`
- `dashboard-frontend`
- `metrics-pusher`
- `redis-exporter`

### Healthchecks

Major services in `docker-compose.yml` include healthchecks, which is good, but healthchecks were not validated live because Docker was unavailable.

### Which services `/v2` needs

| Requirement level | Services |
| --- | --- |
| UI shell only | `dashboard-frontend`, `dashboard-backend` |
| Macro panel with real provenance | `dashboard-backend`, `sentinel-api` |
| BTC consensus with better fidelity | `dashboard-backend`, `consensus-api`, `prometheus`, `sentinel-api` |
| Attribution panels | `analyzer-ai` in addition to above |
| Full realistic stack | all module services plus infra plus frontend/backend |

### Which services appear optional

- `grafana`
- `nginx`
- exporters
- `pushgateway`
- `macro-bridge` for current V2 main path
- `optimizer-api` for current V2 main path

### Which services were observed down

Observed unavailable during audit:

- `3001` frontend
- `8000` safe backend if separately run
- `8004` sentinel-api
- `8005` consensus-api
- `8006` news-ai-limited
- `8007` analyzer-ai
- `8008` optimizer-api
- `8502` dashboard-backend

### Minimal service set recommendations

#### Minimal safe API validation

- the app exposing `/aegis-core/*`
- no legacy execution, optimizer, or paper-trading surfaces

#### Minimal `/v2` functional stack

- `dashboard-frontend`
- `dashboard-backend`
- `sentinel-api`
- `consensus-api`
- `prometheus`
- `analyzer-ai`

#### Full stack

- all module services
- all infra services
- dashboard frontend/backend
- optional proxy/observability

### Risks of running the full stack

1. Large dependency chain increases false-negative health debugging.
2. Unsafe legacy routes are still present.
3. Optimizer and bounded updater can mutate weights.
4. Paper trading and execution-adjacent paths remain reachable in code.
5. Provenance semantics are not yet fully standardized across all services.

### Docker audit result

- `docker compose config --services`: usable
- `docker compose ps`: unavailable in this session due Docker daemon access failure

## 16. Known Bugs / Inconsistencies

1. Fallback constants can still propagate widely through macro and non-crypto consensus scoring.
2. Stream and batch macro fallback defaults are inconsistent for `event_risk_score` and `hours_to_event`.
3. V1 dashboard SSE contract does not track selected timeframe.
4. `dashboard_react/backend/services/sentinel_client.py` generates synthetic freshness timestamps.
5. `dashboard_react/backend/routes/dashboard.py` has static/mock-like endpoints with fresh timestamps.
6. `dashboard_react/backend/routes/dashboard.py` non-crypto consensus uses shared BTC macro, not asset-native inputs.
7. Shared module scores can still drive displayed asset actions even though warnings are shown.
8. `/process` data is still merged into V2, including `action` and `position_size`.
9. `/execute` remains exposed.
10. `/api/paper/*` remains exposed.
11. Optimizer and bounded updater weight mutation surfaces remain active.
12. `dashboard_react/backend/routes/stream.py` contains `except Exception: pass`.
13. `apiV2.ts` derives `macro_score` client-side if backend omits it.
14. `apiV2.ts` can derive allocation values client-side if backend omits them.
15. `tests/test_v2_consistency.py` is runtime-dependent and currently fails immediately when backend is down.
16. `npm run build` is not currently verified in this environment due `EPERM`.
17. Legacy `GET /api/dashboard` comments claim “NO FALLBACK, NO MOCK DATA” while `mock_system_health` and missing-metric substitutes remain present.
18. The live stack was down during audit, so runtime freshness/data correctness remains unverified.

## 17. Severity Ranking

| Issue | Severity | Impact | Affected file(s) | Recommended fix | Status |
| --- | --- | --- | --- | --- | --- |
| `/execute` still reachable | CRITICAL | Execution-adjacent path remains in dashboard backend | `dashboard_react/backend/main.py`, `strategies/execution_engine.py` | Isolate behind explicit non-default service or remove from dashboard runtime | Open |
| V2 merges unsafe `/process` output | CRITICAL | `action` and `position_size` remain in user-facing V2 path | `dashboard_react/frontend/src/services/apiV2.ts`, `dashboard_react/backend/routes/stream.py`, `consensus_engine/main.py` | Split display-safe consensus from execution-style process output | Open |
| Weight mutation endpoints active | CRITICAL | Live model weight drift/mutation possible | `consensus_engine/src/bounded_updater.py`, `optimizer_service/main.py`, `consensus_engine/main.py` | Quarantine from main stack and lock behind admin-only flows | Open |
| Paper-trading routes active | HIGH | Mutable trading simulation surface remains exposed | `dashboard_react/backend/routes/paper_trading.py` | Remove from default dashboard deployment or isolate behind separate service | Open |
| Synthetic timestamps on proxy/static data | HIGH | Freshness can be overstated | `dashboard_react/backend/services/sentinel_client.py`, `dashboard_react/backend/routes/dashboard.py`, `consensus_engine/src/signal_collector.py` | Propagate upstream timestamps or mark `timestamp_source=proxy_now` and `verified=false` | Open |
| Non-crypto consensus uses shared BTC macro proxy | HIGH | XAU/XAG/BOND/CASH can appear more asset-specific than they are | `dashboard_react/backend/routes/dashboard.py`, `AssetConsensusCard.tsx` | Replace with asset-native upstreams or hard-block verification for proxy assets | Open |
| Batch vs SSE macro default mismatch | MEDIUM | Different fallback macro numbers can produce different checklist/allocation outcomes | `dashboard_react/backend/routes/macro.py`, `dashboard_react/backend/routes/stream.py`, `apiV2.ts` | Canonicalize one fallback/default model | Open |
| Static module endpoints return fresh timestamps | MEDIUM | Mock/static data can look live | `dashboard_react/backend/routes/dashboard.py` | Label as `MOCK`/`STATIC` and stop stamping fresh source timestamps | Open |
| Legacy `/` dashboard SSE mismatch | MEDIUM | Displayed timeframe can diverge from live feed | `dashboard_react/frontend/src/pages/Dashboard.tsx`, `useLiveFeed.ts` | Deprecate V1 or bring SSE contract up to V2 parity | Open |
| `except Exception: pass` in stream path | MEDIUM | Silent data loss / alert suppression | `dashboard_react/backend/routes/stream.py` | Replace with logged failure and explicit degraded metadata | Open |
| Horizon-aware allocation previously too weak | LOW | Historical issue now appears improved | `portfolio_allocator.py`, related tests | Keep current tests and add more edge-case coverage | Partially fixed |
| Field-level macro fallback metadata | LOW | Historical issue now improved | `routes/macro.py`, V2 frontend | Keep tests and runtime verification | Partially fixed |

## 18. What Is Actually Reliable Today?

| Surface | Reliable? | Why | Evidence |
| --- | --- | --- | --- |
| `AEGIS Core health` | Partial | Code/tests are reliable, but live service was down | core tests pass; `localhost:8000` unavailable |
| `/aegis-core/signal` | Partial | Safe contract tested; runtime not observed | route and contract tests pass |
| Dashboard macro panel | Partial | Provenance/fallback logic looks good in code; live source unavailable | backend/static tests pass; services down |
| Asset consensus panel | No / Partial | Mixed gateway + unsafe process + shared scores for some assets | `apiV2.ts`, `dashboard.py`, `consensus_engine/main.py` |
| Portfolio allocation | Partial | Logic and tests are good, but depends on macro verification | allocation tests pass; macro runtime unavailable |
| Final checklist | Partial | Frontend logic is explicit and cautious, but depends on upstream data quality | `CrossAlignmentPanel.tsx` |
| Legacy `/execute` | No | Execution-adjacent route remains active | `dashboard_react/backend/main.py` |
| Legacy `/process` | No | Emits action/position_size and uses mutable/legacy logic | `consensus_engine/main.py` |
| SSE stream | Partial | Good metadata merge ideas, but unsafe field passthrough and services unavailable | `stream.py`, services down |
| Docker services | No | Full runtime not verified; Docker daemon unavailable | `docker compose ps` failed |
| Tests | Yes, targeted subset | Core and dashboard static tests passed | pytest/tsc results |

## 19. Recommended Roadmap

| Phase | Exact files | Objective | Tests | Success criteria |
| --- | --- | --- | --- | --- |
| Phase A: stabilize dashboard rendered fallback guard | `dashboard_react/backend/routes/macro.py`, `dashboard_react/backend/routes/stream.py`, `dashboard_react/frontend/src/services/apiV2.ts`, `dashboard_react/frontend/src/components/macro/MacroRegimeCommentary.tsx`, `dashboard_react/frontend/src/components/portfolio/AllocationWithTip.tsx`, `dashboard_react/frontend/src/components/validation/CrossAlignmentPanel.tsx` | Make batch and SSE macro semantics identical and preserve fallback state all the way to render | existing dashboard backend tests plus new SSE parity tests | Same fallback/default values and same labels in batch and stream paths |
| Phase B: canonical live data provider | `dashboard_react/backend/services/sentinel_client.py`, `dashboard_react/backend/services/prometheus_client.py`, `dashboard_react/backend/routes/dashboard.py`, `dashboard_react/backend/routes/macro.py`, `consensus_engine/main.py` | Standardize one canonical source and timestamp policy per field | provenance and timestamp tests | No field shown as live without upstream timestamp/source |
| Phase C: module source/timestamp standardization | `dashboard_react/backend/routes/dashboard.py`, `dashboard_react/backend/routes/stream.py`, `dashboard_react/frontend/src/services/apiV2.ts`, module services, `consensus_engine/main.py` | Require `source`, `timestamp`, `last_updated`, `data_status`, `verified`, `fallback_used`, `module_sources` everywhere | new contract tests | Every visible card field has traceable provenance and freshness |
| Phase D: deprecate unsafe legacy endpoints | `dashboard_react/backend/main.py`, `dashboard_react/backend/routes/paper_trading.py`, `consensus_engine/main.py`, `optimizer_service/main.py`, `macro_bridge/run.py`, `strategies/execution_engine.py`, `shared/proto/signals.proto`, docs | Remove unsafe surfaces from default deployment and isolate them administratively | route isolation tests, manifest checks | Default stack exposes no execution, paper, optimizer, or weight-mutation endpoints |
| Phase E: unify dashboard data source | `dashboard_react/frontend/src/pages/Dashboard.tsx`, `dashboard_react/frontend/src/pages/DashboardV2.tsx`, `dashboard_react/frontend/src/services/apiV2.ts`, `dashboard_react/backend/routes/dashboard.py`, `dashboard_react/backend/routes/stream.py` | Make one canonical data path per panel and retire legacy V1 drift | frontend static tests, live integration tests | No mixed contracts, no symbol/timeframe mismatches, no duplicate truth sources |
| Phase F: E-yAy gateway later | `aegis_core/integration_manifest.json`, `docs/EYAY_BRAINCHAIN_AEGIS_INTEGRATION_CONTRACT.md`, future gateway adapter files outside legacy runtime | Only after Phases A-E, expose safe signal-only gateway to E-yAy | contract tests | E-yAy can only reach `/aegis-core/*`; legacy execution surfaces remain unreachable |

## 20. Appendices

### Appendix A: Commands run

```text
Get-ChildItem -Force
Get-ChildItem -Name tests
Get-ChildItem -Name dashboard_react\backend\tests
Get-ChildItem -Name dashboard_react\frontend\src\components
Get-ChildItem -Name modules
Get-ChildItem -Name consensus_engine\src
Get-ChildItem -Name archive | Select-Object -First 20
Get-ChildItem -Name audit_reports | Select-Object -First 20
Get-ChildItem -Name backtest | Select-Object -First 20
Get-ChildItem -Name backtest_reports | Select-Object -First 20
Get-ChildItem -Name docs | Select-Object -First 20
Get-ChildItem -Name quarantine | Select-Object -First 20
Get-ChildItem -Name scripts | Select-Object -First 20
Get-ChildItem -Name shared | Select-Object -First 20
rg "^def test_" tests dashboard_react\backend\tests aegis_core\tests
rg -n "Date\.now\(|datetime\.now\(" ...
python -m pytest aegis_core/tests
python -m pytest tests/test_aegis_core_routes.py tests/test_aegis_core_data_gate_routes.py tests/test_aegis_core_risk_routes.py tests/test_aegis_core_ownerbrief_routes.py tests/test_eyay_integration_contract.py
python -m pytest dashboard_react/backend/tests
python -m py_compile dashboard_react/backend/routes/macro.py
node .\node_modules\typescript\lib\tsc.js --noEmit
npm run build
python tests/test_v2_consistency.py
docker compose config --services
docker compose ps
Invoke-WebRequest / requests probes for localhost:3001, 8000, 8502, 8005, 8007
Get-NetTCPConnection -LocalPort 3001,8000,8004,8005,8006,8007,8008,8502
Get-Date -Format o
```

### Appendix B: Test outputs summarized

- `aegis_core/tests`: passed
- AEGIS core route/contract suite: passed
- Dashboard backend static suite: passed
- Frontend TypeScript compile: passed
- Frontend production build: failed in this environment with `spawn EPERM`
- Live consistency script: failed because backend `:8502` was down

### Appendix C: Files inspected

- `dashboard_react/backend/main.py`
- `dashboard_react/backend/routes/aegis_core_routes.py`
- `dashboard_react/backend/routes/macro.py`
- `dashboard_react/backend/routes/stream.py`
- `dashboard_react/backend/routes/dashboard.py`
- `dashboard_react/backend/routes/paper_trading.py`
- `dashboard_react/backend/services/portfolio_allocator.py`
- `dashboard_react/backend/services/prometheus_client.py`
- `dashboard_react/backend/services/sentinel_client.py`
- `dashboard_react/frontend/src/App.tsx`
- `dashboard_react/frontend/src/pages/Dashboard.tsx`
- `dashboard_react/frontend/src/pages/DashboardV2.tsx`
- `dashboard_react/frontend/src/hooks/useMetrics.ts`
- `dashboard_react/frontend/src/hooks/useLiveFeed.ts`
- `dashboard_react/frontend/src/hooks/useRealTimeFeed.ts`
- `dashboard_react/frontend/src/services/apiV2.ts`
- `dashboard_react/frontend/src/components/macro/MacroRegimeCommentary.tsx`
- `dashboard_react/frontend/src/components/portfolio/AllocationWithTip.tsx`
- `dashboard_react/frontend/src/components/assets/AssetConsensusCard.tsx`
- `dashboard_react/frontend/src/components/validation/CrossAlignmentPanel.tsx`
- `dashboard_react/frontend/src/components/ui/DataStatusBadge.tsx`
- `dashboard_react/frontend/src/utils/dataFreshness.ts`
- `dashboard_react/frontend/src/context/VadeContext.tsx`
- `aegis_core/engine/consensus.py`
- `aegis_core/data/integrity.py`
- `aegis_core/risk/risk_engine.py`
- `aegis_core/risk/kill_switch.py`
- `aegis_core/engine/backtest.py`
- `aegis_core/engine/confluence.py`
- `aegis_core/integration_manifest.json`
- `docs/EYAY_BRAINCHAIN_AEGIS_INTEGRATION_CONTRACT.md`
- `consensus_engine/main.py`
- `consensus_engine/src/final_allocator.py`
- `consensus_engine/src/position_optimizer.py`
- `consensus_engine/src/bounded_updater.py`
- `optimizer_service/main.py`
- `macro_bridge/run.py`
- `strategies/execution_engine.py`
- `shared/proto/signals.proto`
- `docker-compose.yml`

### Appendix D: Important endpoints

Safe:

- `GET /aegis-core/health`
- `POST /aegis-core/signal`
- `POST /aegis-core/backtest-evidence`

Dashboard/runtime:

- `GET /api/dashboard`
- `GET /api/macro`
- `GET /api/consensus`
- `GET /api/live-feed`
- `GET /health`

Legacy-dangerous:

- `POST /execute`
- `POST /process`
- `GET /signal`
- `GET /weights`
- `POST /bounded_updater/update`
- `POST /api/paper/buy`
- `POST /api/paper/sell`
- `POST /optimizer/apply/{study_id}`
- `POST /optimizer/rollback`

### Appendix E: Important ports

- `3001` dashboard frontend
- `8000` safe backend / aegis-core if separately run
- `8001` touche-api
- `8002` fundamental-api
- `8003` quantum-api
- `8004` sentinel-api
- `8005` consensus-api
- `8006` news-ai-limited
- `8007` analyzer-ai
- `8008` optimizer-api
- `8502` dashboard backend
- `8503` macro-bridge
- `8080` nginx
- `9090` prometheus
- `3000` grafana
- `5432` postgres
- `6379` redis
- `8123`, `9000` clickhouse
- `6333`, `6334` qdrant
- `9091` pushgateway

### Appendix F: Report generation timestamp

- `2026-05-01T22:53:08.8329347+03:00`

### Final audit statement

This audit did **not** modify application logic. The repository now has a clear safe core, but the default live stack remains a **mixed safe/unsafe system** until the legacy execution, paper-trading, optimizer, and `/process` decision surfaces are isolated from the dashboard runtime.
