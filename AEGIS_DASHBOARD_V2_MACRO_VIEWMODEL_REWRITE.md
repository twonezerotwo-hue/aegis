# AEGIS Dashboard V2 Macro ViewModel Rewrite

## Goal

Replace the V2 macro display path with one canonical macro view model so the UI no longer infers live/fallback state independently inside multiple components.

## Scope

Changed:

- `dashboard_react/frontend/src/types/dashboardV2.ts`
- `dashboard_react/frontend/src/services/apiV2.ts`
- `dashboard_react/frontend/src/components/macro/MacroRegimeCommentary.tsx`
- `dashboard_react/frontend/src/components/portfolio/AllocationWithTip.tsx`
- `dashboard_react/frontend/src/components/validation/CrossAlignmentPanel.tsx`
- `dashboard_react/frontend/src/pages/DashboardV2.tsx`
- static checks under `dashboard_react/backend/tests`

Not changed:

- `aegis_core`
- `/aegis-core/*`
- Data Integrity Gate
- Risk Engine wrapper
- Kill Switch wrapper
- OwnerBrief
- Audit Record
- freshness badge utility
- horizon-aware allocator
- asset consensus provenance work

## Canonical macro view model

`apiV2.ts` now exposes one canonical macro function:

- `normalizeMacroViewModel(rawMacro): MacroViewModel`

`MacroViewModel` remains the single frontend contract for macro display and carries:

- `data_status`
- `verified`
- `live`
- `source`
- `fallback_used`
- `fallback_fields`
- `field_sources`
- `metrics`
- `warnings`

It also preserves the existing display fields already needed by V2:

- `regime`
- `macro_score`
- `hedge`
- `allocation_target`
- `allocation_current`
- `allocation_horizon`
- `allocation_profile`
- `allocation_basis`
- `rebalance_required`
- `rebalance_actions`

## Hard invariants

The canonical view model now enforces:

1. If `fallback_fields.length > 0`
   - `data_status = PARTIAL_FALLBACK`
   - `verified = false`
   - `live = false`

2. If the fallback cluster is detected:
   - `dxy = 98.5`
   - `vix = 22.0`
   - `us10y = 4.25`
   - `brent = 92.0`

Then the canonical view model force-marks those fields as fallback and downgrades the macro payload to `PARTIAL_FALLBACK`.

## Rendering changes

### MacroRegimeCommentary

- consumes only `MacroViewModel`
- only generates live commentary when:
  - `data_status === LIVE`
  - `verified === true`
  - `live === true`
- otherwise shows:
  - `NOT FULLY VERIFIED`
  - `FALLBACK`
  - or `NOT VERIFIED`

### AllocationWithTip

- consumes only `MacroViewModel`
- does not show verified rebalance language unless macro is fully live + verified
- uses:
  - `Verified allocation decision unavailable because macro data is not fully verified.`

### CrossAlignmentPanel

- consumes only `MacroViewModel`
- if macro is not fully live + verified:
  - macro regime status becomes `UNVERIFIED`
  - hedge status becomes `UNVERIFIED`
  - VIX status becomes `UNVERIFIED`

### DashboardV2 page-level warning

- now gates the top macro warning banner from canonical `MacroViewModel` flags instead of recomputing visibility from fallback fields

## Static checks added or updated

- fallback cluster always becomes `PARTIAL_FALLBACK`
- `MacroViewModel` with `fallback_fields` cannot be `LIVE`
- `AllocationWithTip` cannot show verified rebalance language for partial/unverified macro
- `CrossAlignmentPanel` cannot show `ONAY` for fallback/unverified macro
- `MacroRegimeCommentary` shows `NOT FULLY VERIFIED` and disables live commentary

## Result

The V2 macro display path now has one canonical macro view model and one canonical truth for:

- whether macro data is live
- whether macro data is verified
- whether macro data is fallback or partial fallback
- which exact fields are fallback-derived

That removes the previous split between API normalization and component-side live/fallback inference.
