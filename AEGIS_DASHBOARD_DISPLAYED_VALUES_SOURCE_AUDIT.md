# AEGIS Dashboard Displayed Values Source Audit

Date: 2026-05-01
Workspace: `C:\Users\twone\Desktop\aegis_codex`
Scope: Audit only. No existing source files modified.

## 1. Exact file(s) where these values come from

Primary sources for the displayed macro/portfolio values:

- `dashboard_react/backend/routes/macro.py:23-36`
  Hardcoded `_FALLBACK_METRICS` contains:
  `dxy=98.5`, `vix=22.0`, `us10y=4.25`, `brent=92.0`, `xau=4800.0`, `btc_d=59.8`, `usdt_d=7.5`, `hg=4.5`, `event_risk_score=0.25`, `hours_to_event=48`, `regime=NORMALIZATION`.

- `dashboard_react/backend/routes/macro.py:49-107`
  `GET /api/macro` returns those values directly on Sentinel failure, and also merges Sentinel payload over those fallback values on partial success.

- `dashboard_react/backend/services/portfolio_allocator.py:10-22, 102-115`
  Regime/horizon allocation weights for `gold / btc / bond / commodity / cash`.

- `dashboard_react/frontend/src/pages/DashboardV2.tsx:79-90, 166-178, 285, 405, 418`
  The V2 page fetches macro data and renders the macro and portfolio panels from `effectiveMacro`.

- `dashboard_react/frontend/src/components/macro/MacroRegimeCommentary.tsx:29-88, 91-137`
  Renders the displayed macro chips, regime badge, `HEDGE ON`, and the "AI Makro Yorumu" text.

- `dashboard_react/frontend/src/components/portfolio/AllocationWithTip.tsx:15-20, 33-52, 55-121`
  Renders the portfolio allocation bars and the `"Dağılım dengede, rebalance gerekmiyor."` tip.

Supporting/secondary sources that duplicate or propagate the same values:

- `dashboard_react/backend/routes/stream.py:151-197`
  SSE macro normalization fallback repeats the same numeric set except `event_risk_score` fallback is `0.18` there.

- `dashboard_react/backend/routes/stream.py:503-538`
  SSE snapshot builder injects `macro_stream_fallback` when `/api/macro` cannot be fetched.

- `dashboard_react/backend/routes/dashboard.py:250-267`
  Non-crypto asset consensus scoring also seeds from `98.5 / 22.0 / 4.25 / 92.0 / 4800.0`.

- `dashboard_react/backend/routes/dashboard.py:300-370`
  `GET /api/consensus` uses those defaults for XAU/XAG/BOND/CASH asset consensus when deriving macro-based scores.

## 2. Whether each value is hardcoded, mock, fallback, static report, or backend response

| Displayed item | Exact source | Classification |
|---|---|---|
| `DXY 98.5` | `routes/macro.py:25` | Hardcoded fallback metric returned by backend |
| `VIX 22.0` | `routes/macro.py:26` | Hardcoded fallback metric returned by backend |
| `US10Y 4.25%` | `routes/macro.py:27` | Hardcoded fallback metric returned by backend |
| `Brent 92.0` | `routes/macro.py:28` | Hardcoded fallback metric returned by backend |
| `XAU 4800` | `routes/macro.py:29` | Hardcoded fallback metric returned by backend |
| `BTC.D 59.8%` | `routes/macro.py:30` | Hardcoded fallback metric returned by backend |
| `USDT.D 7.5%` | `routes/macro.py:31` | Hardcoded fallback metric returned by backend |
| `EvRisk 51%` | not hardcoded as `51`; formatted from `event_risk_score * 100` in `MacroRegimeCommentary.tsx:88` and `CrossAlignmentPanel.tsx:196-201` | Backend response value if runtime `event_risk_score ~= 0.51`; likely merged over fallback metrics by `routes/macro.py:66-69` |
| `NORMALIZATION` regime | `routes/macro.py:35`, `routes/macro.py:70`, fallback path `routes/macro.py:103` | Hardcoded fallback/default regime |
| XAU/BTC/BOND/EMTIA/CASH allocation | `portfolio_allocator.py:11-14`, `portfolio_allocator.py:102-115` via `routes/macro.py:71` or `:92` | Backend-generated from hardcoded regime/horizon weights |
| `"Dağılım dengede, rebalance gerekmiyor."` | `AllocationWithTip.tsx:33-36` | Frontend-generated label from missing rebalance actions |
| `HEDGE ON` | `MacroRegimeCommentary.tsx:110-113`, with `hedge` often derived in `apiV2.ts:411` | Frontend-generated badge, not guaranteed to be backend-declared |
| AI macro commentary text | `MacroRegimeCommentary.tsx:29-77` | Frontend-generated rule text, not analyzer output |

Important nuance:

- `EvRisk 51%` is not hardcoded anywhere in the audited UI/backend files.
- The exact combination `98.5 / 22.0 / 4.25 / 92.0 / 4800 / 59.8 / 7.5 / NORMALIZATION` plus a non-fallback `EvRisk` can happen because `routes/macro.py:66-69` overlays live Sentinel event-risk fields onto the fallback macro snapshot.

## 3. Whether the dashboard labels them as real/live/legacy/fallback

Macro route labeling:

- `dashboard_react/backend/routes/macro.py:73-89`
  Success path labels payload as:
  `source: "sentinel-ai"`
  `fallback_used: false`
  `data_status: LIVE or UNKNOWN depending timestamp`

- `dashboard_react/backend/routes/macro.py:93-107`
  Failure path labels payload as:
  `source: "macro_static_fallback"`
  `fallback_used: true`
  `data_status: FALLBACK`

SSE stream labeling:

- `dashboard_react/backend/routes/stream.py:180-185`
  Macro snapshot is labeled from payload metadata, otherwise defaults to `macro_stream_fallback` and `FALLBACK`.

Frontend labeling:

- `dashboard_react/frontend/src/components/ui/DataStatusBadge.tsx:23-30, 54-77`
  Visible labels are `LIVE DATA`, `RECENT DATA`, `STALE DATA`, `FALLBACK DATA`, `MOCK DATA`, `MISSING DATA`, `UNKNOWN DATA`.

- `dashboard_react/frontend/src/utils/dataFreshness.ts:155-212`
  Badge status comes from explicit `data_status` first, then from `fallback_used`, `source` hints, and timestamp freshness.

- `dashboard_react/frontend/src/components/layout/GlobalHeader.tsx:29-36, 83-90`
  Header uses a separate connection label:
  `Live`
  `Reconnecting...`
  `Manual Sync`

Legacy/v2 labeling:

- `dashboard_react/frontend/src/components/layout/GlobalHeader.tsx:139-162`
  The page is explicitly switchable between `Legacy` and `V2`.

Audit conclusion on labeling:

- The dashboard can correctly label the macro payload as `FALLBACK DATA` when `routes/macro.py` uses its fallback path.
- But the success path in `routes/macro.py` can still contain fallback-filled metrics while labeling the whole payload as `sentinel-ai` and `fallback_used=false`.
- That means the UI can present partly fallback-filled numbers without clearly saying they are partial fallback values.

## 4. Which React component displays them

Macro values and regime:

- `dashboard_react/frontend/src/components/macro/MacroRegimeCommentary.tsx`
  Displays `DXY`, `VIX`, `US10Y`, `Brent`, `XAU`, `BTC.D`, `USDT.D`, `EvRisk`, regime badge, `HEDGE ON`, and commentary text.

Portfolio allocation:

- `dashboard_react/frontend/src/components/portfolio/AllocationWithTip.tsx`
  Displays the XAU/BTC/BOND/EMTIA/CASH allocation bars and rebalance tip.

Page wiring:

- `dashboard_react/frontend/src/pages/DashboardV2.tsx:405`
  Renders `<MacroRegimeCommentary macro={effectiveMacro} />`

- `dashboard_react/frontend/src/pages/DashboardV2.tsx:418`
  Renders `<AllocationWithTip macro={effectiveMacro} vade={vade} />`

Additional EvRisk display:

- `dashboard_react/frontend/src/components/validation/CrossAlignmentPanel.tsx:195-201`
  Shows `EvRisk: XX%`.

## 5. Which API call or data object feeds them

Direct feed to the displayed panels:

- `dashboard_react/frontend/src/pages/DashboardV2.tsx:166`
  `fetchMacro(vade, { signal })`

- `dashboard_react/frontend/src/services/apiV2.ts:641-647`
  `fetchMacro()` calls `GET /api/macro?horizon=...`

- `dashboard_react/frontend/src/pages/DashboardV2.tsx:285`
  `const effectiveMacro = macroHorizon ?? macro;`

- `dashboard_react/frontend/src/services/apiV2.ts:410-411`
  If backend omits `macro_score` or `hedge`, frontend derives them locally. With `VIX 22.0`, this path makes `hedge=true`, which produces the visible `HEDGE ON` badge.

Meaning:

- `macroHorizon` from `GET /api/macro` is preferred over SSE macro.
- Both the macro panel and the portfolio panel read from the same `effectiveMacro` object.

Backend producer:

- `dashboard_react/backend/routes/macro.py:49-107`
  `/api/macro` is the main producer for the displayed macro/portfolio payload.

SSE producer:

- `dashboard_react/backend/routes/stream.py:479-568`
  `/api/live-feed` builds a snapshot that includes `snapshot.macro`, but `DashboardV2` still prefers `macroHorizon` when available.

Portfolio object specifics:

- `routes/macro.py:71` and `:92`
  `allocation_target = get_allocation_weights(...)`

- `dashboard_react/frontend/src/services/apiV2.ts:417-421`
  If `allocation_current` is missing, frontend sets `current = target`.

- `dashboard_react/frontend/src/services/apiV2.ts:438`
  If there are no rebalance actions, `rebalance_required` becomes false.

Why `"Dağılım dengede"` appears:

- `AllocationWithTip.tsx:34-36`
  It appears whenever `rebalance_required` is false or `rebalance_actions` is empty.
- Because `/api/macro` only provides `allocation_target` and not a real current allocation, frontend collapses current to target, so it looks perfectly balanced.

## 6. Whether timestamp is source-provided or frontend-generated

Macro payload:

- `routes/macro.py:72-77`
  Timestamp comes from Sentinel payload:
  `data.timestamp` or `macro_snapshot.timestamp`

- `routes/macro.py:95-96`
  Fallback path returns `timestamp: null`, `last_updated: null`

Frontend:

- `DataStatusBadge.tsx:56-75`
  Frontend does not invent a source timestamp; it only formats age text from the provided timestamp.

- `DashboardV2.tsx:325` and `:345`
  Header/badge use `lastSuccessfulUpdate ?? effectiveMacro.last_updated ?? effectiveMacro.timestamp`

SSE wrapper:

- `routes/stream.py:557`
  The outer SSE snapshot has its own server-generated wrapper timestamp.

- `useRealTimeFeed.ts:194-205` and `:300-313`
  Frontend chooses `lastSuccessfulUpdate` from macro/consensus timestamps, not from the outer SSE wrapper timestamp.

Header clock:

- `GlobalHeader.tsx:65-70`
  The clock shown in the header is frontend-generated current time and is unrelated to data freshness.

## 7. Why values still show even when 8502/8005/8007 are offline

Repository-level explanation:

1. The exact macro numbers are hardcoded backend fallbacks.
   - `routes/macro.py:23-36`
   - `routes/stream.py:154-167`
   - `routes/dashboard.py:253`

2. The V2 page keeps last successful live state in memory.
   - `useRealTimeFeed.ts:117, 195-206, 214-230`
   - `lastKnownStateRef` is reused after stream failure.

3. Asset cards also keep last successful data in memory.
   - `DashboardV2.tsx:45, 147-160, 199-202, 208-216`
   - `AssetConsensusCard.tsx:81-114`

4. `8005` and `8007` are not required for the macro card itself.
   - Macro card comes from `/api/macro`
   - `8005` mainly affects `/process`
   - `8007` mainly affects analyzer attribution

5. The macro route can return a mixed payload.
   - `routes/macro.py:66-69`
   - If Sentinel event-risk responds but omits the macro snapshot, fallback macro numbers remain while live event-risk overwrites `event_risk_score`.

Important limitation from the audited code:

- No frontend proxy was found in `dashboard_react/frontend/vite.config.ts:4-19`.
- Frontend defaults point directly to `http://localhost:8502`, `:8005`, `:8007` in `apiV2.ts:164-166` and `useRealTimeFeed.ts:26`.
- No dashboard data persistence was found in frontend storage.

Therefore:

- If `/v2` still shows these values without a full reload, the code supports that via in-memory last-successful state.
- If `/v2` still shows them after a clean hard refresh while `8502` is truly unreachable, that would mean the backend was reachable at least once in that browser tab/session before failure, or the runtime environment differs from the repo defaults.
- The codebase itself does not contain a frontend-only static macro bootstrap for first-load rendering.

## 8. Recommended patch plan

1. Replace misleading labels
   - Change mixed-success `/api/macro` responses from plain `sentinel-ai` to something like `sentinel-ai-partial-fallback`.
   - Do not label partial fallback-filled payloads as live.

2. Mark these values as `MOCK` / `FALLBACK` / `LEGACY` when not verified
   - Add explicit `field_sources` or `verified_fields` in `/api/macro`.
   - Example: `dxy: fallback`, `vix: fallback`, `event_risk_score: source`.

3. Hide or gray out values if source services are offline
   - If `fallback_used` is true, gray the metric chips and allocation bars.
   - If source timestamp is null, show `timestamp unavailable` prominently, not as a subtle badge detail only.

4. Do not call them live data unless verified
   - Require a real source timestamp plus verified field coverage before setting `data_status=LIVE`.
   - Partial source data should become `PARTIAL_FALLBACK` or `DEGRADED`, not `LIVE` or plain `UNKNOWN`.

5. Stop frontend from inventing hedge state
   - `apiV2.ts:411` currently derives `hedge` from thresholds even if backend did not provide it.
   - Backend and frontend thresholds are inconsistent:
     - frontend macro fetch path: `vix >= 22`
     - backend SSE path: `vix >= 25 or dxy >= 102`
   - Make backend the single source of truth for `hedge`.

6. Stop frontend from pretending current allocation equals target allocation
   - `apiV2.ts:417-421`
   - If backend does not provide `allocation_current`, show `current allocation unavailable` instead of copying target into current.

7. Mark client commentary honestly
   - `"AI Makro Yorumu"` in `MacroRegimeCommentary.tsx` is rule-based frontend text.
   - Relabel it as `Client commentary`, `Rule-based commentary`, or feed it from a verified backend/analyzer endpoint.

8. Make fallback visibility stronger in header
   - If macro payload is fallback or partial fallback, header should not show a plain `Live` pill.
   - Connection status and data freshness/status should be unified.

9. Add offline-aware empty state for hard refresh
   - With no last successful state and no backend, show `data unavailable` instead of any stale-looking macro/portfolio presentation.

## 9. Do not modify files

Completed.

- No existing repository files were modified during this audit.
- Only this new audit report file was created.

## Ruled out / secondary notes

- `consensus_engine/main.py:537-541` has different fallback macro defaults (`103 / 20 / 4.0 / 85 / 2200 / 0.3`), so it is not the source of the displayed `98.5 / 22.0 / 4.25 / 92.0 / 4800` set.
- Analyzer-related code is not the source of the macro panel values. In this V2 path, analyzer is used for attribution, while the visible macro commentary is generated in `MacroRegimeCommentary.tsx`.
