# AEGIS Dashboard V2 — Canonical Macro ViewModel Rewrite

## Overview

The canonical macro view model (MacroViewModel) is the single normalized representation
of all macro data consumed by the frontend. It is produced by `normalizeMacroViewModel()`
in `apiV2.ts` from the raw backend response.

## MacroViewModel contract

All fields are explicitly typed. The key design decisions:

- `data_status`: Single canonical status string (LIVE | PARTIAL_FALLBACK | FALLBACK | MOCK | MISSING | UNKNOWN)
- `verified`: true only when ALL fields are from live sources and no fallback was used
- `live`: same as verified — redundant but kept for backwards compatibility
- `fallback_fields`: array of field names that used hardcoded fallback values
- `field_sources`: per-field source string (from backend `field_sources` map)
- `allocation_target`: allocation weights derived from backend or computed by `deriveAllocationTarget()`
- `allocation_current`: defaults to `allocation_target` when no position tracking exists

## Data flow

1. Backend `/api/macro` fetches market data (yfinance/CoinGecko) + Sentinel event risk
2. Backend returns `data_status`, `verified`, `fallback_fields`, `field_sources`, `field_provenance`
3. `fetchMacro()` in `apiV2.ts` calls `normalizeMacroViewModel()` which normalizes all fields
4. Frontend receives a fully-typed `MacroViewModel` with no raw backend types exposed

## Remaining limitations

- `allocation_current` always equals `allocation_target` (no real position tracking)
- The `→` arrows in the portfolio table always show equal numbers for the same reason
- Quantum module score is always 0.5 (service not providing rich data)
