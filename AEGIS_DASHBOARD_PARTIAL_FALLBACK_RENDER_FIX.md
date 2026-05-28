# AEGIS Dashboard Partial Fallback Render Fix

## Exact rendered path

- `dashboard_react/frontend/src/pages/DashboardV2.tsx`
  - uses `useRealTimeFeed(...)` for SSE macro and BTC consensus
  - also calls `fetchMacro(...)` for the selected horizon
  - renders `effectiveMacro = macroHorizon ?? macro`
- REST macro path:
  - `dashboard_react/frontend/src/services/apiV2.ts`
  - `GET /api/macro`
  - `dashboard_react/backend/routes/macro.py`
- SSE macro path:
  - `dashboard_react/frontend/src/hooks/useRealTimeFeed.ts`
  - `GET /api/live-feed`
  - `dashboard_react/backend/routes/stream.py`
  - stream snapshot normalization was previously rebuilding macro objects without preserving field-level fallback metadata
- Rendered consumers of macro verification state:
  - `dashboard_react/frontend/src/components/macro/MacroRegimeCommentary.tsx`
  - `dashboard_react/frontend/src/components/portfolio/AllocationWithTip.tsx`
  - `dashboard_react/frontend/src/components/validation/CrossAlignmentPanel.tsx`

## Root cause

- Backend partial-fallback detection originally only looked for missing Sentinel fields.
- If Sentinel returned the same hardcoded fallback constants as a full-looking payload, the macro response could still appear `LIVE`.
- SSE normalization in `stream.py` also dropped:
  - `fallback_fields`
  - `field_sources`
  - `warning`
  - hedge unverified state
- The UI therefore had enough macro numbers to render commentary and allocation text, but not enough provenance to stop calling them live or verified.

## Fix summary

- `macro.py`
  - now emits `field_sources`
  - treats a suspicious cluster of exact fallback constants as partial fallback
  - keeps fallback values, but marks them unverified
- `stream.py`
  - preserves `fallback_fields`, `source_fields`, `field_sources`, `warning`, `verified`, `live`
  - forces `PARTIAL_FALLBACK` in the SSE path when field-level fallback exists
- `apiV2.ts`
  - preserves `fallback_fields` and `field_sources`
  - never upgrades partial fallback to live because of timestamp or source label
- `MacroRegimeCommentary.tsx`
  - shows `PARTIAL FALLBACK DATA`
  - shows `NOT FULLY VERIFIED`
  - shows field-level fallback badges
  - replaces AI macro commentary for partial fallback
- `AllocationWithTip.tsx`
  - replaces verified rebalance wording for partial fallback
- `CrossAlignmentPanel.tsx`
  - final checklist now shows `UNVERIFIED` instead of `ONAY` for macro regime, VIX, and hedge when fallback rules apply

## Files changed

- `dashboard_react/backend/routes/macro.py`
- `dashboard_react/backend/routes/stream.py`
- `dashboard_react/frontend/src/services/apiV2.ts`
- `dashboard_react/frontend/src/types/dashboardV2.ts`
- `dashboard_react/frontend/src/pages/DashboardV2.tsx`
- `dashboard_react/frontend/src/components/macro/MacroRegimeCommentary.tsx`
- `dashboard_react/frontend/src/components/portfolio/AllocationWithTip.tsx`
- `dashboard_react/frontend/src/components/validation/CrossAlignmentPanel.tsx`
- `dashboard_react/backend/tests/test_macro_fallback_metadata.py`
- `dashboard_react/backend/tests/test_dashboard_partial_fallback_render_static.py`

## Expected result at localhost:3001/v2

- If any macro field is fallback:
  - macro must not render as `LIVE DATA`
  - macro commentary must not present fallback values as verified AI commentary
  - allocation must not say the allocation is stably verified
  - final checklist must not show macro approval as `ONAY`
- If `VIX` is in `fallback_fields`:
  - VIX checklist row must show `UNVERIFIED`
- If hedge is derived from fallback macro:
  - hedge checklist row must show `UNVERIFIED`

## Remaining limitation

- The dashboard can now correctly label partial fallback and field-level fallback in the actual V2 render path, but the underlying fallback numbers are still illustrative until a canonical verified live macro provider is connected per field.
