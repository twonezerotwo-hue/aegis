# AEGIS Dashboard Data Source Audit

Audit date: 2026-05-01  
Scope: `dashboard_react/frontend`, `dashboard_react/backend`, and related API/config files.  
Constraints followed: no runtime changes, no deletes/moves, no Docker, audit-only.

## 1. Executive summary

The dashboard is using mixed legacy sources, not `"/aegis-core/*"`.

- No frontend call to `GET /aegis-core/health`, `POST /aegis-core/signal`, or `POST /aegis-core/backtest-evidence` was found.
- The legacy `"/"` dashboard uses legacy gateway endpoints on `http://localhost:8502`.
- The `"/v2"` dashboard uses a mix of:
  - gateway endpoints on `http://localhost:8502`
  - direct downstream calls to `http://localhost:8005`
  - direct downstream calls to `http://localhost:8007`
  - an SSE stream from `http://localhost:8502/api/live-feed`
- Mock/static/fallback paths exist in both frontend and backend, especially in macro, consensus normalization, backtest, paper trading, and optimizer areas.

Most likely reason the dashboard looks outdated:

1. `DashboardV2` mixes horizon-specific fetches with a default SSE feed that is effectively fixed to `BTC/USDT`, `1h`, and backend default horizon behavior.
2. The BTC card explicitly prefers SSE consensus over the horizon-aware batch fetch, so the selected vade/timeframe can disagree with the displayed BTC data.
3. The SSE backend itself does not forward horizon cleanly to all downstream calls.
4. Several fallback paths stamp current timestamps onto fallback/static/synthetic data, so stale data can appear fresh.
5. The legacy header shows the browser clock as “Last updated”, not the backend data timestamp.

Bottom line:

- The dashboard is not an `aegis_core` UI today.
- It is a mixed legacy gateway UI with silent fallback behavior.
- The highest-probability root cause is frontend/backend binding mismatch in the V2 live-feed path, not a browser cache or `/aegis-core` issue.

## 2. Frontend route/page inventory

### Active app routes

| Route | File | Component/Page | What it displays | Actual data source(s) |
| --- | --- | --- | --- | --- |
| `/` | `dashboard_react/frontend/src/pages/Dashboard.tsx` | `Dashboard` | Legacy dashboard shell with tabs | `useMetrics()` -> `GET /api/dashboard`; `useLiveFeed()` -> `GET /api/live-feed`; tab components call additional legacy endpoints |
| `/v2` and `/v2/*` | `dashboard_react/frontend/src/pages/DashboardV2.tsx` | `DashboardV2` | V2 macro + allocation + asset consensus + cross-alignment | `useRealTimeFeed()` SSE + `fetchMacro()` + `fetchConsensus()` |
| `/v2/backtest` | `dashboard_react/frontend/src/pages/BacktestV2.tsx` | `BacktestV2` | Backtest V2 page | `POST /backtest/run`, `GET /api/macro`, `POST /api/simulator`, `GET /backtest/export/{id}` |

### Legacy `/` dashboard tab surfaces

| File | Component/Page | What it displays | Endpoint or data source |
| --- | --- | --- | --- |
| `dashboard_react/frontend/src/pages/Dashboard.tsx` | Metrics tab | 5 module cards, consensus, system status | `useMetrics()` -> `dashboard_react/frontend/src/services/api.ts` -> `GET http://localhost:8502/api/dashboard` |
| `dashboard_react/frontend/src/pages/Dashboard.tsx` | AEGIS Intelligence tab | regime, consensus gauge, CBR matches, exit signal, paper trade log | `useLiveFeed()` -> `GET http://localhost:8502/api/live-feed?symbol=...` |
| `dashboard_react/frontend/src/components/AIAnalysisCard.tsx` | AI Analysis tab | analyzer summary, recommendation, risk notes | `GET http://localhost:8502/api/analysis?symbol=...&timeframe=...` |
| `dashboard_react/frontend/src/components/OptimizerCard.tsx` | Optimizer tab | optimizer status and controls | hardcoded `http://localhost:8502/api/optimizer/*` |
| `dashboard_react/frontend/src/pages/Backtest.tsx` | Backtest tab | legacy backtest runner/results | `dashboard_react/frontend/src/services/backtestApi.ts` -> `http://localhost:8502/backtest/*` |
| `dashboard_react/frontend/src/pages/PaperTrading.tsx` | Paper Trading tab | in-memory paper session UI | `dashboard_react/frontend/src/services/paperTradingApi.ts` -> `http://localhost:8502/api/paper/*` |

### V2 `/v2` dashboard surfaces

| File | Component/Page | What it displays | Endpoint or data source |
| --- | --- | --- | --- |
| `dashboard_react/frontend/src/pages/DashboardV2.tsx` | `GlobalHeader` | regime, health, last updated, live status | from `useRealTimeFeed()` plus horizon-specific `fetchMacro()` result |
| `dashboard_react/frontend/src/pages/DashboardV2.tsx` | `MacroRegimeCommentary` | macro regime commentary and macro metrics | `GET http://localhost:8502/api/macro?horizon=...` or SSE macro fallback |
| `dashboard_react/frontend/src/pages/DashboardV2.tsx` | `AllocationWithTip` | allocation target/current | same macro source as above |
| `dashboard_react/frontend/src/pages/DashboardV2.tsx` | asset cards | per-asset consensus cards | `fetchConsensus()` -> gateway `GET /api/consensus` + direct `POST http://localhost:8005/process`; BTC card then overwritten by SSE BTC consensus |
| `dashboard_react/frontend/src/pages/DashboardV2.tsx` | `CrossAlignmentPanel` | macro bias vs asset consensus | derived from macro + asset card data |
| `dashboard_react/frontend/src/components/debug/DataSyncMonitor.tsx` | debug overlay | request log only | intercepts `fetch`, no data ownership |

### V2 backtest surfaces

| File | Component/Page | What it displays | Endpoint or data source |
| --- | --- | --- | --- |
| `dashboard_react/frontend/src/pages/BacktestV2.tsx` | main run action | backtest result cards/tables | `POST http://localhost:8502/backtest/run` |
| `dashboard_react/frontend/src/pages/BacktestV2.tsx` | macro intelligence cards | regime probability, liquidity, volatility | `GET http://localhost:8502/api/macro?horizon=...` |
| `dashboard_react/frontend/src/components/backtest/ScenarioSimulator.tsx` | scenario simulation | what-if macro simulation | `POST http://localhost:8502/api/simulator` |
| `dashboard_react/frontend/src/pages/BacktestV2.tsx` | export report | report JSON export | `GET http://localhost:8502/backtest/export/{backtest_id}` |

### Not currently mounted

- `dashboard_react/frontend/src/components/optimizer/OptimizerTab.tsx` exists but is not mounted by `App.tsx`.
- `dashboard_react/frontend/src/components/paper/PaperTradingTab.tsx` exists but is not mounted by `App.tsx`.
- `dashboard_react/frontend/src/archive/*` and `*.backup` files exist but no live import path to them was found.

## 3. API client inventory

| File | Base URL | Endpoint paths | Target type |
| --- | --- | --- | --- |
| `dashboard_react/frontend/src/services/api.ts` | `VITE_API_URL` or `http://localhost:8502` | `/health`, `/api/metrics/touche`, `/api/metrics/fundamental`, `/api/metrics/quantum`, `/api/metrics/sentinel`, `/api/metrics/news`, `/api/consensus`, `/api/health`, `/api/dashboard`, `/api/config`, `/api/analysis` | Backend gateway `8502` only |
| `dashboard_react/frontend/src/services/apiV2.ts` | gateway: `VITE_API_URL` or `http://localhost:8502`; analyzer: `VITE_ANALYZER_API_URL` or `http://localhost:8007`; consensus: `VITE_CONSENSUS_API_URL` or `http://localhost:8005` | gateway `/api/macro`, `/api/consensus`; consensus `/process`, `/consensus/historical_edge`, `/weights`, `/attribution/calculate`; analyzer `/dashboard/exit_attribution` | Mixed: gateway `8502` + direct `8005` + direct `8007` |
| `dashboard_react/frontend/src/services/backtestApi.ts` | `VITE_API_URL` or `http://localhost:8502` | `/backtest/run`, `/backtest/results`, `/backtest/supported-timeframes`, `/backtest/export/csv`, `/backtest/export/html`, `DELETE /backtest/cache` | Backend `8502` |
| `dashboard_react/frontend/src/services/paperTradingApi.ts` | `VITE_API_URL` or `http://localhost:8502` | `/api/paper/status`, `/start`, `/stop`, `/buy`, `/sell`, `/equity-curve`, `/export` | Backend `8502` |
| `dashboard_react/frontend/src/hooks/useRealTimeFeed.ts` | `VITE_API_URL` or `http://localhost:8502` | `/api/live-feed?symbol=...&timeframe=...&period=...` | SSE via backend `8502` |
| `dashboard_react/frontend/src/hooks/useLiveFeed.ts` | `VITE_API_URL` or `http://localhost:8502` | `/api/live-feed?symbol=...` | SSE via backend `8502` |
| `dashboard_react/frontend/src/components/AIAnalysisCard.tsx` | `VITE_API_URL` or `http://localhost:8502` | `/api/analysis` | Backend `8502` |
| `dashboard_react/frontend/src/components/OptimizerCard.tsx` | hardcoded `http://localhost:8502` | `/api/optimizer/status`, `/record-trade`, `/periodic-optimize`, `/save-config` | Backend `8502`, hardcoded |
| `dashboard_react/frontend/src/components/optimizer/OptimizerTab.tsx` | `VITE_API_URL` or `http://localhost:8502` | `/api/optimizer/status`, `/trade-history`, `/optimization-history`, `/periodic-optimize`, `/save-config`, `/load-config` | Backend `8502` |
| `dashboard_react/frontend/src/components/paper/PaperTradingTab.tsx` | `VITE_API_URL` or `http://localhost:8502` | `/api/paper/status`, `/start`, `/stop`, `/export` | Backend `8502` |
| `dashboard_react/frontend/src/pages/BacktestV2.tsx` | `VITE_API_URL` or `http://localhost:8502` | `/backtest/run`, `/api/macro`, `/backtest/export/{id}` | Backend `8502` |
| `dashboard_react/frontend/src/components/backtest/ScenarioSimulator.tsx` | `VITE_API_URL` or `http://localhost:8502` | `/api/simulator` | Backend `8502` |

Important observations:

- No frontend API client points at port `3001` for data. `3001` is frontend hosting only.
- No active frontend API client points at `127.0.0.1`.
- No active frontend API client points at port `8000`.
- No frontend dev proxy is configured in `dashboard_react/frontend/vite.config.ts`.
- `dashboard_react/frontend/src/services/api.ts` contains `/api/config`, but no backend implementation was found.
- `dashboard_react/frontend/src/services/backtestApi.ts` contains `/backtest/results`, but no matching backend route was found.

## 4. Backend endpoint mapping

| Endpoint | File | Legacy or `aegis_core` | Stale/mock/fallback risk |
| --- | --- | --- | --- |
| `GET /health` | `dashboard_react/backend/main.py` | Legacy gateway | Low; simple gateway health only |
| `POST /execute` | `dashboard_react/backend/main.py` | Legacy execution path | Not used by frontend; not E-yAy safe |
| `GET /api/dashboard` | `dashboard_react/backend/main.py` | Legacy gateway | Medium; substitutes `0.0` for missing Prometheus metrics and uses mock system health |
| `GET /api/analysis` | `dashboard_react/backend/main.py` | Legacy gateway | Medium; synthesizes current-timestamp analyzer response from Prometheus-derived inputs |
| `GET /api/analysis/report` | `dashboard_react/backend/main.py` | Legacy gateway | Medium; passthrough to analyzer |
| `GET /api/optimizer/*`, `POST /api/optimizer/*` | `dashboard_react/backend/main.py` | Legacy gateway | Medium; optimizer state is local runtime state, not `aegis_core` |
| inline `GET/POST /backtest/*` in `main.py` | `dashboard_react/backend/main.py` | Legacy deprecated | High; deprecated, duplicate surface, buy-and-hold fallback, in-memory storage |
| `GET /api/metrics/touche` | `dashboard_react/backend/routes/dashboard.py` | Legacy gateway | Medium; returns default `0.5` and `source: "cache"` on error |
| `GET /api/metrics/fundamental` | `dashboard_react/backend/routes/dashboard.py` | Legacy gateway | Medium; returns default `0.5` and `source: "cache"` on error |
| `GET /api/metrics/quantum` | `dashboard_react/backend/routes/dashboard.py` | Legacy gateway | Medium; returns default `0.5` and `source: "cache"` on error |
| `GET /api/metrics/sentinel` | `dashboard_react/backend/routes/dashboard.py` | Legacy gateway | Medium; returns default `0.5` and `source: "cache"` on error |
| `GET /api/metrics/news` | `dashboard_react/backend/routes/dashboard.py` | Legacy gateway | Medium; returns default `0.5` and `source: "cache"` on error |
| `GET /api/consensus` | `dashboard_react/backend/routes/dashboard.py` | Legacy gateway | Medium; 3-module consensus only, current timestamp on fallback/error |
| `GET /api/health` | `dashboard_react/backend/routes/dashboard.py` | Legacy gateway | Low |
| `GET /api/macro` | `dashboard_react/backend/routes/macro.py` | Legacy gateway | High; falls back to static `_FALLBACK_METRICS` snapshot with fresh timestamp |
| `GET /api/metrics/sentinel/macro` | `dashboard_react/backend/routes/macro.py` | Legacy alias | Same risk as `/api/macro` |
| `POST /api/simulator` | `dashboard_react/backend/routes/macro.py` | Legacy gateway | Medium; local simulated fallback if Sentinel unavailable |
| `GET /api/live-feed` | `dashboard_react/backend/routes/stream.py` | Legacy gateway SSE | High; composes legacy gateway + direct downstreams, normalizes fallback data, no `aegis_core` |
| `GET/POST /api/paper/*` | `dashboard_react/backend/routes/paper_trading.py` | Legacy gateway | High; in-memory sessions and synthetic prices on buy/sell default |
| `POST /backtest/run` | `dashboard_react/backend/routes/backtest_routes.py` | Legacy canonical backtest router | High; mock OHLCV fallback, buy-and-hold fallback, cached results |
| `GET /backtest/status`, `/report/{id}`, `/export/{id}`, `/results`, `/supported-timeframes`, `DELETE /cache` | `dashboard_react/backend/routes/backtest_routes.py` | Legacy backtest router | Medium to high; cached/in-memory behavior |
| `GET /aegis-core/health` | `dashboard_react/backend/routes/aegis_core_routes.py` | `aegis_core` | Safe, read-only |
| `POST /aegis-core/signal` | `dashboard_react/backend/routes/aegis_core_routes.py` | `aegis_core` | Safe signal-only surface; returns data integrity, risk, kill switch, ownerbrief, audit |
| `POST /aegis-core/backtest-evidence` | `dashboard_react/backend/routes/aegis_core_routes.py` | `aegis_core` | Safe evidence-only surface |

Additional notes:

- `main.py` includes `backtest_routes.router` early and comments say the router-based `/backtest/run` is canonical. Inline backtest endpoints still exist and add confusion.
- The live-feed backend does not use `"/aegis-core/*"` anywhere.
- The live-feed backend calls its own gateway at `http://localhost:8502` plus direct downstreams at `http://localhost:8005` and `http://localhost:8007`.

## 5. Static/mock/cache sources

| File/path | What it contains | May dashboard read it? |
| --- | --- | --- |
| `dashboard_react/backend/routes/macro.py` | `_FALLBACK_METRICS` static macro snapshot; comment says realistic last-known values for April 2026 | Yes. Used by `/api/macro` and therefore by `/v2` and SSE when Sentinel is unavailable |
| `dashboard_react/backend/routes/dashboard.py` | per-metric fallback responses with `score: 0.5` and `source: "cache"` | Yes. Used by legacy metric surfaces and gateway consensus dependencies |
| `dashboard_react/backend/routes/dashboard.py` | hardcoded static demo endpoints: multiframe, onchain flows, liquidity analysis, crypto macro, source reliability, performance feedback | Not currently. No active frontend call found |
| `dashboard_react/backend/routes/backtest_routes.py` | `_OHLCV_CACHE`, `backtest_engine.results`, `backtest_runs`, mock historical data generator, buy-and-hold fallback | Yes, for backtest pages and exports |
| `dashboard_react/backend/backtest/historical_news_fetcher.py` | 60-second cached sentiment; neutral `0.0` for dates older than 30 days | Yes, backtest only |
| `dashboard_react/backend/routes/paper_trading.py` | in-memory `SESSIONS`; default buy/sell `price=50000` if caller omits price | Yes, paper trading surfaces |
| `dashboard_react/frontend/src/services/apiV2.ts` | client-side normalization defaults and synthetic fallback `HOLD` response with current timestamp after retries exhaust | Yes, V2 dashboard directly |
| `dashboard_react/frontend/src/components/OptimizerCard.tsx` | client-side `mockTrade` payload posted when user clicks “Record Trade” | Yes, legacy optimizer tab only |
| `dashboard_react/backend/routes/archive/*` | archived mock/deterministic live-feed and metrics code | No active runtime import found |
| `dashboard_react/frontend/src/archive/*` and `*.backup` | archived/backup UI code | No active runtime import found |
| `dashboard_react/frontend/src/components/ui/ThemeToggle.tsx` | `localStorage` theme persistence only | No market/business data cache |

What was not found:

- No active frontend reads from `summary.json`.
- No active frontend reads from `backtest_reports`.
- No active frontend reads from `sessionStorage`.
- No active frontend business-data caching via `localStorage`.

## 6. Timestamp freshness analysis

### Where timestamps are shown

| Surface | File | Timestamp shown | Freshness quality |
| --- | --- | --- | --- |
| Legacy header | `dashboard_react/frontend/src/components/Header.tsx` | browser current time labeled “Last updated” | Misleading; not backend data freshness |
| Legacy metrics footer | `dashboard_react/frontend/src/pages/Dashboard.tsx` | `data.timestamp` from `/api/dashboard` | Better, but only for metrics tab |
| Legacy intelligence tab | `dashboard_react/frontend/src/pages/Dashboard.tsx` | `liveFeed.timestamp` | Depends on old SSE hook that does not match current backend event contract |
| V2 global header | `dashboard_react/frontend/src/components/layout/GlobalHeader.tsx` via `DashboardV2.tsx` | `effectiveMacro.timestamp` only | Partial; does not represent per-asset consensus freshness |
| V2 state hook | `dashboard_react/frontend/src/hooks/useRealTimeFeed.ts` | computes `lastUpdated` from snapshot or fallback state | Computed, but `DashboardV2` does not display this computed field |
| AI analysis card | `dashboard_react/frontend/src/components/AIAnalysisCard.tsx` | backend-generated current timestamp | Can look fresh even if underlying scores are fallback/synthetic |
| Backtest pages | `generated_at`, report timestamps | backend-generated current timestamp | Freshness of report creation, not necessarily freshness of input data |
| Optimizer/paper trading tabs | trade/history/session timestamps | local runtime state timestamps | Not market data freshness |

### Does the frontend validate freshness?

No hard freshness validation was found.

- No max-age check such as “older than X minutes”.
- No comparison between selected horizon/timeframe and incoming timestamp source.
- No warning badge when `fallback: true` is present on macro responses.
- No warning badge when V2 consensus falls back to gateway-only mode after `/process` failure.
- No warning badge when `apiV2` synthesizes default values or injects `new Date().toISOString()`.

### How stale data can be silently shown

1. `DashboardV2` calls `useRealTimeFeed()` with default `symbol=BTC/USDT`, default `timeframe=1h`, and no horizon argument.
2. The SSE backend route accepts `horizon`, but the frontend does not send one.
3. The SSE backend `_build_snapshot()` then calls:
   - `GET /api/macro` without forwarding horizon
   - `POST /process` without forwarding horizon
   - `GET /api/consensus` without horizon awareness beyond timeframe
4. `DashboardV2` then overwrites the BTC asset card with this SSE consensus, even after horizon-aware batch fetches complete.
5. `useRealTimeFeed` fallback polling also uses default `fetchMacro()` and default `fetchConsensus(...)`, which default to medium-horizon behavior.

### Stale data is flagged or silent?

Partially flagged, mostly silent.

- Connection failure is partially flagged:
  - `useRealTimeFeed` exposes `connectionStatus`
  - `DashboardV2` shows a toast/banner when the stream drops into fallback mode
- Data-origin fallback is mostly silent:
  - macro static snapshot fallback is not directly labeled in the UI
  - gateway-only consensus fallback is not directly labeled in the UI
  - client-side synthesized defaults are not labeled in the UI
  - the legacy header makes stale data look fresh by showing the current browser clock

## 7. E-yAy compatibility

### What can safely use `"/aegis-core/*"`

These dashboard additions are compatible with the safe `aegis_core` contract:

- A small status panel calling `GET /aegis-core/health`
- A read-only signal audit panel calling `POST /aegis-core/signal`
  - input can be adapted from existing V2 state:
    - `symbol`
    - `timeframe`
    - `raw_regime` from macro
    - `module_scores` from V2 consensus
    - optional `higher_tf_scores`
    - optional `data_integrity`, `risk_context`, `kill_switch_context`
- A backtest evidence panel on `/v2/backtest` calling `POST /aegis-core/backtest-evidence`

### What is legacy-only today

These parts are currently legacy-only and not E-yAy verified:

- Entire legacy `"/"` dashboard
- `GET /api/dashboard`
- `GET /api/metrics/*`
- `GET /api/consensus`
- `GET /api/live-feed`
- `GET /api/analysis`
- `GET/POST /api/optimizer/*`
- `GET/POST /api/paper/*`
- `POST /backtest/run` and related `/backtest/*` endpoints
- direct frontend calls to:
  - `http://localhost:8005/process`
  - `http://localhost:8005/consensus/historical_edge`
  - `http://localhost:8005/weights`
  - `http://localhost:8007/dashboard/exit_attribution`

### What should display `LEGACY DATA / NOT E-YAY VERIFIED`

Recommended labeling targets:

- All legacy `"/"` dashboard tabs
- V2 macro commentary and allocation panels
- V2 asset consensus cards
- V2 cross-alignment panel
- V2 SSE-derived live status surfaces
- Optimizer panels
- Paper trading panels
- Backtest result surfaces until paired with `POST /aegis-core/backtest-evidence`

Reason:

- None of these surfaces currently source their truth from `"/aegis-core/*"`.
- Several of them rely on mixed legacy gateway + direct downstream + fallback logic.

## 8. Recommended next step

Do not implement yet. Minimal patch plan only.

### Minimal patch plan: add an AEGIS Core status panel

1. Add a tiny frontend service for:
   - `GET /aegis-core/health`
2. Mount a compact “AEGIS Core Status” card near the V2 header.
3. Show:
   - engine
   - status
   - `decision_permission`
   - `final_decision`
4. Add a visible source split:
   - `Gateway Legacy`
   - `AEGIS Core`

### Minimal patch plan: show Data Integrity / Risk / Kill Switch / OwnerBrief

1. Create a read-only adapter from V2 dashboard state to `POST /aegis-core/signal`.
2. Start with one asset only:
   - BTC on `/v2`
3. Build request fields from current V2 state:
   - `symbol` from selected asset
   - `timeframe` from `VadeContext`
   - `raw_regime` from `effectiveMacro.regime`
   - `module_scores` from `ConsensusResponse.module_scores`
   - `higher_tf_scores` empty or derived later
4. Render a small side panel or bottom panel with:
   - Data Integrity
   - Risk
   - Kill Switch
   - OwnerBrief
   - Audit warnings
5. Add explicit labels:
   - `AEGIS CORE`
   - `NON-FINAL SIGNAL ONLY`
   - `LEGACY DATA / NOT E-YAY VERIFIED` for neighboring legacy panels

### Minimal patch plan: add backtest evidence without replacing the legacy backtest

1. Keep existing `POST /backtest/run` flow unchanged.
2. After a successful backtest, call `POST /aegis-core/backtest-evidence` with `result.metrics`.
3. Show the evidence card beside the legacy backtest summary.
4. Label the legacy report and the `aegis_core` evidence separately.

## 9. Risk list

- Stale data risk:
  - V2 uses a default SSE binding that is not aligned with selected horizon/timeframe.
  - Macro route can return static fallback metrics with a fresh timestamp.
  - Backtest uses in-memory caches and mock/buy-hold fallbacks.
- Silent fallback risk:
  - frontend `apiV2` injects defaults and synthetic timestamps
  - macro fallback is not prominently surfaced
  - gateway-only consensus fallback is not prominently surfaced
  - legacy header shows current clock as “Last updated”
- Legacy endpoint risk:
  - no frontend surface uses `"/aegis-core/*"` today
  - V2 still depends on legacy gateway and direct downstream services
  - duplicate/deprecated backtest endpoints still exist in `main.py`
  - legacy `useLiveFeed()` expects an older SSE shape than the current backend emits
- Frontend cache risk:
  - low for browser storage; only theme preference is stored in `localStorage`
  - medium for backend/runtime caches and fallback normalization
  - possible operational risk if `localhost:3001` is serving an old built bundle instead of the live source tree, but no code-level proof of that was found in this audit

## Key conclusion

The dashboard is currently a mixed legacy gateway UI with silent fallback behavior. The strongest concrete finding is the V2 data-binding mismatch around the SSE/live-feed path: default BTC/1h/medium stream data is being mixed with horizon-aware refetches, and the UI can present fallback/static data with fresh timestamps. No current React surface is using the safe `"/aegis-core/*"` contract.
