# AEGIS Dashboard Horizon Allocation Patch

## Root cause

The `short` / `medium` / `long` selector was already reaching the backend macro route, but the allocation logic behind it only applied small additive deltas on top of broad regime defaults. Because the horizon shift was shallow, the resulting weights stayed too close together and did not behave like realistic horizon-aware allocations.

## Files changed

- `C:\Users\twone\Desktop\aegis_codex\dashboard_react\backend\services\portfolio_allocator.py`
- `C:\Users\twone\Desktop\aegis_codex\dashboard_react\backend\routes\macro.py`
- `C:\Users\twone\Desktop\aegis_codex\dashboard_react\backend\routes\stream.py`
- `C:\Users\twone\Desktop\aegis_codex\dashboard_react\backend\tests\test_macro_fallback_metadata.py`
- `C:\Users\twone\Desktop\aegis_codex\dashboard_react\backend\tests\test_portfolio_allocator_horizon.py`
- `C:\Users\twone\Desktop\aegis_codex\dashboard_react\backend\tests\test_frontend_allocation_static.py`
- `C:\Users\twone\Desktop\aegis_codex\dashboard_react\frontend\src\types\dashboardV2.ts`
- `C:\Users\twone\Desktop\aegis_codex\dashboard_react\frontend\src\services\apiV2.ts`
- `C:\Users\twone\Desktop\aegis_codex\dashboard_react\frontend\src\components\portfolio\AllocationWithTip.tsx`

## How horizon now affects allocation

- `short` starts from a defensive base with higher cash and lower BTC / commodity concentration.
- `medium` starts from a balanced base with moderate risk exposure.
- `long` starts from a structural base with higher BTC / gold / commodity exposure and lower cash.
- The allocator then applies overlays for regime, hedge posture, event risk, VIX, and data quality before normalizing back to 100%.
- The macro route now returns allocation metadata alongside `allocation_target`, including:
  - `allocation_horizon`
  - `allocation_profile`
  - `allocation_basis`
  - `data_status`
  - `verified`
  - `warnings`
  - `horizon_adjustments`

## Short / medium / long profile logic

- `short`
  - Base profile prioritizes cash and bonds.
  - BTC is capped lower than long horizon.
  - Commodity exposure stays modest.
- `medium`
  - Balanced starting mix between defensive ballast and growth sleeves.
  - Used as the neutral baseline for normalization and modest macro tilts.
- `long`
  - Higher structural BTC / gold / commodity exposure.
  - Lower cash, but cash never goes to zero.
  - Low-VIX conditions can modestly expand structural risk sleeves.

## Fallback / partial fallback behavior

- `FALLBACK` and `PARTIAL_FALLBACK` now force the allocation profile to `fallback_illustrative`.
- Illustrative allocations reduce risk concentration, raise the cash floor, and suppress verified-sounding rebalance output.
- The allocation card shows:
  - `Allocation horizon`
  - `Allocation profile`
  - `Illustrative allocation based on incomplete/fallback macro data.`

## Manual verification steps

1. Open [Dashboard V2](http://localhost:3001/v2).
2. Switch from `short` to `medium` to `long`.
3. Confirm the allocation card changes meaningfully:
   - `short` should keep more cash and less BTC than `long`.
   - `long` should show visibly higher BTC / structural exposure than `short`.
   - `medium` should sit between them instead of looking nearly identical.
4. Confirm the card shows `Allocation horizon` and `Allocation profile`.
5. Simulate or observe fallback / partial fallback macro data and confirm:
   - the existing fallback visibility remains in place
   - the allocation card shows the illustrative warning text
   - no verified rebalance language is shown while the macro data is fallback / partial fallback

## Remaining limitation

The allocation is still illustrative until a canonical verified live macro data provider is connected end-to-end.
