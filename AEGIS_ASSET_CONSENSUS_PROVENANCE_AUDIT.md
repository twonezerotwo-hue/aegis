# AEGIS Asset Consensus Provenance Audit

## Exact data path

- Dashboard V2 renders asset cards in `dashboard_react/frontend/src/pages/DashboardV2.tsx`.
- Each card is displayed by `dashboard_react/frontend/src/components/assets/AssetConsensusCard.tsx`.
- Standard fetch path:
  - `dashboard_react/frontend/src/services/apiV2.ts`
  - `GET /api/consensus` in `dashboard_react/backend/routes/dashboard.py`
  - `POST /process` in `consensus_engine/main.py`
- Live BTC override path:
  - `dashboard_react/frontend/src/hooks/useRealTimeFeed.ts`
  - `/api/live-feed` in `dashboard_react/backend/routes/stream.py`
  - stream normalization merges gateway and process consensus before the card sees it

## What the current values really are

- `XAU`, `XAG`, `BOND`, and `CASH` are not sourced from direct asset-native live price modules in the gateway path.
- Their gateway `technical`, `fundamental`, and `news` scores are derived from a shared Sentinel BTC macro snapshot plus asset formulas.
- Shared derived module scores now explicitly warn: `Shared module score, not asset-specific.`
- For crypto assets such as `BTC`, the gateway path can use Prometheus module data when available.
- Prometheus `news_sentiment_score` may still be shared or unlabeled rather than truly asset-specific.
- The process path can still receive missing explicit module inputs; when that happens it now marks those module scores as default-neutral fallback instead of looking verified.
- News, Sentinel, and Quantum modules can still be `LIVE`, `RECENT`, `STALE`, `FALLBACK`, `MISSING`, or `UNKNOWN` depending on actual timestamps and service responses.

## Patch summary

- Every consensus response now carries top-level provenance fields:
  - `asset`
  - `symbol`
  - `timeframe`
  - `data_status`
  - `source`
  - `last_updated`
  - `fallback_used`
  - `verified`
  - `module_sources`
  - `warnings`
- Each module source now reports:
  - service and source
  - timestamp and timestamp source
  - fallback and verification state
  - asset-specific vs shared score
  - per-module warnings
- Asset cards now visibly show:
  - Data Status
  - Source
  - Updated
  - Verified
  - Fallback used
  - module source details in `Detay`
- If overall consensus data is stale, fallback, mock, missing, or unknown, the card now shows:
  - `Signal is not verified because source data is stale/fallback/mock.`

## Files changed

- `consensus_engine/main.py`
- `dashboard_react/backend/routes/stream.py`
- `dashboard_react/frontend/src/services/apiV2.ts`
- `dashboard_react/frontend/src/types/dashboardV2.ts`
- `dashboard_react/frontend/src/components/assets/AssetConsensusCard.tsx`

## Remaining limitations

- `XAU`, `XAG`, `BOND`, and `CASH` are still formula-derived from shared macro context, not canonical live per-asset market feeds.
- Some upstream services still do not provide reliable source timestamps, so those modules remain `UNKNOWN` rather than being promoted to verified.
- Until a canonical verified live provider is connected per module and per asset, some asset-card signals remain illustrative or partially derived rather than fully verified live market outputs.
