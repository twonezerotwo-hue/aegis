# AEGIS_DASHBOARD_RULES.md

## Dashboard truth rules

Dashboard values must not imply freshness unless source metadata proves it.

Every major macro/card/signal should show:

- source
- last_updated
- data_status
- fallback_used
- verified/live state if available

## Fallback macro values

`dashboard_react/backend/routes/macro.py` contains fallback macro values.

These are for UI continuity only.

They are not verified live market data.

If fallback or partial fallback is used:

- show `FALLBACK DATA` or `PARTIAL FALLBACK`
- show `NOT VERIFIED`
- do not show `LIVE`
- do not generate confident macro commentary
- do not produce rebalance or allocation instruction
- do not overwrite missing timestamps with client-side current time

## Allowed wording for fallback

Use:

> Verified macro data is unavailable. Fallback values are shown for interface continuity only.

Use:

> Verified allocation decision unavailable because macro data is fallback/partial.

Avoid:

- “live”
- “current”
- “anlık”
- “güncel”
- “rebalance gerekmiyor”
- final portfolio recommendation
