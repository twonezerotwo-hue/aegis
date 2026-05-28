# AEGIS Dashboard Fallback Visibility Patch

## Exact root cause

The suspicious macro values were coming from `dashboard_react/backend/routes/macro.py`, where `_FALLBACK_METRICS` hardcoded values such as `DXY 98.5`, `VIX 22.0`, `US10Y 4.25`, `Brent 92.0`, `XAU 4800`, `BTC.D 59.8`, `USDT.D 7.5`, and `NORMALIZATION`.

Two things made them look more authoritative than they were:

1. The backend returned fallback-filled macro payloads without enough explicit metadata to distinguish:
   - full hardcoded fallback
   - partial Sentinel response merged over fallback

2. The frontend normalized and presented that payload in ways that looked fresher or more verified than it was:
   - it could derive hedge state from fallback metrics
   - it reused non-macro freshness signals in the page header/status area
   - it rendered AI commentary and allocation messaging without clearly separating verified from unverified macro inputs

## Files changed

- `dashboard_react/backend/routes/macro.py`
- `dashboard_react/backend/tests/test_macro_fallback_metadata.py`
- `dashboard_react/frontend/src/services/apiV2.ts`
- `dashboard_react/frontend/src/pages/DashboardV2.tsx`
- `dashboard_react/frontend/src/components/macro/MacroRegimeCommentary.tsx`
- `dashboard_react/frontend/src/components/portfolio/AllocationWithTip.tsx`
- `dashboard_react/frontend/src/components/ui/DataStatusBadge.tsx`
- `dashboard_react/frontend/src/types/dashboardV2.ts`
- `dashboard_react/frontend/src/utils/dataFreshness.ts`

## How fallback is now labeled

Full hardcoded fallback from `macro.py` now returns:

- `data_status: "FALLBACK"`
- `source: "hardcoded_fallback"`
- `fallback_used: true`
- `verified: false`
- `live: false`
- `warning: "Macro data is fallback/hardcoded and not verified live market data."`
- `fallback_fields: [...]` containing all fields sourced from `_FALLBACK_METRICS`
- `source_fields: []`

Frontend behavior now preserves that status instead of upgrading it to live/recent semantics.

Visible UI changes:

- banner on `DashboardV2`
- `FALLBACK DATA` badge
- `NOT VERIFIED` badge
- `SOURCE: hardcoded_fallback` badge
- no fake fresh timestamp generation

## How partial fallback is now labeled

When Sentinel returns only some fields and the backend fills the rest from fallback, `macro.py` now returns:

- `data_status: "PARTIAL_FALLBACK"`
- `source: "sentinel_partial_plus_fallback"`
- `fallback_used: true`
- `verified: false`
- `live: false`
- `fallback_fields: [...]` only for fields missing from Sentinel
- `source_fields: [...]` for fields actually provided by Sentinel
- warning text explaining partial Sentinel plus hardcoded fallback composition

Visible UI changes:

- `PARTIAL FALLBACK` badge
- `NOT VERIFIED` badge
- `SOURCE: sentinel_partial_plus_fallback` badge
- warning banner on `DashboardV2`

## What changed in AI macro commentary

`MacroRegimeCommentary.tsx` no longer presents fallback macro analysis as if it were verified live analysis.

Behavior now:

- verified data keeps the derived commentary behavior
- fallback and partial fallback show:
  - `UNVERIFIED FALLBACK COMMENTARY: Verified macro data is unavailable. Fallback values are shown for interface continuity only.`
- unverified macro payloads also show:
  - `NOT VERIFIED`
  - source badge
  - explicit warning text from backend when available
- frontend-derived hedge from unverified macro data is labeled `HEDGE UNVERIFIED`

## What changed in portfolio allocation and rebalance messaging

`AllocationWithTip.tsx` now treats fallback or partial-fallback macro input as illustrative only.

Behavior now:

- fallback/unverified state shows `Fallback-based illustrative allocation`
- recommendation text becomes:
  - `Verified allocation decision unavailable because macro data is fallback/partial.`
- the previous reassuring rebalance message is no longer used for fallback data
- buy/sell delta highlighting is suppressed for unverified macro payloads
- `NOT VERIFIED` and source badges are shown alongside the allocation block

## Dashboard visibility behavior

`DashboardV2.tsx` now shows a visible warning banner when macro status is:

- `FALLBACK`
- `PARTIAL_FALLBACK`
- `MOCK`
- `MISSING`
- `UNKNOWN`

Banner text:

`Macro data is not verified live data. Displayed values may be fallback, partial, or stale.`

The page also now uses the macro payload's own timestamp for macro freshness display instead of substituting a newer non-macro timestamp.

## Verification performed

Backend:

- `pytest tests/test_macro_fallback_metadata.py -q -p no:cacheprovider`
- result: `2 passed`

Frontend static verification:

- searched for the new warning and labeling strings in:
  - `DashboardV2.tsx`
  - `MacroRegimeCommentary.tsx`
  - `AllocationWithTip.tsx`
  - `DataStatusBadge.tsx`
  - `macro.py`

Frontend compile check:

- `node ./node_modules/typescript/lib/tsc.js --noEmit`
- result: passed

Note:

- full `npm run build` did not complete in this environment because Vite/esbuild hit a local `spawn EPERM` process-launch restriction while loading `vite.config.ts`
- the TypeScript compile check completed successfully, so the edited TS/TSX code type-checks

## Manual verification steps at localhost:3001/v2

1. Open `http://localhost:3001/v2`.
2. Confirm the macro block shows a warning banner when Sentinel-backed macro data is unavailable or partial.
3. Confirm the macro panel shows:
   - `FALLBACK DATA` or `PARTIAL FALLBACK`
   - `NOT VERIFIED`
   - `SOURCE: hardcoded_fallback` or `SOURCE: sentinel_partial_plus_fallback`
4. Confirm the macro commentary does not read like verified live analysis when fallback is active.
5. Confirm a frontend-derived hedge on fallback data appears as `HEDGE UNVERIFIED`.
6. Confirm the allocation section shows `Fallback-based illustrative allocation`.
7. Confirm the allocation recommendation reads:
   - `Verified allocation decision unavailable because macro data is fallback/partial.`
8. Confirm the page is not showing a fake fresh macro timestamp when the macro payload itself has no source timestamp.

## Remaining limitation

The patch fixes labeling, trust signaling, and fallback visibility. It does not connect a real live macro market-data provider. Until a verified live provider is available and consistently reachable, the dashboard can still display fallback or partial-fallback values, but it should no longer present them as live or verified market data.
