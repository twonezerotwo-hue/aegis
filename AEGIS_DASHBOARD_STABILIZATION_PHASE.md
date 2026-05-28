# AEGIS Dashboard Stabilization Phase

## What changed

- Added [dashboard_react/frontend/src/utils/dataFreshness.ts](/C:/Users/twone/Desktop/aegis_codex/dashboard_react/frontend/src/utils/dataFreshness.ts) with:
  - `isStale(timestamp, maxAgeSeconds)`
  - `formatDataAge(timestamp)`
  - `classifyDataStatus(data)` returning `LIVE | RECENT | STALE | FALLBACK | MOCK | MISSING | UNKNOWN`
- Added [dashboard_react/frontend/src/components/ui/DataStatusBadge.tsx](/C:/Users/twone/Desktop/aegis_codex/dashboard_react/frontend/src/components/ui/DataStatusBadge.tsx) and surfaced visible labels on major cards.
- Removed fake “fresh” timestamp generation from the V2 frontend normalizers and fallback paths in:
  - [dashboard_react/frontend/src/services/apiV2.ts](/C:/Users/twone/Desktop/aegis_codex/dashboard_react/frontend/src/services/apiV2.ts)
  - [dashboard_react/frontend/src/hooks/useRealTimeFeed.ts](/C:/Users/twone/Desktop/aegis_codex/dashboard_react/frontend/src/hooks/useRealTimeFeed.ts)
- Fixed the V2 binding mismatch so the selected horizon/timeframe is now forwarded to:
  - HTTP macro fetches
  - HTTP consensus fetches
  - SSE `/api/live-feed`
  - fallback polling after SSE failure
- Added explicit stale/fallback visibility to:
  - [dashboard_react/frontend/src/pages/DashboardV2.tsx](/C:/Users/twone/Desktop/aegis_codex/dashboard_react/frontend/src/pages/DashboardV2.tsx)
  - [dashboard_react/frontend/src/components/assets/AssetConsensusCard.tsx](/C:/Users/twone/Desktop/aegis_codex/dashboard_react/frontend/src/components/assets/AssetConsensusCard.tsx)
  - [dashboard_react/frontend/src/components/macro/MacroRegimeCommentary.tsx](/C:/Users/twone/Desktop/aegis_codex/dashboard_react/frontend/src/components/macro/MacroRegimeCommentary.tsx)
  - [dashboard_react/frontend/src/components/MetricCard.tsx](/C:/Users/twone/Desktop/aegis_codex/dashboard_react/frontend/src/components/MetricCard.tsx)
  - [dashboard_react/frontend/src/components/ConsensusCard.tsx](/C:/Users/twone/Desktop/aegis_codex/dashboard_react/frontend/src/components/ConsensusCard.tsx)
  - [dashboard_react/frontend/src/components/SystemStatus.tsx](/C:/Users/twone/Desktop/aegis_codex/dashboard_react/frontend/src/components/SystemStatus.tsx)
  - [dashboard_react/frontend/src/components/Header.tsx](/C:/Users/twone/Desktop/aegis_codex/dashboard_react/frontend/src/components/Header.tsx)
  - [dashboard_react/frontend/src/components/AIAnalysisCard.tsx](/C:/Users/twone/Desktop/aegis_codex/dashboard_react/frontend/src/components/AIAnalysisCard.tsx)
- Added non-breaking freshness metadata to dashboard-facing backend responses in:
  - [dashboard_react/backend/routes/macro.py](/C:/Users/twone/Desktop/aegis_codex/dashboard_react/backend/routes/macro.py)
  - [dashboard_react/backend/routes/dashboard.py](/C:/Users/twone/Desktop/aegis_codex/dashboard_react/backend/routes/dashboard.py)
  - [dashboard_react/backend/routes/stream.py](/C:/Users/twone/Desktop/aegis_codex/dashboard_react/backend/routes/stream.py)
  - [dashboard_react/backend/main.py](/C:/Users/twone/Desktop/aegis_codex/dashboard_react/backend/main.py)

## Dashboard data-source map

| Frontend file | Endpoint called | Expected symbol/timeframe | Actual symbol/timeframe used now | Timestamp source | Freshness check | Fallback behavior |
| --- | --- | --- | --- | --- | --- | --- |
| `frontend/src/pages/Dashboard.tsx` via `useMetrics` | `GET http://localhost:8502/api/dashboard` | selected symbol + selected timeframe | matches selected symbol/timeframe | backend now returns `timestamp=null` unless a real source timestamp exists | yes | yes, explicit status badge |
| `frontend/src/components/AIAnalysisCard.tsx` | `GET http://localhost:8502/api/analysis?symbol=...&timeframe=...` | selected symbol + selected timeframe | matches selected symbol/timeframe | analyzer timestamp if provided, otherwise `null` | yes | yes, error view shows last successful source/time |
| `frontend/src/hooks/useLiveFeed.ts` on legacy intelligence tab | `GET http://localhost:8502/api/live-feed?symbol=...` | selected symbol + selected timeframe | symbol only; timeframe still server-default for the legacy contract | stream payload timestamp only if backend provides one | no real legacy freshness model | warning added; still legacy-limited |
| `frontend/src/pages/DashboardV2.tsx` + `apiV2.ts` | `GET http://localhost:8502/api/macro?horizon=...` | selected V2 horizon | matches selected horizon | backend `timestamp/last_updated` from Sentinel if present, otherwise `null` | yes | yes |
| `frontend/src/pages/DashboardV2.tsx` + `apiV2.ts` | `GET http://localhost:8502/api/consensus?symbol=...&timeframe=...&horizon=...` | per-card symbol + horizon-derived timeframe | now matches selected symbol/timeframe/horizon | backend `timestamp/last_updated` if present, otherwise `null` | yes | yes |
| `frontend/src/pages/DashboardV2.tsx` + `apiV2.ts` | `POST http://localhost:8005/process` | per-card symbol + horizon-derived timeframe | now matches selected symbol/timeframe/horizon | process timestamp if provided, otherwise `null` | yes | yes, gateway-only path is labeled fallback |
| `frontend/src/hooks/useRealTimeFeed.ts` | `GET http://localhost:8502/api/live-feed?symbol=BTC/USDT&timeframe=...&period=7d&horizon=...` | BTC/USDT + horizon-derived timeframe | now matches selected V2 timeframe/horizon | macro/consensus timestamps inside SSE snapshot | yes | yes, SSE reconnect and polling are labeled fallback |
| `frontend/src/hooks/useRealTimeFeed.ts` fallback | `GET /api/macro`, `GET /api/consensus`, `GET http://localhost:8007/dashboard/exit_attribution`, `GET http://localhost:8005/consensus/historical_edge` | same V2 selection | now uses same horizon/timeframe for macro + consensus | upstream timestamps only; never `Date.now()` | yes | yes |

## Which dashboard sources remain legacy

- The `/` page is still a legacy aggregate dashboard backed by `http://localhost:8502/api/dashboard`.
- The legacy intelligence tab still uses the old `useLiveFeed` contract and does not pass timeframe into SSE.
- V2 still depends on mixed legacy backends:
  - `8502` for macro + gateway consensus + SSE
  - `8005` for `/process` and historical edge
  - `8007` for exit attribution

## Endpoints that still may be stale or unknown

- `GET /api/dashboard`
  - now exposes `source`, `fallback_used`, and `data_status`
  - still cannot claim true freshness because the aggregate payload does not carry upstream metric timestamps
  - cards will usually show `UNKNOWN DATA` unless metrics are missing, in which case they show `MISSING DATA` or `FALLBACK DATA`
- `GET /api/consensus`
  - now exposes freshness metadata
  - for live Prometheus queries the source timestamp is still generally unknown
- `GET /api/analysis`
  - now exposes freshness metadata
  - remains `UNKNOWN DATA` if the analyzer response does not include a real timestamp
- `GET /api/live-feed`
  - V2 selection is now aligned
  - legacy intelligence usage is still older-contract and should be treated as legacy-only
- legacy system health inside `GET /api/dashboard`
  - still uses mocked health data
  - now explicitly labeled `MOCK DATA`

## How freshness is now displayed

- Major cards now show a visible status pill:
  - `LIVE DATA`
  - `RECENT DATA`
  - `STALE DATA`
  - `FALLBACK DATA`
  - `MOCK DATA`
  - `MISSING DATA`
  - `UNKNOWN DATA` when the backend has no trustworthy source timestamp
- Status details show:
  - `Source: ...`
  - `Updated: ...`
- Error states now preserve and display:
  - `Last successful update: ...`
  - `Source: ...`
- Missing timestamps are no longer replaced by `Date.now()` or `new Date().toISOString()`.

## Backend metadata added

- `/api/macro`
  - now returns `source`, `timestamp`, `last_updated`, `fallback_used`, `data_status`
- `/api/consensus`
  - now returns `source`, `timestamp`, `last_updated`, `fallback_used`, `data_status`
- `/api/dashboard`
  - now returns top-level freshness metadata
  - per-metric metadata
  - consensus metadata
  - explicit `mock_system_health`
- `/api/analysis`
  - now returns `source`, `timestamp`, `last_updated`, `fallback_used`, `data_status`
- `/api/live-feed`
  - now forwards V2 `horizon` to downstream macro + consensus requests
  - snapshot normalization no longer fabricates fresh timestamps for fallback payloads

## Known limitations

- The legacy intelligence tab still uses an older SSE payload contract and does not pass timeframe to the feed. A warning is shown instead of forcing a risky retrofit in this phase.
- `http://localhost:8502/api/dashboard` still cannot prove Prometheus source freshness, so aggregate cards will often show `UNKNOWN DATA`.
- `system_health` in the legacy aggregate response is still mocked.
- No business-data `localStorage` or `sessionStorage` cache was found, so the stale-data issue was not browser-cache driven.
- `frontend/src/components/OptimizerCard.tsx` still posts a mock trade payload to optimizer endpoints when that tab is used. This was not changed in this phase.

## Verification

- Backend syntax check passed with `py_compile` for:
  - `dashboard_react/backend/main.py`
  - `dashboard_react/backend/routes/dashboard.py`
  - `dashboard_react/backend/routes/macro.py`
  - `dashboard_react/backend/routes/stream.py`
- Frontend static verification is partially blocked by the local toolchain:
  - `npm run build` failed because `tsc` was not resolved correctly from the local environment
  - direct `typescript` invocation also failed because the local install is incomplete (`Cannot find module '../lib/tsc.js'`)
- No frontend unit-test harness was present in `dashboard_react/frontend/package.json`, so no automated frontend tests were added in this phase.

## Manual verification

1. Start backend:
   - `cd C:\Users\twone\Desktop\aegis_codex\dashboard_react\backend`
   - `python main.py`
2. Start frontend:
   - `cd C:\Users\twone\Desktop\aegis_codex\dashboard_react\frontend`
   - `npm run dev -- --port 3001`
3. Open [http://localhost:3001](http://localhost:3001).
4. Verify the legacy page `/`:
   - Select `BTC/USDT`
   - Change timeframe between `1h`, `4h`, and `1d`
   - Confirm each major card shows a visible status badge
   - Confirm the header shows browser time separately from data status
   - Confirm the footer/header no longer imply a fake fresh timestamp
5. Verify the V2 page [http://localhost:3001/v2](http://localhost:3001/v2):
   - Confirm the `Data Source Binding` banner is visible
   - Confirm macro and asset cards display status, source, and updated age
   - Switch horizon between `short`, `medium`, and `long`
   - Confirm the displayed timeframe changes with the selected horizon
   - Confirm V2 cards continue to show BTC/USDT + the same timeframe/horizon in both fetch-backed and SSE-backed data
6. Verify failure behavior:
   - Temporarily stop the service on `8005` if available, or otherwise break the `/process` path
   - Refresh `/v2`
   - Confirm affected cards show `FALLBACK DATA` or `Data unavailable`
   - Confirm the UI shows `Last successful update` and `Source`
   - Confirm no card suddenly flips to a brand-new current timestamp
7. Verify analysis behavior:
   - Open the `AI Analysis` tab on `/`
   - Refresh once while `8007` is healthy
   - Then stop or block `8007`
   - Refresh again and confirm the error state shows the last successful source/time instead of presenting old analysis as current

## Next step

Connect both dashboard modes to one canonical live/verified data provider with a single freshness contract:

- one authoritative source for symbol/timeframe selection
- one authoritative source timestamp per card
- one authoritative `fallback_used` signal
- one deprecation path for the legacy intelligence SSE contract
